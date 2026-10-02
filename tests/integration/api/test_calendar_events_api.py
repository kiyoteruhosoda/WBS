"""予定の API（task #156 第 2 段、ADR-0009）。

- 回は閲覧者のタイムゾーンへ投影して返る（``start`` は Z 付きの UTC 瞬間）
- 他人の予定には読み書きとも届かない（404）
- ``expected_version`` が古ければ 409（状態は変わらない）
- 繰り返しの編集範囲: この回だけ・この回以降・すべて、飛ばす・戻す・移動・取り消し・以降を消す

日付は 2026-10-05（月）からの週。既定の利用者は Asia/Tokyo。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import timedelta

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db
from src.shared.clock import isoformat_utc, utcnow

OTHER_EMAIL = "other@example.com"
WEEKLY_MON_WED = {"type": "WEEKLY", "interval": 1, "weekly": {"weekdays": ["MO", "WE"]}}


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email,
            timezone="Asia/Tokyo", language="ja",
        )

    return current


@pytest.fixture
def other_user_id(client) -> int:
    session = next(get_db())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="他人")
        session.add(user)
        session.flush()
        user_id = user.id
        session.commit()
    finally:
        session.close()
    return user_id


@pytest.fixture
def two_users(client, other_user_id) -> Iterator:
    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_user_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _create(client, **fields) -> dict:
    body = {"title": "予定", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _weekly(client, **fields) -> dict:
    return _create(client, **{"title": "定例", "recurrence": WEEKLY_MON_WED, **fields})


def _occurrences(client, start: str, end: str, **params) -> list[dict]:
    res = client.get("/api/calendar/occurrences", params={"from": start, "to": end, **params})
    assert res.status_code == 200, res.text
    return res.json()


def _summary(occurrences: list[dict]) -> list[tuple[str, str, str]]:
    return [(o["date"], o["start_time"], o["title"]) for o in occurrences]


def _key(day: str, at: str = "09:00") -> dict:
    return {"date": day, "start_time": at}


# ── 作る・引く ──────────────────────────────────────────────────────────────


def test_single_event_is_listed_in_the_viewers_time_zone(client) -> None:
    created = _create(client, title="打合せ", start="2026-10-05T01:30:00Z", duration_minutes=45)
    assert created["kind"] == "SINGLE"
    assert created["time_zone"] == "Asia/Tokyo"
    assert created["start"] == "2026-10-05T01:30:00Z"
    assert created["version"] == 1

    [occurrence] = _occurrences(client, "2026-10-05", "2026-10-05")
    assert occurrence == {
        "id": str(created["id"]),
        "event_id": created["id"],
        "event_version": 1,
        "title": "打合せ",
        "start": "2026-10-05T01:30:00Z",
        "duration_minutes": 45,
        "date": "2026-10-05",
        "start_time": "10:30",
        "is_all_day": False,
        "color_key": "DEFAULT",
        "location": None,
        "task_id": None,
        "is_recurring": False,
        "is_moved": False,
        "is_overridden": False,
        "series_key": None,
        # 作るときに通知を省くと既定（4 つとも入り。ADR-0021）
        "alarm": {
            "enabled": True,
            "notify_15_min": True,
            "notify_5_min": True,
            "notify_1_min": True,
            "notify_at_start": True,
        },
        # 作るときに分類を省くと予定（ADR-0025）
        "event_type": "EVENT",
        "is_done": False,
    }


def test_another_viewer_time_zone_moves_the_local_day_but_not_the_instant(client) -> None:
    _create(client, start="2026-10-05T00:00:00Z")  # 東京 10/5 09:00 ＝ NY 10/4 20:00
    [occurrence] = _occurrences(client, "2026-10-04", "2026-10-04", time_zone="America/New_York")
    assert occurrence["date"] == "2026-10-04"
    assert occurrence["start_time"] == "20:00"
    assert occurrence["start"] == "2026-10-05T00:00:00Z"
    assert _occurrences(client, "2026-10-05", "2026-10-05", time_zone="America/New_York") == []


def test_weekly_event_expands_with_series_keys(client) -> None:
    created = _weekly(client)
    occurrences = _occurrences(client, "2026-10-05", "2026-10-11")
    assert _summary(occurrences) == [
        ("2026-10-05", "09:00", "定例"),
        ("2026-10-07", "09:00", "定例"),
    ]
    first = occurrences[0]
    assert first["id"] == f"{created['id']}:2026-10-05T09:00"
    assert first["is_recurring"] is True
    assert first["series_key"] == {"date": "2026-10-05", "start_time": "09:00"}
    assert occurrences[1]["start"] == "2026-10-07T00:00:00Z"
    assert created["recurrence"] == {
        "type": "WEEKLY", "interval": 1, "end_date": None,
        "weekly": {"weekdays": ["MO", "WE"]}, "monthly": None, "yearly": None, "adjustment": None,
    }


def test_all_day_event_stays_on_its_day_for_another_viewer(client) -> None:
    _create(client, title="終日", start="2026-10-05T15:00:00Z", duration_minutes=1440)  # 東京 10/6 0:00
    [occurrence] = _occurrences(client, "2026-10-06", "2026-10-06", time_zone="America/New_York")
    assert occurrence["is_all_day"] is True
    assert occurrence["date"] == "2026-10-06"
    assert occurrence["start"] == "2026-10-06T04:00:00Z"  # NY の 10/6 0:00


def test_bad_input_is_422(client) -> None:
    for body in (
        {"title": "", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60},
        {"title": "x", "start": "2026-10-05T00:00:30Z", "duration_minutes": 60},
        {"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 0},
        {"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60, "time_zone": "Mars/Base"},
        {"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
         "recurrence": {"type": "WEEKLY"}},
    ):
        assert client.post("/api/calendar/events", json=body).status_code == 422, body
    res = client.get("/api/calendar/occurrences", params={"from": "2026-10-10", "to": "2026-10-01"})
    assert res.status_code == 422


def test_event_can_point_at_my_task(client) -> None:
    task_id = client.post("/api/tasks", json={"title": "設計"}).json()["id"]
    _create(client, task_id=task_id)
    [occurrence] = _occurrences(client, "2026-10-05", "2026-10-05")
    assert occurrence["task_id"] == task_id


# ── 他人の予定 ──────────────────────────────────────────────────────────────


@pytest.fixture
def theirs(client, two_users) -> dict:
    two_users.other()
    created = _weekly(client, title="他人の定例")
    two_users.me()
    return created


def test_someone_elses_events_are_not_listed(client, theirs) -> None:
    assert _occurrences(client, "2026-10-05", "2026-10-11") == []
    res = client.get("/api/calendar/events", params={"from": "2026-10-05", "to": "2026-10-11"})
    assert res.json() == []


def test_someone_elses_event_cannot_be_read_or_changed(client, two_users, theirs) -> None:
    event_id = theirs["id"]
    key = {"occurrence": _key("2026-10-05")}
    assert client.get(f"/api/calendar/events/{event_id}").status_code == 404
    assert client.put(
        f"/api/calendar/events/{event_id}", json={"title": "乗っ取り"}
    ).status_code == 404
    assert client.put(
        f"/api/calendar/events/{event_id}/series",
        json={"title": "乗っ取り", "duration_minutes": 60, "recurrence": WEEKLY_MON_WED},
    ).status_code == 404
    for action in ("skip", "restore", "cancel-move", "delete-following"):
        res = client.post(f"/api/calendar/events/{event_id}/occurrences/{action}", json=key)
        assert res.status_code == 404, action
    assert client.post(
        f"/api/calendar/events/{event_id}/occurrences/move",
        json={**key, "start": "2026-10-06T00:00:00Z", "duration_minutes": 60},
    ).status_code == 404
    assert client.post(
        f"/api/calendar/events/{event_id}/occurrences/split",
        json={**key, "title": "x", "start": "2026-10-06T00:00:00Z", "duration_minutes": 60},
    ).status_code == 404
    assert client.post(
        f"/api/calendar/events/{event_id}/occurrences/following",
        json={**key, "title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
              "recurrence": WEEKLY_MON_WED},
    ).status_code == 404
    assert client.delete(f"/api/calendar/events/{event_id}").status_code == 404

    two_users.other()
    still = client.get(f"/api/calendar/events/{event_id}").json()
    assert still["title"] == "他人の定例"
    assert still["version"] == 1
    assert len(_occurrences(client, "2026-10-05", "2026-10-11")) == 2


def test_cannot_point_at_someone_elses_task_or_business_calendar(client, two_users) -> None:
    two_users.other()
    their_task = client.post("/api/tasks", json={"title": "他人のタスク"}).json()["id"]
    their_calendar = client.post("/api/business-calendars", json={"name": "他人の暦"}).json()["id"]
    two_users.me()

    res = client.post(
        "/api/calendar/events",
        json={"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
              "task_id": their_task},
    )
    assert res.status_code == 404
    rule = {
        **WEEKLY_MON_WED,
        "adjustment": {"condition": "HOLIDAY", "shift_unit": "BUSINESS_DAY", "shift_amount": 1,
                       "calendar_id": their_calendar},
    }
    res = client.post(
        "/api/calendar/events",
        json={"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
              "recurrence": rule},
    )
    assert res.status_code == 404


# ── 楽観ロック ──────────────────────────────────────────────────────────────


def test_stale_version_is_409_and_changes_nothing(client) -> None:
    created = _weekly(client)
    event_id = created["id"]
    res = client.put(
        f"/api/calendar/events/{event_id}", json={"title": "直した", "expected_version": 1}
    )
    assert res.status_code == 200, res.text
    current = res.json()["version"]
    assert current > 1

    res = client.put(
        f"/api/calendar/events/{event_id}", json={"title": "古い画面から", "expected_version": 1}
    )
    assert res.status_code == 409
    res = client.post(
        f"/api/calendar/events/{event_id}/occurrences/skip",
        json={"occurrence": _key("2026-10-05"), "expected_version": 1},
    )
    assert res.status_code == 409
    res = client.post(
        f"/api/calendar/events/{event_id}/occurrences/split",
        json={"occurrence": _key("2026-10-05"), "title": "x", "start": "2026-10-05T02:00:00Z",
              "duration_minutes": 60, "expected_version": 1},
    )
    assert res.status_code == 409
    assert client.delete(
        f"/api/calendar/events/{event_id}", params={"expected_version": 1}
    ).status_code == 409

    after = client.get(f"/api/calendar/events/{event_id}").json()
    assert after["title"] == "直した"
    assert after["version"] == current
    assert after["exceptions"] == []
    # 単発が増えていない（切り出しは巻き戻った）
    assert [o["title"] for o in _occurrences(client, "2026-10-05", "2026-10-05")] == ["直した"]

    assert client.delete(
        f"/api/calendar/events/{event_id}", params={"expected_version": current}
    ).status_code == 204
    assert client.get(f"/api/calendar/events/{event_id}").status_code == 404


def test_occurrence_carries_the_version_to_send_back(client) -> None:
    created = _weekly(client)
    first = _occurrences(client, "2026-10-05", "2026-10-05")[0]
    res = client.post(
        f"/api/calendar/events/{created['id']}/occurrences/skip",
        json={"occurrence": first["series_key"], "expected_version": first["event_version"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["version"] == first["event_version"] + 1


# ── 繰り返しの編集範囲 ──────────────────────────────────────────────────────


def test_this_occurrence_only(client) -> None:
    series = _weekly(client)
    res = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/split",
        json={"occurrence": _key("2026-10-07"), "title": "この回だけ",
              "start": "2026-10-07T05:00:00Z", "duration_minutes": 30,
              "expected_version": series["version"]},
    )
    assert res.status_code == 201, res.text
    single = res.json()
    assert single["kind"] == "SINGLE"

    assert _summary(_occurrences(client, "2026-10-05", "2026-10-14")) == [
        ("2026-10-05", "09:00", "定例"),
        ("2026-10-07", "14:00", "この回だけ"),
        ("2026-10-12", "09:00", "定例"),
        ("2026-10-14", "09:00", "定例"),
    ]
    after = client.get(f"/api/calendar/events/{series['id']}").json()
    assert after["exceptions"] == [
        {"occurrence": {"date": "2026-10-07", "start_time": "09:00"}, "type": "SKIP"}
    ]


def test_this_and_following_occurrences(client) -> None:
    series = _weekly(client)
    res = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/following",
        json={"occurrence": _key("2026-10-12"), "title": "新しい定例",
              "start": "2026-10-12T01:00:00Z", "duration_minutes": 60,
              "recurrence": {"type": "WEEKLY", "weekly": {"weekdays": ["MO"]}}},
    )
    assert res.status_code == 201, res.text
    new_series = res.json()
    assert new_series["id"] != series["id"]

    assert _summary(_occurrences(client, "2026-10-05", "2026-10-21")) == [
        ("2026-10-05", "09:00", "定例"),
        ("2026-10-07", "09:00", "定例"),
        ("2026-10-12", "10:00", "新しい定例"),
        ("2026-10-19", "10:00", "新しい定例"),
    ]
    old = client.get(f"/api/calendar/events/{series['id']}").json()
    assert old["recurrence"]["end_date"] == "2026-10-11"


def test_following_from_the_first_occurrence_replaces_the_series(client) -> None:
    series = _weekly(client)
    res = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/following",
        json={"occurrence": _key("2026-10-05"), "title": "全部入れ替え",
              "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
              "recurrence": WEEKLY_MON_WED},
    )
    assert res.status_code == 201, res.text
    # 元の系列は消え、新しい系列だけが残る（SQLite は消えた id を使い回しうるので id では比べない）
    events = client.get(
        "/api/calendar/events", params={"from": "2026-10-05", "to": "2026-10-11"}
    ).json()
    assert [e["title"] for e in events] == ["全部入れ替え"]
    assert {o["title"] for o in _occurrences(client, "2026-10-05", "2026-10-11")} == {"全部入れ替え"}


def test_all_occurrences_keeps_the_exceptions(client) -> None:
    series = _weekly(client)
    skipped = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/skip",
        json={"occurrence": _key("2026-10-07")},
    ).json()
    res = client.put(
        f"/api/calendar/events/{series['id']}/series",
        json={"title": "すべて直した", "duration_minutes": 90, "recurrence": WEEKLY_MON_WED,
              "color_key": "TOMATO", "expected_version": skipped["version"]},
    )
    assert res.status_code == 200, res.text

    occurrences = _occurrences(client, "2026-10-05", "2026-10-14")
    assert _summary(occurrences) == [
        ("2026-10-05", "09:00", "すべて直した"),
        ("2026-10-12", "09:00", "すべて直した"),
        ("2026-10-14", "09:00", "すべて直した"),
    ]
    assert {(o["duration_minutes"], o["color_key"]) for o in occurrences} == {(90, "TOMATO")}


def test_skip_and_restore(client) -> None:
    series = _weekly(client)
    url = f"/api/calendar/events/{series['id']}/occurrences"
    assert client.post(f"{url}/skip", json={"occurrence": _key("2026-10-07")}).status_code == 200
    assert [o["date"] for o in _occurrences(client, "2026-10-05", "2026-10-11")] == ["2026-10-05"]

    assert client.post(f"{url}/restore", json={"occurrence": _key("2026-10-07")}).status_code == 200
    assert [o["date"] for o in _occurrences(client, "2026-10-05", "2026-10-11")] == [
        "2026-10-05", "2026-10-07",
    ]
    # 飛ばしていない回を戻すのは 404
    assert client.post(f"{url}/restore", json={"occurrence": _key("2026-10-07")}).status_code == 404


def test_move_and_cancel_the_move(client) -> None:
    series = _weekly(client)
    url = f"/api/calendar/events/{series['id']}/occurrences"
    res = client.post(
        f"{url}/move",
        json={"occurrence": _key("2026-10-07"), "start": "2026-10-08T03:00:00Z",
              "duration_minutes": 30, "title": "木曜へ"},
    )
    assert res.status_code == 200, res.text

    occurrences = _occurrences(client, "2026-10-05", "2026-10-11")
    assert _summary(occurrences) == [
        ("2026-10-05", "09:00", "定例"),
        ("2026-10-08", "12:00", "木曜へ"),
    ]
    moved = occurrences[1]
    assert moved["is_moved"] is True
    assert moved["duration_minutes"] == 30
    assert moved["series_key"] == {"date": "2026-10-07", "start_time": "09:00"}

    res = client.post(f"{url}/cancel-move", json={"occurrence": moved["series_key"]})
    assert res.status_code == 200, res.text
    assert _summary(_occurrences(client, "2026-10-05", "2026-10-11")) == [
        ("2026-10-05", "09:00", "定例"),
        ("2026-10-07", "09:00", "定例"),
    ]


def test_delete_following_occurrences(client) -> None:
    series = _weekly(client)
    res = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/delete-following",
        json={"occurrence": _key("2026-10-12")},
    )
    assert res.status_code == 204
    assert [o["date"] for o in _occurrences(client, "2026-10-05", "2026-10-21")] == [
        "2026-10-05", "2026-10-07",
    ]


def test_single_event_is_rescheduled_by_put(client) -> None:
    created = _create(client, title="単発")
    res = client.put(
        f"/api/calendar/events/{created['id']}",
        json={"title": "単発", "start": "2026-10-06T06:00:00Z", "duration_minutes": 15,
              "expected_version": created["version"]},
    )
    assert res.status_code == 200, res.text
    assert _summary(_occurrences(client, "2026-10-05", "2026-10-06")) == [
        ("2026-10-06", "15:00", "単発"),
    ]


def test_occurrence_operations_on_a_single_event_are_422(client) -> None:
    created = _create(client)
    res = client.post(
        f"/api/calendar/events/{created['id']}/occurrences/move",
        json={"occurrence": _key("2026-10-05"), "start": "2026-10-06T00:00:00Z",
              "duration_minutes": 60},
    )
    assert res.status_code == 422


def test_business_day_shift_uses_my_calendar(client) -> None:
    calendar = client.post("/api/business-calendars", json={"name": "日本"}).json()
    client.post(
        f"/api/business-calendars/{calendar['id']}/holidays",
        json={"date": "2026-10-12", "name": "スポーツの日"},
    )
    rule = {
        "type": "WEEKLY", "weekly": {"weekdays": ["MO"]},
        "adjustment": {"condition": "HOLIDAY", "shift_unit": "BUSINESS_DAY", "shift_amount": 1,
                       "calendar_id": calendar["id"]},
    }
    _create(client, title="月曜の定例", recurrence=rule)
    occurrences = _occurrences(client, "2026-10-12", "2026-10-13")
    assert [(o["date"], o["series_key"]["date"]) for o in occurrences] == [
        ("2026-10-13", "2026-10-12"),
    ]


# ── 打刻の既定のタスク（ADR-0008） ─────────────────────────────────────────


def test_timer_start_defaults_to_the_task_of_the_current_occurrence(client) -> None:
    task_id = client.post("/api/tasks", json={"title": "いまの予定のタスク"}).json()["id"]
    now = utcnow().replace(second=0, microsecond=0)
    _create(
        client, title="いまの予定", start=isoformat_utc(now - timedelta(minutes=30)),
        duration_minutes=120, task_id=task_id,
    )
    res = client.post("/api/time-entries/start", json=None)
    assert res.status_code == 201, res.text
    assert res.json()["started"]["task_id"] == task_id
