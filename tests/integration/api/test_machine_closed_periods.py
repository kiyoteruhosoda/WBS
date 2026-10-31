"""Tracker で締めた時間を受け取る（task #540 / ADR-0056）。

確かめるのは、期間ごとの置き換え・取り消しで実績（タスクの ``actual_hours``）が増え・元に戻ることと、
WBS 自身の締めの行を二重に数えないこと。
"""

from __future__ import annotations

import sqlite3
from datetime import date

from src.infrastructure.database.models import TaskModel, WorkLogModel
from src.presentation.api.dependencies import get_db
from tests.integration.api.test_auth import ISSUER, sign_in, sso_provider  # noqa: F401
from tests.integration.api.test_machine_assigned_tasks import TRACKER_MACHINE, _as, client  # noqa: F401

URL = "/api/machine/closed-periods/2026-10-16"


def _task(client, title: str) -> int:  # noqa: F811
    sign_in(client, "taro-code")
    task_id = client.post("/api/tasks", json={"title": title}).json()["id"]
    client.cookies.clear()
    return task_id


def _actual(client, task_id: int) -> float:  # noqa: F811
    sign_in(client, "taro-code")
    hours = client.get(f"/api/tasks/{task_id}").json()["actual_hours"]
    client.cookies.clear()
    return hours


def _put(client, entries, *, last_day="2026-10-31", token="tracker"):  # noqa: F811
    kwargs = _as(token)
    return client.put(URL, json={"last_day": last_day, "entries": entries}, **kwargs)


def test_closing_adds_actuals_and_reopening_takes_them_back(client) -> None:  # noqa: F811
    task_id = _task(client, "設計")
    res = _put(client, [
        {"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 3600},
        {"wbs_task_id": task_id, "work_date": "2026-10-17", "seconds": 1800},
    ])
    assert res.status_code == 200, res.text
    assert res.json() == {"stored": 2, "unknown_task_ids": []}
    assert _actual(client, task_id) == 1.5

    # 送り直すと置き換わる（足し込まない）
    _put(client, [{"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 7200}])
    assert _actual(client, task_id) == 2.0

    res = client.delete(URL, **_as("tracker"))
    assert res.status_code == 200, res.text
    assert res.json() == {"removed": 1}
    assert _actual(client, task_id) == 0.0
    # 取り消しは何度送ってもよい
    assert client.delete(URL, **_as("tracker")).json() == {"removed": 0}


def test_unknown_tasks_are_reported_and_skipped(client) -> None:  # noqa: F811
    task_id = _task(client, "設計")
    res = _put(client, [
        {"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 3600},
        {"wbs_task_id": 987654, "work_date": "2026-10-16", "seconds": 3600},
    ])
    assert res.json() == {"stored": 1, "unknown_task_ids": [987654]}


def test_entries_outside_the_period_are_refused(client) -> None:  # noqa: F811
    task_id = _task(client, "設計")
    res = _put(client, [{"wbs_task_id": task_id, "work_date": "2026-11-01", "seconds": 60}])
    assert res.status_code == 422, res.text


def test_wbs_own_closings_in_the_period_are_retired(client) -> None:  # noqa: F811
    task_id = _task(client, "設計")
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        owner = session.get(TaskModel, task_id).user_id
        # Tracker へ移る前に WBS 自身が締めた行（同じ日）
        session.add(WorkLogModel(
            user_id=owner, task_id=task_id, work_date=date(2026, 10, 16), hours=1,
            source="closing", duration_seconds=3600,
        ))
        session.commit()
    finally:
        session.close()
    assert _actual(client, task_id) == 1.0
    _put(client, [{"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 3600}])
    # 二重に数えない（Tracker の値に置き換わる）
    assert _actual(client, task_id) == 1.0


def test_only_the_tracker_machine_may_write(client) -> None:  # noqa: F811
    task_id = _task(client, "設計")
    res = _put(client, [{"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 60}], token="other-machine")
    assert res.status_code == 401


def _operation_logs(database_path) -> list[tuple]:
    query = "SELECT client_id, user_id, operation, detail FROM machine_operation_logs ORDER BY id"
    with sqlite3.connect(database_path) as connection:
        return connection.execute(query).fetchall()


def test_writes_leave_the_client_and_the_operation_in_the_log(client, database_path) -> None:  # noqa: F811
    """どのアプリが・誰の分を・何を、が同じ表で引ける（task #802 / ADR-0068）。"""
    task_id = _task(client, "設計")

    assert _put(client, [{"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 60}]).status_code == 200
    assert client.delete(URL, **_as("tracker")).status_code == 200

    (put, delete) = _operation_logs(database_path)
    assert put[0] == TRACKER_MACHINE
    assert put[2:] == ("PUT /api/machine/closed-periods/{first_day}", "first_day=2026-10-16 stored=1")
    assert delete[0] == TRACKER_MACHINE
    assert delete[2:] == ("DELETE /api/machine/closed-periods/{first_day}", "first_day=2026-10-16 removed=1")
    assert put[1] == delete[1]


def test_refused_writes_and_reads_are_not_in_the_log(client, database_path) -> None:  # noqa: F811
    task_id = _task(client, "設計")

    entry = {"wbs_task_id": task_id, "work_date": "2026-10-16", "seconds": 60}
    assert _put(client, [entry], token="other-machine").status_code == 401
    assert _put(client, [{"wbs_task_id": task_id, "work_date": "2026-11-16", "seconds": 60}]).status_code >= 400
    assert client.get("/api/machine/assigned-tasks", **_as("tracker")).status_code == 200

    assert _operation_logs(database_path) == []
