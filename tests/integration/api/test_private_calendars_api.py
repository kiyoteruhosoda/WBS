"""予定のカレンダーの「仕事 / プライベート」（task #191、ADR-0033）。

- カレンダーは既定で仕事。作るとき・直すときにプライベートにできる（既定のカレンダー・休みの層はできない）
- プライベートのカレンダーにはタスクを結んだ予定を入れられない（422）。結んだ予定があればプライベートにできない（409）
- プライベートの予定は回の一覧に ``is_private`` で出る（「今日」・カレンダーには出す）
- 実績の「予定した時間」・締めの予定の列と抜けの指摘には数えない

期間は過去（2026-09-01〜15、利用者は Asia/Tokyo）。
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_db


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


def _calendar(client, name: str, scope: str | None = None) -> dict:
    body = {"name": name, "color_key": "BASIL", **({"scope": scope} if scope else {})}
    res = client.post("/api/calendars", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _event(client, start: str, minutes: int, **fields):
    body = {"title": "予定", "start": start, "duration_minutes": minutes, **fields}
    return client.post("/api/calendar/events", json=body)


def test_calendars_are_work_by_default_and_can_be_private(client) -> None:
    listed = client.get("/api/calendars").json()
    assert {c["scope"] for c in listed} == {"WORK"}
    home = _calendar(client, "家", "PRIVATE")
    assert home["scope"] == "PRIVATE"
    work = _calendar(client, "仕事")
    assert work["scope"] == "WORK"
    res = client.put(
        f"/api/calendars/{work['id']}", json={"name": "仕事", "color_key": "BASIL", "scope": "PRIVATE"}
    )
    assert res.status_code == 200, res.text
    assert res.json()["scope"] == "PRIVATE"
    # scope を省けば今のまま
    res = client.put(f"/api/calendars/{work['id']}", json={"name": "仕事2", "color_key": "BASIL"})
    assert res.json()["scope"] == "PRIVATE"


def test_default_calendar_and_layers_stay_work(client) -> None:
    listed = client.get("/api/calendars").json()
    default = next(c for c in listed if c["is_default"])
    layer = next(c for c in listed if c["kind"] != "EVENTS")
    for calendar in (default, layer):
        res = client.put(
            f"/api/calendars/{calendar['id']}",
            json={"name": calendar["name"], "color_key": calendar["color_key"], "scope": "PRIVATE"},
        )
        assert res.status_code == 422, res.text


def test_private_calendar_refuses_task_events(client) -> None:
    home = _calendar(client, "家", "PRIVATE")
    task_id = _task(client, "設計")
    res = _event(client, "2026-09-03T01:00:00Z", 60, task_id=task_id, calendar_id=home["id"])
    assert res.status_code == 422, res.text
    assert _event(client, "2026-09-03T01:00:00Z", 60, calendar_id=home["id"]).status_code == 201

    work = _calendar(client, "仕事")
    assert _event(
        client, "2026-09-03T01:00:00Z", 60, task_id=task_id, calendar_id=work["id"]
    ).status_code == 201
    res = client.put(
        f"/api/calendars/{work['id']}", json={"name": "仕事", "color_key": "BASIL", "scope": "PRIVATE"}
    )
    assert res.status_code == 409, res.text


def test_private_events_are_shown_but_not_planned_or_closed(client) -> None:
    home = _calendar(client, "家", "PRIVATE")
    task_id = _task(client, "設計")
    # 仕事: 9/3 10:00〜11:00（タスク）。プライベート: 9/4 10:00〜12:00
    assert _event(client, "2026-09-03T01:00:00Z", 60, task_id=task_id).status_code == 201
    assert _event(
        client, "2026-09-04T01:00:00Z", 120, title="通院", calendar_id=home["id"]
    ).status_code == 201

    occurrences = client.get(
        "/api/calendar/occurrences", params={"from": "2026-09-03", "to": "2026-09-04"}
    ).json()
    assert sorted((o["date"], o["is_private"]) for o in occurrences) == [
        ("2026-09-03", False), ("2026-09-04", True),
    ]

    periods = client.get(
        "/api/actuals/periods", params={"unit": "closing", "from": "2026-09-01", "to": "2026-09-15"}
    ).json()["periods"]
    assert (periods[0]["planned_task_seconds"], periods[0]["planned_off_task_seconds"]) == (3600, 0)

    board = client.get("/api/closing-periods/2026-09-01").json()
    assert [o["title"] for o in board["occurrences"]] == ["予定"]
    assert [o["title"] for o in board["findings"]["missed_occurrences"]] == ["予定"]
