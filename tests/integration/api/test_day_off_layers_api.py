"""休みの 4 層と営業日の判定の API（task #191、ADR-0029）。

- カレンダーの一覧に 4 層（営業日・会社の公休・私の休み・日本の祝日）が並ぶ（消せない・予定は入れない）
- 層へ日を足す・消す・日本の祝日を年ごとに入れる。他人の層には触れない
- 期間の休みの理由（曜日の休み・層の日）。「休みとして数える」を外すと営業日のまま
- 営業日シフトは私の休みを避ける。表示のチェックを外しても計算は変わらない

2026-10-12（月）はスポーツの日。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other@example.com"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email, timezone="Asia/Tokyo", language="ja",
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


def _layers(client) -> dict[str, dict]:
    res = client.get("/api/calendars")
    assert res.status_code == 200, res.text
    return {
        (c["day_off_reason"] or "WORKWEEK"): c for c in res.json() if c["kind"] != "EVENTS"
    }


def _marks(client, start: str, end: str) -> list[tuple[str, str, bool]]:
    res = client.get("/api/calendars/days-off", params={"from": start, "to": end})
    assert res.status_code == 200, res.text
    return [(m["date"], m["reason"], m["counts_as_day_off"]) for m in res.json()]


def test_four_layers_are_listed_and_cannot_be_deleted_or_hold_events(client) -> None:
    layers = _layers(client)
    assert {k: (v["name"], v["kind"], v["counts_as_day_off"]) for k, v in layers.items()} == {
        "WORKWEEK": ("営業日", "WORKWEEK", False),
        "COMPANY": ("会社の休日", "DAYS_OFF", True),
        "PERSONAL": ("個人の休日", "DAYS_OFF", True),
        "NATIONAL_HOLIDAY": ("日本の祝日", "DAYS_OFF", True),
    }
    assert layers["WORKWEEK"]["workdays"] == ["MO", "TU", "WE", "TH", "FR"]
    assert client.delete(f"/api/calendars/{layers['PERSONAL']['id']}").status_code == 409
    res = client.post(
        "/api/calendar/events",
        json={"title": "x", "start": "2026-10-05T00:00:00Z", "duration_minutes": 30,
              "calendar_id": layers["PERSONAL"]["id"]},
    )
    assert res.status_code == 422
    assert len(_layers(client)) == 4  # 2 度目は作らない


def test_days_are_added_removed_and_imported(client) -> None:
    layers = _layers(client)
    personal = layers["PERSONAL"]["id"]
    res = client.post(f"/api/calendars/{personal}/days-off", json={"date": "2026-10-13", "name": " 旅行 "})
    assert res.status_code == 200, res.text
    assert res.json() == [{"date": "2026-10-13", "name": "旅行"}]
    res = client.post(f"/api/calendars/{layers['NATIONAL_HOLIDAY']['id']}/days-off/japan", json={"year": 2026})
    assert {"date": "2026-10-12", "name": "スポーツの日"} in res.json()

    assert _marks(client, "2026-10-10", "2026-10-13") == [
        ("2026-10-10", "WEEKLY", True),
        ("2026-10-11", "WEEKLY", True),
        ("2026-10-12", "NATIONAL_HOLIDAY", True),
        ("2026-10-13", "PERSONAL", True),
    ]
    res = client.delete(f"/api/calendars/{personal}/days-off/2026-10-13")
    assert res.json() == []
    # 予定のカレンダー・営業日の層には日を足せない
    events = next(c for c in client.get("/api/calendars").json() if c["kind"] == "EVENTS")
    assert client.post(
        f"/api/calendars/{events['id']}/days-off", json={"date": "2026-10-13"}
    ).status_code == 422


def test_not_counting_keeps_the_day_a_business_day_but_still_marks_it(client) -> None:
    personal = _layers(client)["PERSONAL"]
    client.post(f"/api/calendars/{personal['id']}/days-off", json={"date": "2026-10-13"})
    res = client.put(
        f"/api/calendars/{personal['id']}",
        json={"name": personal["name"], "color_key": personal["color_key"], "counts_as_day_off": False},
    )
    assert res.status_code == 200, res.text
    assert res.json()["counts_as_day_off"] is False
    assert _marks(client, "2026-10-13", "2026-10-13") == [("2026-10-13", "PERSONAL", False)]


def test_workweek_rule_can_change(client) -> None:
    workweek = _layers(client)["WORKWEEK"]
    res = client.put(
        f"/api/calendars/{workweek['id']}",
        json={"name": "営業日", "color_key": "GRAPHITE", "workdays": ["MO", "TU", "WE", "TH"]},
    )
    assert res.status_code == 200, res.text
    assert ("2026-10-09", "WEEKLY", True) in _marks(client, "2026-10-09", "2026-10-09")


def test_other_users_layers_are_out_of_reach(client, two_users) -> None:
    two_users.other()
    theirs = _layers(client)["PERSONAL"]["id"]
    two_users.me()
    assert client.post(f"/api/calendars/{theirs}/days-off", json={"date": "2026-10-13"}).status_code == 404
    assert client.get(f"/api/calendars/{theirs}/days-off").status_code == 404
    assert client.delete(f"/api/calendars/{theirs}/days-off/2026-10-13").status_code == 404


def _weekly_monday_dates(client) -> list[str]:
    res = client.post(
        "/api/calendar/events",
        json={
            "title": "週次", "start": "2026-10-05T00:00:00Z", "duration_minutes": 60,
            "recurrence": {
                "type": "WEEKLY", "interval": 1, "weekly": {"weekdays": ["MO"]},
                "end_date": "2026-10-25",
                "adjustment": {"condition": "HOLIDAY", "shift_unit": "BUSINESS_DAY", "shift_amount": 1},
            },
        },
    )
    assert res.status_code == 201, res.text
    occurrences = client.get(
        "/api/calendar/occurrences", params={"from": "2026-10-05", "to": "2026-10-25"}
    ).json()
    return [o["date"] for o in occurrences if o["event_id"] == res.json()["id"]]


def test_business_day_shift_avoids_my_day_off_regardless_of_visibility(client) -> None:
    layers = _layers(client)
    client.post(f"/api/calendars/{layers['NATIONAL_HOLIDAY']['id']}/days-off/japan", json={"year": 2026})
    client.post(f"/api/calendars/{layers['PERSONAL']['id']}/days-off", json={"date": "2026-10-13"})
    # 層を全部隠しても計算は変わらない
    events_only = [c["id"] for c in client.get("/api/calendars").json() if c["kind"] == "EVENTS"]
    client.put("/api/calendars/visibility", json={"visible_calendar_ids": events_only})

    assert _weekly_monday_dates(client) == ["2026-10-05", "2026-10-14", "2026-10-19"]
