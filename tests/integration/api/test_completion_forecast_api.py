"""Return the forecast finish date via the API (task #555 / ADR-0058).

Check that the forecast appears on the task list, a single task, the Gantt and milestones, and that fixing remaining hours, allocation, days off, ratios or dependencies
changes it on the next read (it is not stored). "Today" is fixed to 2026-11-02 (Monday).
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
    """Enter and read the ADR-0058 calculation example through the same API as the screen."""
    root = _project(client)
    pid = root["id"]
    client.post(f"/api/projects/{pid}/members", json={"user_id": other_id})
    client.put(f"/api/projects/{pid}/members/{SINGLE_USER_ID}/capacity", json={"daily_hours": 8, "engagement_percent": 50})
    client.put(f"/api/projects/{pid}/members/{other_id}/capacity", json={"daily_hours": 8, "engagement_percent": 75})
    client.post(f"/api/projects/{pid}/calendar/days-off", json={"day": "2026-11-03", "name": "文化の日"})
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
    assert task["forecast_finish"] == "2026-11-02"  # also included in the create response
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
    client.put(f"/api/projects/{pid}/calendar/workdays", json={"workdays": ["MO", "WE"]})
    task = _task(client, "週 2 日", project_id=pid, remaining_hours=8)
    assert task["forecast_finish"] == "2026-11-04"  # Mon 4h, Wed 4h


def test_a_member_seen_by_another_member_has_the_same_forecast(client, other_id) -> None:
    pid = _project(client)["id"]
    client.post(f"/api/projects/{pid}/members", json={"user_id": other_id})
    _task(client, "共有", project_id=pid, remaining_hours=16)
    client.app.dependency_overrides[get_current_user] = _as_user(other_id)
    try:
        assert _by_title(client)["共有"]["forecast_finish"] == "2026-11-03"
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


def test_project_and_person_calendars_move_the_forecast(client) -> None:
    """ADR-0059: a lower project's holiday stops only that project's tasks, and a half day off halves that day."""
    root = _project(client)
    child = client.post("/api/projects", json={"name": "子", "parent_project_id": root["id"]}).json()
    grandchild = client.post("/api/projects", json={"name": "孫", "parent_project_id": child["id"]}).json()
    _task(client, "根の", project_id=root["id"], remaining_hours=16)
    _task(client, "孫の", project_id=grandchild["id"], remaining_hours=8, due_date="2026-11-01")
    # The grandchild's task comes first (earlier deadline): done with 8 hours on Monday. The root's task gets Tue and Wed
    tasks = _by_title(client)
    assert tasks["孫の"]["forecast_finish"] == "2026-11-02"
    assert tasks["根の"]["forecast_finish"] == "2026-11-04"

    # Adding a holiday to the child is inherited by the grandchild, and Monday goes to the root's task
    client.post(f"/api/projects/{child['id']}/calendar/days-off", json={"day": "2026-11-02"})
    tasks = _by_title(client)
    assert tasks["孫の"]["forecast_finish"] == "2026-11-03"
    assert tasks["根の"]["forecast_finish"] == "2026-11-04"  # Mon 8, (Tue to the grandchild), Wed 8

    # The person's half day off (Wed) pushes the root's task back
    res = client.post(
        f"/api/projects/{root['id']}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-11-04", "off_percent": 50}
    )
    assert res.status_code == 200, res.text
    tasks = _by_title(client)
    assert tasks["根の"]["forecast_finish"] == "2026-11-05"


def test_working_hours_and_extra_workdays_move_the_forecast(client) -> None:
    """ADR-0060: overtime, short days, holiday work, and project working days. Today = 11/2 (Mon)."""
    root = _project(client)
    pid = root["id"]
    _task(client, "T", project_id=pid, remaining_hours=40)
    leave = f"/api/projects/{pid}/members/{SINGLE_USER_ID}/leave"
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-06"  # 8 hours × 5, Mon to Fri
    # With 16 hours of overtime on Monday, it finishes on Thursday
    client.post(leave, json={"day": "2026-11-02", "hours": 16})
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-05"
    # Setting Tuesday to 0 hours moves it back to Friday
    client.post(leave, json={"day": "2026-11-03", "hours": 0})
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-06"
    # Increase remaining; with 8 hours of holiday work on Saturday it finishes on Saturday instead of slipping to Monday
    client.put(f"/api/tasks/{_by_title(client)['T']['id']}", json={"remaining_hours": 48})
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-09"
    client.post(leave, json={"day": "2026-11-07", "hours": 8})
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-07"
    # Drop the person's holiday work and make it a project working day instead: still finishes on Saturday
    client.delete(f"{leave}/2026-11-07")
    client.post(f"/api/projects/{pid}/calendar/extra-workdays", json={"day": "2026-11-07"})
    assert _by_title(client)["T"]["forecast_finish"] == "2026-11-07"
