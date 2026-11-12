"""API for visualizing actuals (task #162 / ADR-0017; schedules and time tracking were removed in task #543 / ADR-0070).

- Per period: confirmed actuals (half month, week, month; boundaries use the user's dates)
- Other users' actuals are not counted
- Per task: reasons to review remaining hours (over estimate, remaining 0, remaining undetermined, not revised after a Tracker close arrived)
- Gantt actuals bar, per-category rollup, CSV export
"""

from __future__ import annotations

import csv
import io
from collections.abc import Iterator
from datetime import date, datetime
from decimal import Decimal

import pytest

from src.infrastructure.database.models import TaskModel, UserModel, WorkLogModel
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


@pytest.fixture
def stranger(db) -> dict:
    """Another user, with their task and actuals (placed on the same dates)."""
    other = UserModel(email="other-actuals@example.com", display_name="他人", timezone="Asia/Tokyo")
    db.add(other)
    db.flush()
    task = TaskModel(user_id=other.id, title="他人のタスク")
    db.add(task)
    db.flush()
    db.add(
        WorkLogModel(
            user_id=other.id, task_id=task.id, work_date=date(2026, 9, 2), hours=Decimal("4")
        )
    )
    db.commit()
    return {"user_id": other.id, "task_id": task.id}


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _work_log(client, task_id: int, work_date: str, hours: float) -> None:
    res = client.post(
        "/api/work-logs", json={"task_id": task_id, "work_date": work_date, "hours": hours}
    )
    assert res.status_code == 201, res.text


def _get(client, path: str, **params) -> dict:
    res = client.get(path, params=params)
    assert res.status_code == 200, res.text
    return res.json()


# ── Per period ──────────────────────────────────────────────────────────


def test_periods_sum_confirmed_work_per_half_month(client, stranger) -> None:
    design = _task(client, "設計")
    _work_log(client, design["id"], "2026-09-15", 1)
    _work_log(client, design["id"], "2026-09-16", 1.5)

    body = _get(
        client, "/api/actuals/periods", unit="closing", **{"from": "2026-09-01", "to": "2026-09-30"}
    )

    assert body["unit"] == "closing"
    assert body["time_zone"] == "Asia/Tokyo"
    assert body["periods"] == [
        {"first_day": "2026-09-01", "last_day": "2026-09-15", "confirmed_seconds": 3600},
        {"first_day": "2026-09-16", "last_day": "2026-09-30", "confirmed_seconds": 5400},
    ]


def test_week_and_month_periods(client) -> None:
    task = _task(client, "実装")
    _work_log(client, task["id"], "2026-09-13", 0.5)  # Sunday
    _work_log(client, task["id"], "2026-09-14", 0.5)  # Monday
    _work_log(client, task["id"], "2026-09-01", 1)

    weeks = _get(
        client, "/api/actuals/periods", unit="week", **{"from": "2026-09-07", "to": "2026-09-14"}
    )
    assert [(p["first_day"], p["confirmed_seconds"]) for p in weeks["periods"]] == [
        ("2026-09-07", 1800),
        ("2026-09-14", 1800),
    ]

    months = _get(
        client, "/api/actuals/periods", unit="month", **{"from": "2026-08-15", "to": "2026-09-01"}
    )
    assert [(p["first_day"], p["last_day"], p["confirmed_seconds"]) for p in months["periods"]] == [
        ("2026-08-01", "2026-08-31", 0),
        ("2026-09-01", "2026-09-30", 3600 + 1800 + 1800),
    ]


def test_someone_elses_time_is_not_counted(client, stranger) -> None:
    body = _get(
        client, "/api/actuals/periods", unit="closing", **{"from": "2026-09-01", "to": "2026-09-15"}
    )
    (period,) = body["periods"]
    assert period["confirmed_seconds"] == 0

    breakdown = _get(client, "/api/actuals/breakdown", **{"from": "2026-09-01", "to": "2026-09-15"})
    assert breakdown["groups"] == []

    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-01", "to": "2026-09-15"})
    assert res.status_code == 200
    assert len(list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))) == 1  # header only

    assert _get(client, "/api/actuals/gantt") == []
    assert stranger["task_id"] not in [
        r["task"]["id"] for r in _get(client, "/api/actuals/tasks")["rows"]
    ]


def test_a_range_ending_before_it_starts_is_rejected(client) -> None:
    res = client.get("/api/actuals/periods", params={"from": "2026-09-10", "to": "2026-09-01"})
    assert res.status_code == 422
    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-10", "to": "2026-09-01"})
    assert res.status_code == 422


