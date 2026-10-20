"""終わる見込みの日を API で返す（task #555 / ADR-0058）。

タスクの一覧・1 件・ガント・マイルストーンに見込みが載り、残・従事率・休み・比率・依存を直すと
次に読んだときに変わる（保存しない）ことを見る。「今日」は 2026-11-02（月）に固定する。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import date
from unittest.mock import patch

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

TODAY = date(2026, 11, 2)
OTHER_EMAIL = "member@example.com"


@pytest.fixture(autouse=True)
def fixed_today() -> Iterator[None]:
    with patch("src.application.user_clock.UserClock.today", return_value=TODAY):
        yield


def _as_user(user_id: int) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=OTHER_EMAIL, display_name="仲間", timezone="Asia/Tokyo", language="ja",
        )

    return current


@pytest.fixture
def other_id(client) -> int:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        user = UserModel(email=OTHER_EMAIL, display_name="仲間", timezone="Asia/Tokyo")
        session.add(user)
        session.commit()
        return user.id
    finally:
        session.close()


def _project(client) -> dict:
    res = client.post("/api/projects", json={"name": "根"})
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _by_title(client, **params) -> dict[str, dict]:
    res = client.get("/api/tasks", params=params)
    assert res.status_code == 200, res.text
    return {t["title"]: t for t in res.json()}


def test_adr_example_through_the_api(client, other_id) -> None:
    """ADR-0058 の計算の例を、画面と同じ API で入れて読む。"""
    root = _project(client)
    pid = root["id"]
    client.post(f"/api/projects/{pid}/members", json={"user_id": other_id})
    client.put(f"/api/projects/{pid}/members/{SINGLE_USER_ID}/capacity", json={"daily_hours": 8, "engagement_percent": 50})
    client.put(f"/api/projects/{pid}/members/{other_id}/capacity", json={"daily_hours": 8, "engagement_percent": 75})
    client.post(f"/api/projects/{pid}/team-calendar/days-off", json={"day": "2026-11-03", "name": "文化の日"})
    client.post(f"/api/projects/{pid}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-11-05"})
    milestone = client.post("/api/milestones", json={"name": "M", "project_id": pid}).json()

    a1 = _task(client, "A1", project_id=pid, remaining_hours=6, due_date="2026-11-06", milestone_id=milestone["id"])
    _task(client, "A2", project_id=pid, remaining_hours=4, allocation_percent=50)
    _task(client, "A3", project_id=pid, remaining_hours=4, due_date="2026-11-10")
    b1 = _task(
        client, "B1", project_id=pid, remaining_hours=9, due_date="2026-11-06",
        assignee_user_id=other_id, milestone_id=milestone["id"],
    )
    _task(client, "U", project_id=pid, remaining_hours=3, assignee_user_id=None)
    res = client.post(f"/api/tasks/{b1['id']}/dependencies", json={"predecessor_task_id": a1["id"]})
    assert res.status_code in (200, 201), res.text

    tasks = _by_title(client)
    assert (tasks["A1"]["forecast_start"], tasks["A1"]["forecast_finish"]) == ("2026-11-02", "2026-11-06")
    assert tasks["A2"]["forecast_finish"] == "2026-11-04"
    assert tasks["A3"]["forecast_finish"] == "2026-11-09"
    assert tasks["B1"]["forecast_start"] == "2026-11-09"
    assert tasks["B1"]["forecast_finish"] == "2026-11-10"
    assert tasks["B1"]["forecast_overdue_days"] == 4
    assert tasks["U"]["forecast_finish"] is None
    assert tasks["U"]["forecast_gap"] == "no_assignee"

    gantt = {t["title"]: t for t in client.get("/api/gantt").json()}
    assert gantt["B1"]["forecast_finish"] == "2026-11-10"
    assert gantt["B1"]["forecast_overdue_days"] == 4

    milestones = client.get("/api/milestones").json()
    assert milestones[0]["forecast_finish"] == "2026-11-10"
    assert milestones[0]["forecast_unforecast_count"] == 0
    one = client.get(f"/api/milestones/{milestone['id']}").json()
    assert one["forecast_finish"] == "2026-11-10"


def test_editing_the_remaining_changes_the_forecast_at_once(client) -> None:
    task = _task(client, "見積", remaining_hours=8)
    assert task["forecast_finish"] == "2026-11-02"  # 作った応答にも載る
    res = client.put(f"/api/tasks/{task['id']}", json={"remaining_hours": 24})
    assert res.json()["forecast_finish"] == "2026-11-04"
    assert client.get(f"/api/tasks/{task['id']}").json()["forecast_finish"] == "2026-11-04"


def test_done_and_zero_remaining_get_no_forecast(client) -> None:
    task = _task(client, "済み", remaining_hours=0)
    assert task["forecast_finish"] is None
    assert task["forecast_gap"] == "finished"
    unknown = _task(client, "未入力")
    assert unknown["forecast_gap"] == "no_remaining"


def test_uncategorized_task_uses_8_hours_a_day(client) -> None:
    task = _task(client, "未分類", remaining_hours=16)
    assert task["project_id"] is None
    assert task["forecast_finish"] == "2026-11-03"


def test_engagement_and_workdays_are_used(client) -> None:
    pid = _project(client)["id"]
    client.put(f"/api/projects/{pid}/members/{SINGLE_USER_ID}/capacity", json={"daily_hours": 4, "engagement_percent": 100})
    client.put(f"/api/projects/{pid}/team-calendar/workdays", json={"workdays": ["MO", "WE"]})
    task = _task(client, "週 2 日", project_id=pid, remaining_hours=8)
    assert task["forecast_finish"] == "2026-11-04"  # 月 4h・水 4h


def test_a_member_seen_by_another_member_has_the_same_forecast(client, other_id) -> None:
    pid = _project(client)["id"]
    client.post(f"/api/projects/{pid}/members", json={"user_id": other_id})
    _task(client, "共有", project_id=pid, remaining_hours=16)
    client.app.dependency_overrides[get_current_user] = _as_user(other_id)
    try:
        assert _by_title(client)["共有"]["forecast_finish"] == "2026-11-03"
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)
