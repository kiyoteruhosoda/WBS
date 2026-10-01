"""タスクの「予定済みの時間」（task #159、ADR-0014）。

- 今日（利用者の日付）以降に始まる、そのタスクに結ばれた予定の回の長さを足す
- 昨日までの回・終日の回・タスクに結ばれていない回は数えない。今日の回は過ぎていても数える
- 繰り返しは回ごとに数える（移した回は移した先で）
- 他人の予定は、たとえ自分のタスクの id を持っていても数えない
- まだ取っていない分 = 残 − 予定済み（0 未満は 0）

「今」は 2026-10-05 00:00 UTC（東京の月曜 9:00）に止める。既定の利用者は Asia/Tokyo。
"""

from __future__ import annotations

from datetime import datetime

import pytest

from src.domain.entities.calendar_event import CalendarEvent
from src.domain.value_objects.event_schedule import SingleEventSchedule
from src.domain.value_objects.time_zone import TimeZoneId
from src.infrastructure.database.models import UserModel
from src.infrastructure.repositories.calendar_event_repository import (
    SqlAlchemyCalendarEventRepository,
)
from src.presentation.api.dependencies import get_db

_MONDAY_9AM_IN_TOKYO = datetime(2026, 10, 5, 0, 0)  # naive な UTC（保存値と同じ形）
WEEKLY_MON_WED_UNTIL_14TH = {
    "type": "WEEKLY",
    "interval": 1,
    "end_date": "2026-10-14",
    "weekly": {"weekdays": ["MO", "WE"]},
}


@pytest.fixture
def frozen_now(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("src.application.user_clock.utcnow", lambda: _MONDAY_9AM_IN_TOKYO)


def _task(client, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": "設計書", **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _event(client, **fields) -> dict:
    body = {"title": "作業", "start": "2026-10-06T00:00:00Z", "duration_minutes": 60, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _get(client, task_id: int) -> dict:
    res = client.get(f"/api/tasks/{task_id}")
    assert res.status_code == 200, res.text
    return res.json()


def _listed(client, task_id: int) -> dict:
    res = client.get("/api/tasks")
    assert res.status_code == 200, res.text
    [found] = [t for t in res.json() if t["id"] == task_id]
    return found


def test_a_task_without_events_has_nothing_scheduled(client, frozen_now) -> None:
    task = _task(client, estimated_hours=10)
    assert task["scheduled_hours"] == 0.0
    assert task["unscheduled_hours"] == 10.0


def test_counts_todays_and_future_occurrences_linked_to_the_task(client, frozen_now) -> None:
    task = _task(client, estimated_hours=10)
    other_task = _task(client, title="別のタスク", estimated_hours=3)
    tid = task["id"]

    _event(
        client, task_id=tid, start="2026-10-04T00:00:00Z", duration_minutes=120
    )  # 昨日: 数えない
    _event(
        client, task_id=tid, start="2026-10-04T15:00:00Z", duration_minutes=30
    )  # 今日 0:00（過ぎた）: 数える
    _event(client, task_id=tid, start="2026-10-06T01:00:00Z", duration_minutes=90)  # 明日: 数える
    _event(
        client, task_id=tid, start="2026-10-05T15:00:00Z", duration_minutes=24 * 60
    )  # 終日: 数えない
    _event(client, start="2026-10-06T03:00:00Z", duration_minutes=60)  # タスクなし: 数えない
    _event(client, task_id=other_task["id"], start="2026-10-07T00:00:00Z", duration_minutes=45)
    # 月・水の 9:00 から 1 時間、10/14 まで → 10/5・10/7・10/12・10/14 の 4 回
    _event(client, task_id=tid, start="2026-10-05T00:00:00Z", recurrence=WEEKLY_MON_WED_UNTIL_14TH)

    expected = 0.5 + 1.5 + 4.0
    for seen in (_get(client, tid), _listed(client, tid)):
        assert seen["scheduled_hours"] == expected
        assert seen["unscheduled_hours"] == 10.0 - expected
    assert _get(client, other_task["id"])["scheduled_hours"] == 0.75


def test_a_moved_occurrence_counts_where_it_was_moved(client, frozen_now) -> None:
    task = _task(client, estimated_hours=10)
    series = _event(
        client,
        task_id=task["id"],
        start="2026-10-05T00:00:00Z",
        recurrence=WEEKLY_MON_WED_UNTIL_14TH,
    )
    # 10/7 の回を昨日へ移す → 残りは 3 回
    res = client.post(
        f"/api/calendar/events/{series['id']}/occurrences/move",
        json={
            "occurrence": {"date": "2026-10-07", "start_time": "09:00"},
            "start": "2026-10-04T00:00:00Z",
            "duration_minutes": 60,
            "expected_version": series["version"],
        },
    )
    assert res.status_code == 200, res.text
    assert _get(client, task["id"])["scheduled_hours"] == 3.0


def test_unscheduled_never_goes_below_zero_and_needs_a_remaining(client, frozen_now) -> None:
    short = _task(client, estimated_hours=1)
    _event(client, task_id=short["id"], duration_minutes=150)
    seen = _get(client, short["id"])
    assert seen["scheduled_hours"] == 2.5
    assert seen["unscheduled_hours"] == 0.0

    no_estimate = _task(client, title="見積なし")
    _event(client, task_id=no_estimate["id"], duration_minutes=60)
    seen = _get(client, no_estimate["id"])
    assert seen["scheduled_hours"] == 1.0
    assert seen["unscheduled_hours"] is None


def test_someone_elses_event_pointing_at_my_task_is_not_counted(client, frozen_now) -> None:
    task = _task(client, estimated_hours=4)
    _event(client, task_id=task["id"], duration_minutes=60)

    # API からは他人のタスクに結べない（404）ので、表へ直に入れる。
    session = next(get_db())
    try:
        other = UserModel(email="other-scheduler@example.com", display_name="他人")
        session.add(other)
        session.flush()
        SqlAlchemyCalendarEventRepository(session).save(
            CalendarEvent.create_single(
                user_id=other.id,
                title="他人の予定",
                time_zone=TimeZoneId("Asia/Tokyo"),
                schedule=SingleEventSchedule(datetime(2026, 10, 6, 2, 0), 180),
                created_at=_MONDAY_9AM_IN_TOKYO,
                task_id=task["id"],
            )
        )
        session.commit()
    finally:
        session.close()

    seen = _get(client, task["id"])
    assert seen["scheduled_hours"] == 1.0
    assert seen["unscheduled_hours"] == 3.0


def test_occurrences_beyond_the_horizon_are_not_counted(client, frozen_now) -> None:
    task = _task(client, estimated_hours=4)
    _event(client, task_id=task["id"], start="2027-12-01T00:00:00Z", duration_minutes=60)
    assert _get(client, task["id"])["scheduled_hours"] == 0.0