def test_periods_default_to_the_recent_six(client) -> None:
    body = _get(client, "/api/actuals/periods", unit="month")
    assert len(body["periods"]) == 6


# ── Per task, review remaining ──────────────────────────────────────────


def _rows(client, **params) -> dict[str, dict]:
    body = _get(client, "/api/actuals/tasks", **params)
    return {r["task"]["title"]: r for r in body["rows"]}


def test_task_rows_carry_estimate_actual_remaining_and_review_reasons(client) -> None:
    over = _task(client, "超過", estimated_hours=2)
    _work_log(client, over["id"], "2026-09-03", 3)
    unknown = _task(client, "見積なし")
    _work_log(client, unknown["id"], "2026-09-04", 1)
    zero = _task(client, "残ゼロ", estimated_hours=5, remaining_hours=0)
    _task(client, "順調", estimated_hours=10)
    done = _task(client, "完了", estimated_hours=1, status="DONE")
    _work_log(client, done["id"], "2026-09-05", 2)

    rows = _rows(client)

    assert rows["超過"]["review_reasons"] == ["over_estimate"]
    assert rows["超過"]["task"]["estimated_hours"] == 2
    assert rows["超過"]["task"]["actual_hours"] == 3
    assert rows["超過"]["task"]["remaining_hours"] == 0
    assert rows["超過"]["actual_first_date"] == "2026-09-03"
    assert rows["超過"]["actual_last_date"] == "2026-09-03"
    assert rows["見積なし"]["review_reasons"] == ["unknown_remaining"]
    assert rows["残ゼロ"]["review_reasons"] == ["no_remaining"]
    assert rows["順調"]["review_reasons"] == []
    assert rows["順調"]["actual_first_date"] is None
    assert rows["完了"]["review_reasons"] == []
    assert zero["id"] in [
        r["task"]["id"] for r in _get(client, "/api/actuals/tasks", review_only=True)["rows"]
    ]
    assert set(_rows(client, review_only=True)) == {"超過", "見積なし", "残ゼロ"}

    # Entering remaining hours on the spot removes it
    res = client.patch(f"/api/tasks/{over['id']}", json={"remaining_hours": 1.5})
    assert res.status_code == 200, res.text
    assert "超過" not in _rows(client, review_only=True)


def _tracker_log(db, task_id: int, first_day: date, work_date: date, seconds: int, at: datetime) -> None:
    """Actuals delivered from Tracker's close (ADR-0056; ``at`` is the moment it arrived)."""
    db.add(
        WorkLogModel(
            user_id=1, task_id=task_id, work_date=work_date, hours=Decimal(seconds) / 3600,
            source="tracker", duration_seconds=seconds, tracker_first_day=first_day,
            created_at=at, updated_at=at,
        )
    )


def test_a_remaining_left_untouched_after_trackers_closing_is_asked_again(client, db) -> None:
    task = _task(client, "設計", estimated_hours=8, remaining_hours=6)
    untouched = _task(client, "手付かず", estimated_hours=8, remaining_hours=6)
    db.query(TaskModel).update({TaskModel.updated_at: datetime(2026, 9, 1)})
    # An earlier period and the latest period (this one is the "latest close")
    _tracker_log(db, task["id"], date(2026, 8, 16), date(2026, 8, 20), 1800, datetime(2026, 9, 1, 1))
    _tracker_log(db, task["id"], date(2026, 9, 1), date(2026, 9, 2), 3600, datetime(2026, 9, 16, 1))
    _tracker_log(db, task["id"], date(2026, 9, 1), date(2026, 9, 3), 3600, datetime(2026, 9, 16, 2))
    db.commit()

    body = _get(client, "/api/actuals/tasks")
    assert body["latest_closed_period"] == {
        "first_day": "2026-09-01", "last_day": "2026-09-03", "closed_at": "2026-09-16T02:00:00Z",
    }
    rows = {r["task"]["title"]: r for r in body["rows"]}
    assert rows["設計"]["review_reasons"] == ["stale_remaining"]
    assert rows["設計"]["latest_closed_hours"] == 2
    # Tasks that got no actuals from the close are not asked about
    assert rows["手付かず"]["review_reasons"] == []
    assert untouched["id"] == rows["手付かず"]["task"]["id"]

    res = client.patch(f"/api/tasks/{task['id']}", json={"remaining_hours": 4})
    assert res.status_code == 200, res.text
    assert _rows(client)["設計"]["review_reasons"] == []


