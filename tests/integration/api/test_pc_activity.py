"""PC を使っていた時間（WinTrack → wbstimer、task #397 / ADR-0049）。日ごとに丸ごと置き換え、締めには関係しない。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import (
    ClosingPeriodModel,
    PcActivityDayModel,
    PcActivitySpanModel,
    UserModel,
)
from src.presentation.api.dependencies import get_db
from src.shared.clock import utcnow

JST = timedelta(hours=9)


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


def _today_jst() -> date:
    return (utcnow() + JST).date()


def _yesterday_jst() -> date:
    return _today_jst() - timedelta(days=1)


def _jst(day: date, hour: int, minute: int = 0) -> str:
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}:00+09:00"


def _utc(day: date, hour: int, minute: int = 0) -> datetime:
    return datetime.combine(day, datetime.min.time()) + timedelta(hours=hour, minutes=minute) - JST


def _z(value: datetime) -> str:
    return f"{value.isoformat()}Z"


def _put(client, day: date, *spans: tuple[str, str], time_zone: str = "Asia/Tokyo"):
    return client.put(
        f"/api/pc-activity/{day.isoformat()}",
        json={
            "time_zone": time_zone,
            "spans": [{"started_at": s, "ended_at": e} for s, e in spans],
        },
    )


def _get_day(client, day: date):
    start = _utc(day, 0)
    return client.get(
        "/api/pc-activity", params={"start": _z(start), "end": _z(start + timedelta(days=1))}
    )


def _spans(body: dict) -> list[tuple[str, str]]:
    return [(s["started_at"], s["ended_at"]) for s in body["spans"]]


def test_spans_of_today_are_saved_and_read_back_in_order(client) -> None:
    """AC1: 今日の区間 2 つを送ると同じ区間が返り、今日 0 時〜翌 0 時で始まりの順に 2 つ読める。"""
    now = utcnow().replace(microsecond=0)
    today = _today_jst()
    day_start = _utc(today, 0)
    if now - day_start < timedelta(hours=1):
        pytest.skip("JST の 0 時直後は今日の過去の区間を 2 つ作れない")
    first = (day_start + (now - day_start) * 0.1, day_start + (now - day_start) * 0.3)
    second = (day_start + (now - day_start) * 0.5, now - timedelta(minutes=1))
    first = (first[0].replace(microsecond=0), first[1].replace(microsecond=0))
    second = (second[0].replace(microsecond=0), second[1].replace(microsecond=0))

    # 遅いほうを先に送っても始まりの順に返る
    res = _put(client, today, (_z(second[0]), _z(second[1])), (_z(first[0]), _z(first[1])))
    assert res.status_code == 200, res.text
    body = res.json()
    expected = [(_z(first[0]), _z(first[1])), (_z(second[0]), _z(second[1]))]
    assert body["date"] == today.isoformat()
    assert _spans(body) == expected
    assert body["updated_at"].endswith("Z")

    listed = _get_day(client, today)
    assert listed.status_code == 200, listed.text
    assert _spans(listed.json()) == expected
    assert listed.json()["updated_at"] == body["updated_at"]


def test_resending_replaces_and_an_empty_list_clears_the_day(client) -> None:
    """AC2: 送り直すと置き換わり、``spans: []`` でその日の区間が全部消える（ほかの日は残る）。"""
    day = _yesterday_jst()
    before = day - timedelta(days=1)
    assert _put(client, before, (_jst(before, 9), _jst(before, 18))).status_code == 200
    _put(client, day, (_jst(day, 9), _jst(day, 12)), (_jst(day, 13), _jst(day, 18)))

    res = _put(client, day, (_jst(day, 10), _jst(day, 11)))
    assert _spans(res.json()) == [(_z(_utc(day, 10)), _z(_utc(day, 11)))]
    assert _spans(_get_day(client, day).json()) == [(_z(_utc(day, 10)), _z(_utc(day, 11)))]

    cleared = _put(client, day)
    assert cleared.status_code == 200
    assert cleared.json()["spans"] == []
    listed = _get_day(client, day).json()
    assert listed["spans"] == []
    # 空でも受けた時刻は残る（送れているかが分かる）
    assert listed["updated_at"] == cleared.json()["updated_at"]
    assert len(_get_day(client, before).json()["spans"]) == 1


def test_nothing_sent_yet_reads_as_empty(client) -> None:
    listed = _get_day(client, _yesterday_jst())
    assert listed.status_code == 200
    assert listed.json() == {"spans": [], "updated_at": None}


@pytest.mark.parametrize(
    "spans",
    [
        [("{d}T12:00:00+09:00", "{d}T11:00:00+09:00")],  # 逆転
        [("{d}T12:00:00+09:00", "{d}T12:00:00+09:00")],  # 長さ 0
        [
            ("{d}T12:00:00+09:00", "{d}T13:00:00+09:00"),
            ("{d}T12:30:00+09:00", "{d}T14:00:00+09:00"),
        ],  # 重なり
        [("{d}T23:30:00+09:00", "{n}T00:30:00+09:00")],  # その日からはみ出す
        [("{p}T23:30:00+09:00", "{d}T00:30:00+09:00")],  # 前の日からはみ出す
    ],
    ids=["reversed", "empty", "overlapping", "past-the-end", "before-the-start"],
)
def test_bad_spans_are_refused_and_keep_what_was_saved(client, spans) -> None:
    """AC3: 不正な区間は 422 で、保存されていた区間は変わらない。"""
    day = _yesterday_jst()
    _put(client, day, (_jst(day, 9), _jst(day, 10)))
    fill = {"d": day, "n": day + timedelta(days=1), "p": day - timedelta(days=1)}
    filled = [(s.format(**fill), e.format(**fill)) for s, e in spans]
    assert _put(client, day, *filled).status_code == 422
    assert _spans(_get_day(client, day).json()) == [(_z(_utc(day, 9)), _z(_utc(day, 10)))]


def test_days_too_old_or_in_the_future_are_refused(client) -> None:
    """AC3: 7 日より前の日・未来の日・未来の区間は 422 で、保存されていた区間は変わらない。"""
    today = _today_jst()
    yesterday = _yesterday_jst()
    _put(client, yesterday, (_jst(yesterday, 9), _jst(yesterday, 10)))

    old = today - timedelta(days=10)
    assert _put(client, old, (_jst(old, 9), _jst(old, 10))).status_code == 422
    tomorrow = today + timedelta(days=2)
    assert _put(client, tomorrow).status_code == 422
    future = utcnow().replace(microsecond=0) + timedelta(hours=1)
    assert _put(client, today, (_z(future), _z(future + timedelta(minutes=5)))).status_code == 422
    assert _put(client, yesterday, time_zone="Mars/Olympus").status_code == 422
    assert _spans(_get_day(client, yesterday).json()) == [
        (_z(_utc(yesterday, 9)), _z(_utc(yesterday, 10)))
    ]


def test_a_closed_day_is_still_accepted(client, db) -> None:
    """AC4: 確定済みの締めの期間の日でも 200 で受ける（締めには関係しない）。"""
    db.query(UserModel).update({UserModel.timezone: "Asia/Tokyo"})
    day = _yesterday_jst()
    start = _utc(day, 0)
    db.add(
        ClosingPeriodModel(
            user_id=SINGLE_USER_ID,
            first_day=day,
            last_day=day,
            time_zone="Asia/Tokyo",
            starts_at=start,
            ends_at=start + timedelta(days=1),
            closed_at=utcnow(),
        )
    )
    db.commit()
    res = _put(client, day, (_jst(day, 9), _jst(day, 12)))
    assert res.status_code == 200, res.text
    assert len(_get_day(client, day).json()["spans"]) == 1


def test_days_older_than_35_days_are_dropped_on_write(client, db) -> None:
    """ADR-0049: 書くときに 35 日より前に終わった日を区間ごと消す。"""
    old = _today_jst() - timedelta(days=40)
    day = PcActivityDayModel(
        user_id=SINGLE_USER_ID,
        local_date=old,
        time_zone="Asia/Tokyo",
        starts_at=_utc(old, 0),
        ends_at=_utc(old + timedelta(days=1), 0),
        updated_at=utcnow(),
    )
    db.add(day)
    db.flush()
    db.add(
        PcActivitySpanModel(
            day_id=day.id, user_id=SINGLE_USER_ID, started_at=_utc(old, 9), ended_at=_utc(old, 10)
        )
    )
    db.commit()
    assert len(_get_day(client, old).json()["spans"]) == 1

    yesterday = _yesterday_jst()
    assert _put(client, yesterday, (_jst(yesterday, 9), _jst(yesterday, 10))).status_code == 200
    assert _get_day(client, old).json() == {"spans": [], "updated_at": None}
    assert len(_get_day(client, yesterday).json()["spans"]) == 1
