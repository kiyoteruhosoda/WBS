"""「今日」の画面の「まだ予定を取っていないタスク」の選び方（task #160 / ADR-0015）。"""

from __future__ import annotations

from datetime import date

from src.application.use_cases.today_use_cases import (
    lacks_schedule,
    needs_time_today,
    pick_tasks_to_schedule,
)

TODAY = date(2026, 9, 10)


def _task(**fields) -> dict:
    base = {
        "id": 1,
        "status": "TODO",
        "due_date": None,
        "start_date": None,
        "priority_score": 0,
        "remaining_hours": 1.0,
        "scheduled_hours": 0.0,
        "unscheduled_hours": 1.0,
    }
    return {**base, **fields}


def test_due_until_tomorrow_started_or_doing_is_for_today() -> None:
    assert needs_time_today(_task(due_date=date(2026, 9, 1)), TODAY)
    assert needs_time_today(_task(due_date=TODAY), TODAY)
    assert needs_time_today(_task(due_date=date(2026, 9, 11)), TODAY)
    assert not needs_time_today(_task(due_date=date(2026, 9, 12)), TODAY)
    assert needs_time_today(_task(start_date=TODAY), TODAY)
    assert not needs_time_today(_task(start_date=date(2026, 9, 11)), TODAY)
    assert needs_time_today(_task(status="DOING"), TODAY)
    assert not needs_time_today(_task(), TODAY)


def test_waiting_done_and_cancelled_are_not_for_today() -> None:
    for status in ("WAITING", "DONE", "CANCELLED"):
        assert not needs_time_today(_task(status=status, due_date=TODAY), TODAY)


def test_lacks_schedule() -> None:
    assert lacks_schedule(_task(unscheduled_hours=0.5))
    assert not lacks_schedule(_task(unscheduled_hours=0.0))
    # 残が決まらない: 予定が 1 つも無ければ数える（期限の近いタスクを画面から消さない）
    assert lacks_schedule(_task(remaining_hours=None, unscheduled_hours=None, scheduled_hours=0.0))
    assert not lacks_schedule(
        _task(remaining_hours=None, unscheduled_hours=None, scheduled_hours=1.0)
    )
    # 予定を見ない応答（scheduled_hours も null）でも消さない
    assert lacks_schedule(_task(remaining_hours=None, unscheduled_hours=None, scheduled_hours=None))


def test_order_is_score_then_due_then_id() -> None:
    tasks = [
        _task(id=1, status="DOING"),
        _task(id=2, due_date=date(2026, 9, 11)),
        _task(id=3, due_date=TODAY),
        _task(id=4, due_date=TODAY, priority_score=500),
        _task(id=5, due_date=TODAY, unscheduled_hours=0.0),
        _task(id=6, due_date=date(2026, 9, 30)),
    ]
    assert [t["id"] for t in pick_tasks_to_schedule(tasks, TODAY)] == [4, 3, 2, 1]