def test_without_a_closing_from_tracker_there_is_no_latest_period(client) -> None:
    task = _task(client, "設計", estimated_hours=8, remaining_hours=6)
    _work_log(client, task["id"], "2026-09-02", 2)
    body = _get(client, "/api/actuals/tasks")
    assert body["latest_closed_period"] is None
    assert body["rows"][0]["latest_closed_hours"] == 0


def test_parent_tasks_are_not_asked_for_a_remaining(client) -> None:
    parent = _task(client, "親")
    child = _task(client, "子", estimated_hours=1, parent_task_id=parent["id"])
    _work_log(client, parent["id"], "2026-09-03", 2)
    _work_log(client, child["id"], "2026-09-03", 2)

    rows = _rows(client)
    assert rows["親"]["review_reasons"] == []
    assert rows["子"]["review_reasons"] == ["over_estimate"]


# ── Gantt, rollup, export ───────────────────────────────────────────────


def test_gantt_spans_cover_all_logs_and_days_only_the_asked_range(client) -> None:
    task = _task(client, "設計")
    _work_log(client, task["id"], "2026-09-03", 1)
    _work_log(client, task["id"], "2026-09-10", 2)
    _work_log(client, task["id"], "2026-09-10", 0.5)

    (span,) = _get(client, "/api/actuals/gantt", **{"from": "2026-09-05", "to": "2026-09-30"})

    assert span["task_id"] == task["id"]
    assert (span["first_date"], span["last_date"]) == ("2026-09-03", "2026-09-10")
    assert span["days"] == [{"date": "2026-09-10", "seconds": 9000}]


def test_breakdown_stacks_by_category(client) -> None:
    work = client.post("/api/categories", json={"name": "仕事", "color": "#0017C1"}).json()
    in_work = _task(client, "設計", category_id=work["id"])
    loose = _task(client, "雑務")
    _work_log(client, in_work["id"], "2026-09-02", 1)
    _work_log(client, loose["id"], "2026-09-02", 0.5)
    _work_log(client, loose["id"], "2026-09-16", 0.25)

    body = _get(
        client,
        "/api/actuals/breakdown",
        unit="closing",
        group_by="category",
        **{"from": "2026-09-01", "to": "2026-09-30"},
    )

    assert body["groups"] == [
        {"key": f"category:{work['id']}", "name": "仕事", "color": "#0017C1"},
        {"key": "none", "name": None, "color": None},
    ]
    assert [p["seconds_by_group"] for p in body["periods"]] == [
        {f"category:{work['id']}": 3600, "none": 1800},
        {"none": 900},
    ]


def test_breakdown_by_milestone_uses_confirmed_work_logs(client) -> None:
    release = client.post("/api/milestones", json={"name": "リリース"}).json()
    task = _task(client, "設計", milestone_id=release["id"])
    _work_log(client, task["id"], "2026-09-03", 2)

    body = _get(
        client,
        "/api/actuals/breakdown",
        group_by="milestone",
        **{"from": "2026-09-01", "to": "2026-09-15"},
    )

    assert "source" not in body
    assert body["groups"] == [
        {"key": f"milestone:{release['id']}", "name": "リリース", "color": None}
    ]
    assert body["periods"][0]["seconds_by_group"] == {f"milestone:{release['id']}": 7200}


def test_export_writes_period_day_task_and_hours(client) -> None:
    work = client.post("/api/categories", json={"name": "仕事"}).json()
    task = _task(client, "設計, 第 1 版", category_id=work["id"])
    _work_log(client, task["id"], "2026-09-15", 1.25)
    _work_log(client, task["id"], "2026-09-16", 0.5)

    res = client.get("/api/actuals/export.csv", params={"from": "2026-09-01", "to": "2026-09-30"})

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment" in res.headers["content-disposition"]
    assert res.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(res.text.lstrip("﻿"))))
    assert rows[0] == [
        "period_start",
        "period_end",
        "date",
        "task_id",
        "task",
        "category",
        "milestone",
        "hours",
        "seconds",
    ]
    assert rows[1:] == [
        [
            "2026-09-01",
            "2026-09-15",
            "2026-09-15",
            str(task["id"]),
            "設計, 第 1 版",
            "仕事",
            "",
            "1.25",
            "4500",
        ],
        [
            "2026-09-16",
            "2026-09-30",
            "2026-09-16",
            str(task["id"]),
            "設計, 第 1 版",
            "仕事",
            "",
            "0.50",
            "1800",
        ],
    ]
