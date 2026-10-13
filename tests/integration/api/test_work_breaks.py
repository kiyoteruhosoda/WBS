"""休み（WinTrack、task #392 / ADR-0048）。日ごとに丸ごと置き換え、実績の長さから重なる分を引く。"""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date, datetime, timedelta

import pytest

from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import ClosingPeriodModel, UserModel, WorkBreakModel
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


@pytest.fixture(autouse=True)
def tokyo(client, db) -> None:
    db.query(UserModel).update({UserModel.timezone: "Asia/Tokyo"})
    db.commit()


def _yesterday_jst() -> date:
    return (utcnow() + JST).date() - timedelta(days=1)


def _jst(day: date, hour: int, minute: int = 0) -> str:
    return f"{day.isoformat()}T{hour:02d}:{minute:02d}:00+09:00"


def _put(client, day: date, *spans: tuple[str, str], time_zone: str = "Asia/Tokyo"):
    return client.put(
        f"/api/breaks/auto/{day.isoformat()}",
        json={"time_zone": time_zone, "breaks": [{"started_at": s, "ended_at": e} for s, e in spans]},
    )


def _z(value: datetime) -> str:
    return f"{value.isoformat()}Z"


def test_breaks_of_a_day_are_replaced_as_a_whole(client) -> None:
    day = _yesterday_jst()
    res = _put(client, day, (_jst(day, 12), _jst(day, 12, 45)), (_jst(day, 15), _jst(day, 15, 10)))
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["date"] == day.isoformat()
    assert [(b["source"], b["started_at"]) for b in body["breaks"]] == [
        ("auto", _z(datetime.combine(day, datetime.min.time()) + timedelta(hours=12) - JST)),
        ("auto", _z(datetime.combine(day, datetime.min.time()) + timedelta(hours=15) - JST)),
    ]

    # 送り直すと置き換わる（増えない）
    res = _put(client, day, (_jst(day, 13), _jst(day, 13, 30)))
    assert [b["started_at"] for b in res.json()["breaks"]] == [
        _z(datetime.combine(day, datetime.min.time()) + timedelta(hours=13) - JST)
    ]
    start = datetime.combine(day, datetime.min.time()) - JST
    listed = client.get("/api/breaks", params={"start": _z(start), "end": _z(start + timedelta(days=1))})
    assert listed.status_code == 200
    assert len(listed.json()["breaks"]) == 1
    # [] で全部消える
    assert _put(client, day).json()["breaks"] == []
    listed = client.get("/api/breaks", params={"start": _z(start), "end": _z(start + timedelta(days=1))})
    assert listed.json()["breaks"] == []


def test_other_days_are_left_alone(client) -> None:
    day = _yesterday_jst()
    before = day - timedelta(days=1)
    _put(client, before, (_jst(before, 12), _jst(before, 13)))
    _put(client, day, (_jst(day, 12), _jst(day, 13)))
    _put(client, day)
    start = datetime.combine(before, datetime.min.time()) - JST
    listed = client.get("/api/breaks", params={"start": _z(start), "end": _z(start + timedelta(days=2))})
    assert len(listed.json()["breaks"]) == 1


@pytest.mark.parametrize(
    "spans",
    [
        [("{d}T12:00:00+09:00", "{d}T11:00:00+09:00")],  # 逆転
        [("{d}T12:00:00+09:00", "{d}T13:00:00+09:00"), ("{d}T12:30:00+09:00", "{d}T14:00:00+09:00")],  # 重なり
        [("{d}T23:30:00+09:00", "{n}T00:30:00+09:00")],  # その日に収まらない
    ],
    ids=["reversed", "overlapping", "outside-the-day"],
)
def test_bad_breaks_are_refused(client, spans) -> None:
    day = _yesterday_jst()
    filled = [(s.format(d=day, n=day + timedelta(days=1)), e.format(d=day, n=day + timedelta(days=1))) for s, e in spans]
    assert _put(client, day, *filled).status_code == 422


def test_days_out_of_range_and_unknown_time_zones_are_refused(client) -> None:
    old = _yesterday_jst() - timedelta(days=10)
    assert _put(client, old).status_code == 422
    future = _yesterday_jst() + timedelta(days=3)
    assert _put(client, future).status_code == 422
    assert _put(client, _yesterday_jst(), time_zone="Mars/Olympus").status_code == 422


def test_a_closed_day_is_refused(client, db) -> None:
    day = _yesterday_jst()
    start = datetime.combine(day, datetime.min.time()) - JST
    db.add(ClosingPeriodModel(
        user_id=SINGLE_USER_ID, first_day=day, last_day=day, time_zone="Asia/Tokyo",
        starts_at=start, ends_at=start + timedelta(days=1), closed_at=utcnow(),
    ))
    db.commit()
    res = _put(client, day, (_jst(day, 12), _jst(day, 13)))
    assert res.status_code == 409
    assert res.json()["detail"] == "closed"


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _entry(client, start: str, end: str, task_id: int) -> None:
    res = client.post("/api/time-entries", json={"started_at": start, "ended_at": end, "task_id": task_id})
    assert res.status_code == 201, res.text


def _past_break(db, start: str, end: str) -> None:
    # 9 月の休み（PUT は 7 日より前を受けないので、表へ直に入れる）
    db.add(WorkBreakModel(
        user_id=SINGLE_USER_ID, started_at=datetime.fromisoformat(start), ended_at=datetime.fromisoformat(end),
        source="auto", created_at=utcnow(),
    ))
    db.commit()


def test_the_closing_board_shows_breaks_and_takes_them_off_the_totals(client, db) -> None:
    task = _task(client, "設計")
    # 9/3 JST 9:00〜18:00、休み 12:00〜12:45
    _entry(client, "2026-09-03T00:00:00Z", "2026-09-03T09:00:00Z", task)
    _past_break(db, "2026-09-03 03:00:00", "2026-09-03 03:45:00")

    board = client.get("/api/closing-periods/2026-09-01").json()
    assert [(b["started_at"], b["ended_at"]) for b in board["breaks"]] == [
        ("2026-09-03T03:00:00Z", "2026-09-03T03:45:00Z")
    ]
    assert [(t["work_date"], t["seconds"]) for t in board["daily_totals"]] == [
        ("2026-09-03", 9 * 3600 - 45 * 60)
    ]

    # 確定の work_logs も同じ計算
    res = client.post("/api/closing-periods/2026-09-01/close")
    assert res.status_code == 200, res.text
    [log] = res.json()["work_logs"]
    assert log["duration_seconds"] == 9 * 3600 - 45 * 60


def test_actuals_take_breaks_off_tracked_time(client, db) -> None:
    task = _task(client, "設計")
    _entry(client, "2026-09-03T00:00:00Z", "2026-09-03T02:00:00Z", task)
    _past_break(db, "2026-09-03 01:00:00", "2026-09-03 01:30:00")
    body = client.get(
        "/api/actuals/periods", params={"unit": "closing", "from": "2026-09-01", "to": "2026-09-15"}
    ).json()
    assert body["periods"][0]["tracked_task_seconds"] == 90 * 60
