"""予定のカレンダーを複数・表示の選択・表示の組み合わせ（task #191、ADR-0027）。

- 一覧で既定のカレンダー「予定」ができる（移行の後に来た利用者にも）。予定は省けばそこへ入る
- 予定を別のカレンダーへ入れる・移す。回の一覧にカレンダーと色が付く
- 他人のカレンダーには入れられない・触れない（404）。既定は消せない（409）
- 消すと中の予定は既定へ移る
- 表示の選択はサーバーに覚える。新しいカレンダーは最初から表示
- 組み合わせを当てると入っているカレンダーだけが表示
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other@example.com"
MONDAY_9_JST = "2026-10-05T00:00:00Z"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email,
            timezone="Asia/Tokyo", language="ja",
        )

    return current


@pytest.fixture
def two_users(client) -> Iterator:
    session = next(get_db())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="他人")
        session.add(user)
        session.flush()
        other_id = user.id
        session.commit()
    finally:
        session.close()

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _calendars(client) -> list[dict]:
    res = client.get("/api/calendars")
    assert res.status_code == 200, res.text
    return res.json()


def _new_calendar(client, name: str, color_key: str = "TOMATO") -> dict:
    res = client.post("/api/calendars", json={"name": name, "color_key": color_key})
    assert res.status_code == 201, res.text
    return res.json()


def _event(client, **fields) -> dict:
    body = {"title": "会議", "start": MONDAY_9_JST, "duration_minutes": 60, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _occurrences(client) -> list[dict]:
    res = client.get("/api/calendar/occurrences", params={"from": "2026-10-05", "to": "2026-10-05"})
    assert res.status_code == 200, res.text
    return res.json()


def test_default_calendar_is_made_and_events_go_there(client) -> None:
    listed = _calendars(client)
    assert [(c["name"], c["is_default"], c["is_visible"], c["kind"]) for c in listed] == [
        ("予定", True, True, "EVENTS")
    ]
    event = _event(client)
    assert event["calendar_id"] == listed[0]["id"]
    assert _calendars(client) == listed  # 2 度目は作らない


def test_event_in_another_calendar_carries_its_color(client) -> None:
    work = _new_calendar(client, "仕事", "TOMATO")
    _event(client, calendar_id=work["id"])
    [occurrence] = _occurrences(client)
    assert (occurrence["calendar_id"], occurrence["calendar_color_key"], occurrence["color_key"]) == (
        work["id"], "TOMATO", "DEFAULT",
    )


def test_moving_an_event_by_editing(client) -> None:
    work = _new_calendar(client, "仕事")
    event = _event(client)
    res = client.put(
        f"/api/calendar/events/{event['id']}",
        json={"title": "会議", "calendar_id": work["id"], "expected_version": event["version"]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["calendar_id"] == work["id"]
    # 省けば今のまま（ドラッグなどの部分的な更新で戻らない）
    res = client.put(
        f"/api/calendar/events/{event['id']}",
        json={"title": "会議（改）", "expected_version": res.json()["version"]},
    )
    assert res.json()["calendar_id"] == work["id"]


def test_other_users_calendar_is_out_of_reach(client, two_users) -> None:
    two_users.other()
    theirs = _new_calendar(client, "他人の")
    their_default = next(c for c in _calendars(client) if c["is_default"])
    two_users.me()

    assert [c["name"] for c in _calendars(client)] == ["予定"]
    res = client.post(
        "/api/calendar/events",
        json={"title": "x", "start": MONDAY_9_JST, "duration_minutes": 30, "calendar_id": theirs["id"]},
    )
    assert res.status_code == 404
    assert client.put(
        f"/api/calendars/{theirs['id']}", json={"name": "奪う", "color_key": "BASIL"}
    ).status_code == 404
    assert client.delete(f"/api/calendars/{their_default['id']}").status_code == 404
    assert client.delete(f"/api/calendars/{theirs['id']}").status_code == 404
    assert client.put(
        "/api/calendars/visibility", json={"visible_calendar_ids": [theirs["id"]]}
    ).status_code == 404

    two_users.other()
    assert {c["name"]: c["is_visible"] for c in _calendars(client)} == {"予定": True, "他人の": True}


def test_deleting_moves_events_to_default_and_default_cannot_be_deleted(client) -> None:
    default = _calendars(client)[0]
    work = _new_calendar(client, "仕事")
    event = _event(client, calendar_id=work["id"])

    assert client.delete(f"/api/calendars/{default['id']}").status_code == 409
    res = client.delete(f"/api/calendars/{work['id']}")
    assert res.status_code == 200, res.text
    assert res.json() == {"moved_event_count": 1}
    moved = client.get(f"/api/calendar/events/{event['id']}").json()
    assert moved["calendar_id"] == default["id"]
    assert [c["id"] for c in _calendars(client)] == [default["id"]]


def test_visibility_is_remembered_and_new_calendars_start_visible(client) -> None:
    default = _calendars(client)[0]
    work = _new_calendar(client, "仕事")
    res = client.put("/api/calendars/visibility", json={"visible_calendar_ids": [work["id"]]})
    assert res.status_code == 200, res.text
    assert {c["id"]: c["is_visible"] for c in _calendars(client)} == {
        default["id"]: False, work["id"]: True,
    }
    home = _new_calendar(client, "家")
    assert home["is_visible"] is True


def test_preset_switches_the_selection_in_one_go(client) -> None:
    default = _calendars(client)[0]
    work = _new_calendar(client, "仕事")
    res = client.post(
        "/api/calendar-view-presets", json={"name": "仕事だけ", "calendar_ids": [work["id"]]}
    )
    assert res.status_code == 201, res.text
    preset = res.json()

    res = client.post(f"/api/calendar-view-presets/{preset['id']}/apply")
    assert res.status_code == 200, res.text
    assert {c["id"]: c["is_visible"] for c in res.json()} == {
        default["id"]: False, work["id"]: True,
    }
    assert [p["name"] for p in client.get("/api/calendar-view-presets").json()] == ["仕事だけ"]

    res = client.put(
        f"/api/calendar-view-presets/{preset['id']}",
        json={"name": "計画", "calendar_ids": [default["id"], work["id"]]},
    )
    assert res.json()["calendar_ids"] == [default["id"], work["id"]]
    assert client.delete(f"/api/calendar-view-presets/{preset['id']}").status_code == 204
    assert client.get("/api/calendar-view-presets").json() == []


def test_reorder(client) -> None:
    default = _calendars(client)[0]
    work = _new_calendar(client, "仕事")
    res = client.put("/api/calendars/order", json={"calendar_ids": [work["id"], default["id"]]})
    assert res.status_code == 200, res.text
    assert [c["name"] for c in _calendars(client)] == ["仕事", "予定"]
