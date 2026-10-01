"""営業日カレンダーと祝日の API（task #156 第 2 段、ADR-0009）。"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other-calendar@example.com"


@pytest.fixture
def as_other(client) -> Iterator:
    session = next(get_db())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="他人")
        session.add(user)
        session.flush()
        other_id = user.id
        session.commit()
    finally:
        session.close()

    def switch(on: bool) -> None:
        if on:
            client.app.dependency_overrides[get_current_user] = lambda: AuthenticatedUserDTO(
                user_id=other_id, email=OTHER_EMAIL, display_name="他人",
                timezone="Asia/Tokyo", language="ja",
            )
        else:
            client.app.dependency_overrides.pop(get_current_user, None)

    yield switch
    switch(False)


def _calendar(client, **fields) -> dict:
    res = client.post("/api/business-calendars", json={"name": "日本", **fields})
    assert res.status_code == 201, res.text
    return res.json()


def test_create_defaults_to_weekdays_and_my_time_zone(client) -> None:
    created = _calendar(client)
    assert created["workdays"] == ["MO", "TU", "WE", "TH", "FR"]
    assert created["time_zone"] == "Asia/Tokyo"
    assert created["holidays"] == []
    assert created["is_enabled"] is True
    assert created["created_at"].endswith("Z")
    assert [c["id"] for c in client.get("/api/business-calendars").json()] == [created["id"]]


def test_update_keeps_holidays(client) -> None:
    created = _calendar(client)
    url = f"/api/business-calendars/{created['id']}"
    client.post(f"{url}/holidays", json={"date": "2026-11-03", "name": "文化の日"})
    res = client.put(
        url, json={"name": "土曜も営業", "workdays": ["SA", "MO", "TU", "WE", "TH", "FR"],
                   "shift_on_holidays_only": True, "is_enabled": False},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["name"] == "土曜も営業"
    assert body["workdays"] == ["MO", "TU", "WE", "TH", "FR", "SA"]
    assert body["shift_on_holidays_only"] is True
    assert body["holidays"] == [{"date": "2026-11-03", "name": "文化の日"}]


def test_import_japanese_holidays_by_year(client) -> None:
    created = _calendar(client)
    url = f"/api/business-calendars/{created['id']}/holidays"
    res = client.post(f"{url}/japan", json={"year": 2026})
    assert res.status_code == 200, res.text
    holidays = res.json()["holidays"]
    assert len(holidays) == 18
    assert {"date": "2026-09-22", "name": "国民の休日"} in holidays

    # 2 度入れても増えない
    again = client.post(f"{url}/japan", json={"year": 2026}).json()["holidays"]
    assert again == holidays
    assert client.post(f"{url}/japan", json={"year": 1999}).status_code == 422


def test_bulk_add_and_remove_holidays(client) -> None:
    created = _calendar(client)
    url = f"/api/business-calendars/{created['id']}/holidays"
    res = client.post(
        f"{url}/bulk",
        json={"holidays": [
            {"date": "2026-12-29", "name": "年末休暇"},
            {"date": "2026-12-30", "name": "年末休暇"},
            {"date": "2026-12-29", "name": "重複"},
        ]},
    )
    assert res.status_code == 200, res.text
    assert res.json()["holidays"] == [
        {"date": "2026-12-29", "name": "年末休暇"},
        {"date": "2026-12-30", "name": "年末休暇"},
    ]
    res = client.delete(f"{url}/2026-12-29")
    assert res.status_code == 200
    assert [h["date"] for h in res.json()["holidays"]] == ["2026-12-30"]


def test_holidays_for_the_calendar_view_come_from_enabled_calendars(client) -> None:
    enabled = _calendar(client, name="有効")
    disabled = _calendar(client, name="無効", is_enabled=False)
    client.post(f"/api/business-calendars/{enabled['id']}/holidays",
                json={"date": "2026-10-12", "name": "スポーツの日"})
    client.post(f"/api/business-calendars/{disabled['id']}/holidays",
                json={"date": "2026-10-13", "name": "見せない"})
    res = client.get("/api/calendar/holidays", params={"from": "2026-10-01", "to": "2026-10-31"})
    assert res.status_code == 200
    assert res.json() == [{"date": "2026-10-12", "name": "スポーツの日"}]


def test_delete_calendar(client) -> None:
    created = _calendar(client)
    assert client.delete(f"/api/business-calendars/{created['id']}").status_code == 204
    assert client.get(f"/api/business-calendars/{created['id']}").status_code == 404


def test_someone_elses_calendar_is_out_of_reach(client, as_other) -> None:
    as_other(True)
    theirs = _calendar(client, name="他人の暦")
    client.post(f"/api/business-calendars/{theirs['id']}/holidays",
                json={"date": "2026-10-12", "name": "他人の祝日"})
    as_other(False)

    url = f"/api/business-calendars/{theirs['id']}"
    assert client.get("/api/business-calendars").json() == []
    assert client.get(url).status_code == 404
    assert client.put(url, json={"name": "x", "workdays": ["MO"]}).status_code == 404
    assert client.post(f"{url}/holidays", json={"date": "2026-10-13"}).status_code == 404
    assert client.post(f"{url}/holidays/bulk", json={"holidays": []}).status_code == 404
    assert client.post(f"{url}/holidays/japan", json={"year": 2026}).status_code == 404
    assert client.delete(f"{url}/holidays/2026-10-12").status_code == 404
    assert client.delete(url).status_code == 404
    assert client.get(
        "/api/calendar/holidays", params={"from": "2026-10-01", "to": "2026-10-31"}
    ).json() == []

    as_other(True)
    still = client.get(url).json()
    assert still["name"] == "他人の暦"
    assert still["holidays"] == [{"date": "2026-10-12", "name": "他人の祝日"}]
