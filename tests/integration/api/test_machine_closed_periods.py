"""Tracker で締めた時間を受け取る（task #540 / ADR-0056）。

確かめるのは、期間ごとの置き換え・取り消しで実績（タスクの ``actual_hours``）が増え・元に戻ることと、
WBS 自身の締めの行を二重に数えないこと。
"""

from __future__ import annotations

from datetime import date

from src.infrastructure.database.models import TaskModel, WorkLogModel
from src.presentation.api.dependencies import get_db
from tests.integration.api.test_auth import ISSUER, sign_in, sso_provider  # noqa: F401
from tests.integration.api.test_machine_assigned_tasks import _as, client  # noqa: F401

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
    assert res.json() == {"stored": 2, "unknown_task_ids": [], "unknown_project_ids": []}
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
    assert res.json() == {"stored": 1, "unknown_task_ids": [987654], "unknown_project_ids": []}


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


# ── プロジェクトだけの時間（task #708 / ADR-0064） ─────────────────────────


def _project(client, name: str, *, parent_id: int | None = None, code: str = "taro-code") -> int:  # noqa: F811
    sign_in(client, code)
    body: dict = {"name": name}
    if parent_id is not None:
        body["parent_project_id"] = parent_id
    project_id = client.post("/api/projects", json=body).json()["id"]
    client.cookies.clear()
    return project_id


def _confirmed(client, **params) -> tuple[int, dict[str, int]]:  # noqa: F811
    """10/16〜10/31 の確定実績の合計と、プロジェクト別の積み上げ（キー → 秒）。"""
    sign_in(client, "taro-code")
    span = {"unit": "closing", "from": "2026-10-16", "to": "2026-10-31", **params}
    (period,) = client.get("/api/actuals/periods", params=span).json()["periods"]
    breakdown = client.get(
        "/api/actuals/breakdown", params={**span, "group_by": "project", "source": "confirmed"}
    ).json()
    client.cookies.clear()
    (row,) = breakdown["periods"]
    return period["confirmed_seconds"], row["seconds_by_group"]


def test_project_only_time_counts_toward_the_project_and_its_parents(client) -> None:  # noqa: F811
    root = _project(client, "案件")
    child = _project(client, "設計", parent_id=root)
    res = _put(client, [
        {"wbs_project_id": child, "work_date": "2026-10-16", "seconds": 3600},
        {"wbs_project_id": child, "work_date": "2026-10-16", "seconds": 1800},
    ])
    assert res.status_code == 200, res.text
    assert res.json() == {"stored": 1, "unknown_task_ids": [], "unknown_project_ids": []}

    total, groups = _confirmed(client)
    assert total == 5400
    assert groups == {f"project:{root}": 5400}  # 最上位では親の枝に積む
    _, under_root = _confirmed(client, project_id=root)
    assert under_root == {f"project:{child}": 5400}  # 親で絞ると子の枝に
    assert _confirmed(client, unclassified="true")[0] == 0  # 未分類には入らない


def test_project_only_time_is_replaced_not_added_and_withdrawn(client) -> None:  # noqa: F811
    project = _project(client, "案件")
    task_id = _task(client, "設計")
    _put(client, [{"wbs_project_id": project, "work_date": "2026-10-16", "seconds": 3600}])
    _put(client, [
        {"wbs_project_id": project, "work_date": "2026-10-16", "seconds": 7200},
        {"wbs_task_id": task_id, "work_date": "2026-10-17", "seconds": 600},
    ])
    assert _confirmed(client)[0] == 7800  # 送り直しは置き換え

    res = client.delete(URL, **_as("tracker"))
    assert res.json() == {"removed": 2}
    assert _confirmed(client)[0] == 0


def test_unknown_and_invisible_projects_are_reported_and_skipped(client) -> None:  # noqa: F811
    mine = _project(client, "案件")
    theirs = _project(client, "よその案件", code="hanako-code")
    res = _put(client, [
        {"wbs_project_id": mine, "work_date": "2026-10-16", "seconds": 60},
        {"wbs_project_id": theirs, "work_date": "2026-10-16", "seconds": 60},
        {"wbs_project_id": 987654, "work_date": "2026-10-16", "seconds": 60},
    ])
    assert res.json() == {"stored": 1, "unknown_task_ids": [], "unknown_project_ids": sorted([theirs, 987654])}


def test_an_entry_needs_exactly_one_of_task_or_project(client) -> None:  # noqa: F811
    project = _project(client, "案件")
    task_id = _task(client, "設計")
    both = {"wbs_task_id": task_id, "wbs_project_id": project, "work_date": "2026-10-16", "seconds": 60}
    assert _put(client, [both]).status_code == 422
    assert _put(client, [{"work_date": "2026-10-16", "seconds": 60}]).status_code == 422


def test_a_project_with_received_time_cannot_be_deleted(client) -> None:  # noqa: F811
    project = _project(client, "案件")
    _put(client, [{"wbs_project_id": project, "work_date": "2026-10-16", "seconds": 60}])
    sign_in(client, "taro-code")
    assert client.delete(f"/api/projects/{project}").status_code == 409
    client.cookies.clear()
    client.delete(URL, **_as("tracker"))
    sign_in(client, "taro-code")
    assert client.delete(f"/api/projects/{project}").status_code in (200, 204)
