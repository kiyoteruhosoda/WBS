"""タスクをまとめて別のプロジェクトへ移す（task #187 / ADR-0030）。

- 書くのは枝の根だけ。子孫は根と一緒に移る（ADR-0024 の 4）
- 祖先を一緒に選んでいない子タスクを含めば、何も変えずに 422
- 届かなくなったマイルストーンは外す
- 他人のタスク・プロジェクトは 404（何も変えない）
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.infrastructure.database.models import ProjectModel, TaskModel, UserModel
from src.presentation.api.dependencies import get_db

URL = "/api/tasks/move-to-project"


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


def _project(client, name: str, parent: dict | None = None) -> dict:
    res = client.post(
        "/api/projects", json={"name": name, "parent_project_id": parent["id"] if parent else None}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _project_of(client, task: dict) -> int | None:
    return client.get(f"/api/tasks/{task['id']}").json()["project_id"]


def test_moving_parents_carries_their_subtasks(client) -> None:
    work = _project(client, "仕事")
    home = _project(client, "私用")
    parent = _task(client, "親", project_id=work["id"])
    child = _task(client, "子", parent_task_id=parent["id"])
    grandchild = _task(client, "孫", parent_task_id=child["id"])
    loose = _task(client, "未分類のもの")
    already = _task(client, "もう私用", project_id=home["id"])

    res = client.post(
        URL,
        json={"task_ids": [parent["id"], grandchild["id"], loose["id"], already["id"]], "project_id": home["id"]},
    )

    assert res.status_code == 200, res.text
    body = res.json()
    # 選んでいない子も親と一緒に移る。もともと私用のものは数えない
    assert body["moved_task_ids"] == sorted([parent["id"], child["id"], grandchild["id"], loose["id"]])
    assert body["detached_milestone_task_ids"] == []
    for t in (parent, child, grandchild, loose, already):
        assert _project_of(client, t) == home["id"]
    listed = client.get("/api/tasks", params={"project_id": home["id"]}).json()
    assert {t["project_path"] for t in listed} == {"私用"}


def test_null_moves_to_unclassified(client) -> None:
    work = _project(client, "仕事")
    task = _task(client, "作業", project_id=work["id"])

    res = client.post(URL, json={"task_ids": [task["id"]], "project_id": None})

    assert res.status_code == 200, res.text
    assert _project_of(client, task) is None
    assert [t["title"] for t in client.get("/api/tasks", params={"unclassified": True}).json()] == ["作業"]


def test_a_subtask_selected_without_its_parent_is_refused_and_nothing_changes(client) -> None:
    work = _project(client, "仕事")
    home = _project(client, "私用")
    parent = _task(client, "親", project_id=work["id"])
    child = _task(client, "子", parent_task_id=parent["id"])
    other = _task(client, "別の根", project_id=work["id"])

    res = client.post(URL, json={"task_ids": [other["id"], child["id"]], "project_id": home["id"]})

    assert res.status_code == 422, res.text
    assert str(child["id"]) in res.text
    for t in (parent, child, other):
        assert _project_of(client, t) == work["id"]


def test_milestones_out_of_reach_are_detached(client) -> None:
    work = _project(client, "仕事")
    design = _project(client, "設計", work)
    home = _project(client, "私用")
    milestone = client.post("/api/milestones", json={"name": "リリース", "project_id": work["id"]}).json()
    anywhere = client.post("/api/milestones", json={"name": "どこでも"}).json()
    task = _task(client, "設計書", project_id=design["id"], milestone_id=milestone["id"])
    keeps = _task(client, "雑務", project_id=design["id"], milestone_id=anywhere["id"])

    res = client.post(URL, json={"task_ids": [task["id"], keeps["id"]], "project_id": home["id"]})

    assert res.status_code == 200, res.text
    assert res.json()["detached_milestone_task_ids"] == [task["id"]]
    assert client.get(f"/api/tasks/{task['id']}").json()["milestone_id"] is None
    assert client.get(f"/api/tasks/{keeps['id']}").json()["milestone_id"] == anywhere["id"]


def test_empty_selection_is_422(client) -> None:
    assert client.post(URL, json={"task_ids": [], "project_id": None}).status_code == 422


def test_another_users_task_or_project_is_404_and_nothing_changes(client, db) -> None:
    mine = _project(client, "自分の")
    task = _task(client, "自分のタスク")
    other = UserModel(email="other-move@example.com", display_name="他人", timezone="Asia/Tokyo")
    db.add(other)
    db.flush()
    theirs = ProjectModel(user_id=other.id, name="他人の", status="active", sort_order=0)
    db.add(theirs)
    db.flush()
    their_task = TaskModel(user_id=other.id, title="他人のタスク")
    db.add(their_task)
    db.commit()

    res = client.post(URL, json={"task_ids": [task["id"]], "project_id": theirs.id})
    assert res.status_code == 404, res.text
    res = client.post(URL, json={"task_ids": [task["id"], their_task.id], "project_id": mine["id"]})
    assert res.status_code == 404, res.text
    assert _project_of(client, task) is None
