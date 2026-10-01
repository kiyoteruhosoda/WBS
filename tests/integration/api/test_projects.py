"""プロジェクト（入れ子）とタスク・マイルストーンの所属（task #187 / ADR-0024）。

- 何段でも入れ子にできる。自分・自分の子孫の下へは移せない（409）
- 絞り込みは子孫を含む（タスク・マイルストーン・ガント・実績）
- 子タスクは親タスクと同じプロジェクト。親を移すと子孫も移る
- マイルストーンは、そのプロジェクトと子孫のタスクにだけ付く。届かなくなったら外れる
- 他人のプロジェクトには触れない（404）
- 実績のプロジェクト別は枝ごとに積み上げる
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.infrastructure.database.models import ProjectModel, TaskModel, UserModel
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


def _project(client, name: str, parent: dict | None = None, **fields) -> dict:
    body = {"name": name, "parent_project_id": parent["id"] if parent else None, **fields}
    res = client.post("/api/projects", json=body)
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _titles(client, path: str, **params) -> list[str]:
    res = client.get(path, params=params)
    assert res.status_code == 200, res.text
    return sorted(t.get("title") or t.get("name") for t in res.json())


# ── 木 ──────────────────────────────────────────────────────────────────


def test_projects_nest_to_any_depth_and_list_in_tree_order(client) -> None:
    root = _project(client, "仕事", color="#0017C1")
    child = _project(client, "案件 A", root)
    grandchild = _project(client, "設計", child)
    _project(client, "私用")

    listed = client.get("/api/projects").json()

    assert [p["name"] for p in listed] == ["仕事", "案件 A", "設計", "私用"]
    assert grandchild["path"] == "仕事 / 案件 A / 設計"
    assert grandchild["parent_project_id"] == child["id"]
    assert listed[0]["color"] == "#0017C1"
    assert listed[0]["status"] == "active"


def test_a_project_cannot_be_moved_under_itself_or_its_descendants(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    grandchild = _project(client, "設計", child)

    for target in (root, grandchild):
        res = client.post(f"/api/projects/{root['id']}/move", json={"parent_project_id": target["id"]})
        assert res.status_code == 409, res.text

    # 動かなかった
    assert client.get(f"/api/projects/{root['id']}").json()["parent_project_id"] is None


def test_moving_changes_the_parent_and_the_order_among_siblings(client) -> None:
    a = _project(client, "A")
    b = _project(client, "B")
    c = _project(client, "C")

    # C を先頭へ
    moved = client.post(f"/api/projects/{c['id']}/move", json={"parent_project_id": None, "position": 0})
    assert moved.status_code == 200, moved.text
    assert [p["name"] for p in client.get("/api/projects").json()] == ["C", "A", "B"]

    # B を A の下へ
    res = client.post(f"/api/projects/{b['id']}/move", json={"parent_project_id": a["id"]})
    assert res.status_code == 200
    assert res.json()["path"] == "A / B"
    assert [p["name"] for p in client.get("/api/projects").json()] == ["C", "A", "B"]
    assert client.get(f"/api/projects/{b['id']}").json()["parent_project_id"] == a["id"]


def test_rename_archive_and_restore(client) -> None:
    project = _project(client, "仕事", description="本業")

    res = client.put(f"/api/projects/{project['id']}", json={"name": " 本業 ", "status": "archived"})
    assert res.status_code == 200, res.text
    assert res.json()["name"] == "本業"
    assert res.json()["status"] == "archived"
    assert res.json()["description"] == "本業"

    res = client.put(f"/api/projects/{project['id']}", json={"status": "active", "description": None})
    assert res.json()["status"] == "active"
    assert res.json()["description"] is None

    assert client.put(f"/api/projects/{project['id']}", json={"name": "   "}).status_code == 422
    assert client.put(f"/api/projects/{project['id']}", json={"color": "red"}).status_code == 422


def test_only_an_empty_project_can_be_deleted(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    task = _task(client, "設計", project_id=child["id"])

    assert client.delete(f"/api/projects/{root['id']}").status_code == 409  # 子がある
    assert client.delete(f"/api/projects/{child['id']}").status_code == 409  # タスクがある

    client.put(f"/api/tasks/{task['id']}", json={"project_id": None})
    milestone = client.post("/api/milestones", json={"name": "納品", "project_id": child["id"]}).json()
    assert client.delete(f"/api/projects/{child['id']}").status_code == 409  # マイルストーンがある

    client.delete(f"/api/milestones/{milestone['id']}")
    assert client.delete(f"/api/projects/{child['id']}").status_code == 204
    assert client.delete(f"/api/projects/{root['id']}").status_code == 204
    assert client.get("/api/projects").json() == []


def test_a_deleted_task_does_not_keep_its_project_from_being_deleted(client) -> None:
    project = _project(client, "仕事")
    task = _task(client, "捨てる", project_id=project["id"])
    client.delete(f"/api/tasks/{task['id']}")

    assert client.delete(f"/api/projects/{project['id']}").status_code == 204


# ── タスクの所属 ────────────────────────────────────────────────────────


def test_existing_style_tasks_are_unclassified(client) -> None:
    task = _task(client, "どこにも属さない")

    assert task["project_id"] is None
    assert task["project_path"] is None
    assert _titles(client, "/api/tasks", unclassified=True) == ["どこにも属さない"]


def test_task_list_filtered_by_a_project_includes_its_descendants(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    grandchild = _project(client, "設計", child)
    other = _project(client, "私用")
    _task(client, "全体の会議", project_id=root["id"])
    _task(client, "A の見積", project_id=child["id"])
    deep = _task(client, "画面設計", project_id=grandchild["id"])
    _task(client, "買い物", project_id=other["id"])
    _task(client, "未分類")

    assert _titles(client, "/api/tasks", project_id=root["id"]) == ["A の見積", "全体の会議", "画面設計"]
    assert _titles(client, "/api/tasks", project_id=child["id"]) == ["A の見積", "画面設計"]
    assert _titles(client, "/api/tasks", project_id=grandchild["id"]) == ["画面設計"]
    assert deep["project_path"] == "仕事 / 案件 A / 設計"

    gantt = client.get("/api/gantt", params={"project_id": child["id"]}).json()
    assert sorted(t["title"] for t in gantt) == ["A の見積", "画面設計"]


def test_a_subtask_belongs_to_the_project_of_its_parent(client) -> None:
    work = _project(client, "仕事")
    home = _project(client, "私用")
    parent = _task(client, "親", project_id=work["id"])

    # 省けば親に揃う
    child = _task(client, "子", parent_task_id=parent["id"])
    assert child["project_id"] == work["id"]
    grandchild = _task(client, "孫", parent_task_id=child["id"], project_id=work["id"])
    assert grandchild["project_id"] == work["id"]

    # 子だけ別のプロジェクトにはできない
    res = client.post("/api/tasks", json={"title": "子 2", "parent_task_id": parent["id"], "project_id": home["id"]})
    assert res.status_code == 422
    res = client.put(f"/api/tasks/{child['id']}", json={"project_id": home["id"]})
    assert res.status_code == 422

    # 親を移すと子孫も移る
    res = client.put(f"/api/tasks/{parent['id']}", json={"project_id": home["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] == home["id"]
    for task in (child, grandchild):
        assert client.get(f"/api/tasks/{task['id']}").json()["project_id"] == home["id"]

    # 未分類へ戻すと子孫も未分類
    client.put(f"/api/tasks/{parent['id']}", json={"project_id": None})
    assert client.get(f"/api/tasks/{grandchild['id']}").json()["project_id"] is None


def test_a_subtask_whose_parent_was_deleted_can_still_be_edited(client) -> None:
    work = _project(client, "仕事")
    parent = _task(client, "親", project_id=work["id"])
    child = _task(client, "子", parent_task_id=parent["id"])
    client.delete(f"/api/tasks/{parent['id']}")

    res = client.put(f"/api/tasks/{child['id']}", json={"title": "子（親なし）", "project_id": None})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] is None


def test_changing_the_parent_task_moves_the_branch_into_the_new_parents_project(client) -> None:
    work = _project(client, "仕事")
    home = _project(client, "私用")
    new_parent = _task(client, "新しい親", project_id=home["id"])
    task = _task(client, "動かす", project_id=work["id"])
    sub = _task(client, "その子", parent_task_id=task["id"])

    res = client.put(f"/api/tasks/{task['id']}", json={"parent_task_id": new_parent["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] == home["id"]
    assert client.get(f"/api/tasks/{sub['id']}").json()["project_id"] == home["id"]

    # 自分の子孫を親にはできない
    assert client.put(f"/api/tasks/{new_parent['id']}", json={"parent_task_id": sub["id"]}).status_code == 409


# ── マイルストーン ──────────────────────────────────────────────────────


def test_milestones_belong_to_projects_and_filter_with_descendants(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    for name, project in (("全体の締め", root), ("A の納品", child), ("どこでも", None)):
        res = client.post(
            "/api/milestones", json={"name": name, "project_id": project["id"] if project else None}
        )
        assert res.status_code == 201, res.text

    assert _titles(client, "/api/milestones", project_id=root["id"]) == ["A の納品", "全体の締め"]
    assert _titles(client, "/api/milestones", project_id=child["id"]) == ["A の納品"]
    assert _titles(client, "/api/milestones", unclassified=True) == ["どこでも"]


def test_a_task_takes_milestones_of_its_project_or_ancestors_only(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    sibling = _project(client, "案件 B", root)
    of_root = client.post("/api/milestones", json={"name": "全体", "project_id": root["id"]}).json()
    of_sibling = client.post("/api/milestones", json={"name": "B の納品", "project_id": sibling["id"]}).json()
    anywhere = client.post("/api/milestones", json={"name": "どこでも"}).json()

    task = _task(client, "A の作業", project_id=child["id"], milestone_id=of_root["id"])
    assert task["milestone_id"] == of_root["id"]
    assert _task(client, "A の作業 2", project_id=child["id"], milestone_id=anywhere["id"])["milestone_id"] == anywhere["id"]
    res = client.post("/api/tasks", json={"title": "x", "project_id": child["id"], "milestone_id": of_sibling["id"]})
    assert res.status_code == 422
    assert client.post("/api/tasks", json={"title": "未分類", "milestone_id": of_root["id"]}).status_code == 422

    # null で外せる
    res = client.put(f"/api/tasks/{task['id']}", json={"milestone_id": None})
    assert res.json()["milestone_id"] is None


def test_a_task_moved_out_of_reach_loses_its_milestone(client) -> None:
    root = _project(client, "仕事")
    child = _project(client, "案件 A", root)
    home = _project(client, "私用")
    milestone = client.post("/api/milestones", json={"name": "全体", "project_id": root["id"]}).json()
    anywhere = client.post("/api/milestones", json={"name": "どこでも"}).json()
    task = _task(client, "A の作業", project_id=child["id"], milestone_id=milestone["id"])
    keeps = _task(client, "どこでもの作業", project_id=child["id"], milestone_id=anywhere["id"])

    # タスクを別の枝へ（画面は前のマイルストーンをそのまま送ってくる）
    res = client.put(
        f"/api/tasks/{task['id']}", json={"project_id": home["id"], "milestone_id": milestone["id"]}
    )
    assert res.status_code == 200, res.text
    assert res.json()["milestone_id"] is None

    # プロジェクトを枝の外へ動かすと、元の祖先のマイルストーンから外れる
    client.put(f"/api/tasks/{task['id']}", json={"project_id": child["id"], "milestone_id": milestone["id"]})
    assert client.get(f"/api/tasks/{task['id']}").json()["milestone_id"] == milestone["id"]
    client.post(f"/api/projects/{child['id']}/move", json={"parent_project_id": home["id"]})
    assert client.get(f"/api/tasks/{task['id']}").json()["milestone_id"] is None
    assert client.get(f"/api/tasks/{keeps['id']}").json()["milestone_id"] == anywhere["id"]

    # マイルストーンを別のプロジェクトへ移しても、届かなくなったタスクから外れる
    res = client.put(f"/api/tasks/{keeps['id']}", json={"milestone_id": milestone["id"]})
    assert res.status_code == 422  # 「案件 A」はもう「仕事」の枝の外
    target = _task(client, "全体の作業", project_id=root["id"], milestone_id=milestone["id"])
    client.put(f"/api/milestones/{milestone['id']}", json={"project_id": home["id"]})
    assert client.get(f"/api/tasks/{target['id']}").json()["milestone_id"] is None


# ── 他人 ────────────────────────────────────────────────────────────────


def test_another_users_project_is_not_reachable(client, db) -> None:
    mine = _project(client, "自分の")
    other = UserModel(email="other-projects@example.com", display_name="他人", timezone="Asia/Tokyo")
    db.add(other)
    db.flush()
    theirs = ProjectModel(user_id=other.id, name="他人の", status="active", sort_order=0)
    db.add(theirs)
    db.flush()
    # 他人の行が自分のプロジェクトの下を指していても、子孫として辿らない
    sneaky = ProjectModel(user_id=other.id, name="紛れ込み", parent_project_id=mine["id"], status="active", sort_order=0)
    db.add(sneaky)
    db.flush()
    db.add(TaskModel(user_id=other.id, title="他人のタスク", project_id=sneaky.id))
    db.commit()

    pid = theirs.id
    assert client.get(f"/api/projects/{pid}").status_code == 404
    assert client.put(f"/api/projects/{pid}", json={"name": "改名"}).status_code == 404
    assert client.delete(f"/api/projects/{pid}").status_code == 404
    assert client.post(f"/api/projects/{pid}/move", json={"parent_project_id": None}).status_code == 404
    assert client.post(f"/api/projects/{mine['id']}/move", json={"parent_project_id": pid}).status_code == 404
    assert client.post("/api/projects", json={"name": "子", "parent_project_id": pid}).status_code == 404
    assert client.post("/api/tasks", json={"title": "x", "project_id": pid}).status_code == 404
    assert client.post("/api/milestones", json={"name": "x", "project_id": pid}).status_code == 404
    assert client.get("/api/tasks", params={"project_id": pid}).status_code == 404
    assert client.get("/api/milestones", params={"project_id": pid}).status_code == 404
    assert client.get("/api/actuals/breakdown", params={"project_id": pid}).status_code == 404

    assert [p["name"] for p in client.get("/api/projects").json()] == ["自分の"]
    assert client.get("/api/tasks", params={"project_id": mine["id"]}).json() == []


# ── 実績 ────────────────────────────────────────────────────────────────


def _work_log(client, task_id: int, work_date: str, hours: float) -> None:
    res = client.post("/api/work-logs", json={"task_id": task_id, "work_date": work_date, "hours": hours})
    assert res.status_code == 201, res.text


def test_breakdown_by_project_stacks_each_branch(client) -> None:
    work = _project(client, "仕事", color="#0017C1")
    a = _project(client, "案件 A", work)
    design = _project(client, "設計", a)
    home = _project(client, "私用")
    _work_log(client, _task(client, "会議", project_id=work["id"])["id"], "2026-09-02", 1)
    _work_log(client, _task(client, "見積", project_id=a["id"])["id"], "2026-09-02", 2)
    _work_log(client, _task(client, "画面", project_id=design["id"])["id"], "2026-09-03", 3)
    _work_log(client, _task(client, "買い物", project_id=home["id"])["id"], "2026-09-03", 0.5)
    _work_log(client, _task(client, "未分類")["id"], "2026-09-04", 0.25)
    window = {"from": "2026-09-01", "to": "2026-09-15", "group_by": "project"}

    # 指さなければ最上位ごと（子孫の分を積む）
    top = client.get("/api/actuals/breakdown", params=window).json()
    assert [g["key"] for g in top["groups"]] == [f"project:{work['id']}", f"project:{home['id']}", "none"]
    assert top["groups"][0]["color"] == "#0017C1"
    assert top["periods"][0]["seconds_by_group"] == {
        f"project:{work['id']}": 6 * 3600,
        f"project:{home['id']}": 1800,
        "none": 900,
    }

    # 指せば、その直下の子ごと＋そのプロジェクトに直に付いた分（枝の外は数えない）
    inside = client.get("/api/actuals/breakdown", params={**window, "project_id": work["id"]}).json()
    assert [g["key"] for g in inside["groups"]] == [f"project:{work['id']}", f"project:{a['id']}"]
    assert inside["periods"][0]["seconds_by_group"] == {
        f"project:{work['id']}": 3600,
        f"project:{a['id']}": 5 * 3600,
    }

    # カテゴリ別も、絞ると枝の分だけ
    by_category = client.get(
        "/api/actuals/breakdown", params={**window, "group_by": "category", "project_id": a["id"]}
    ).json()
    assert by_category["periods"][0]["seconds_by_group"] == {"none": 5 * 3600}


def test_actuals_tasks_and_periods_filter_by_project(client) -> None:
    work = _project(client, "仕事")
    a = _project(client, "案件 A", work)
    inside = _task(client, "見積", project_id=a["id"])
    outside = _task(client, "買い物")
    _work_log(client, inside["id"], "2026-09-02", 2)
    _work_log(client, outside["id"], "2026-09-02", 1)

    rows = client.get("/api/actuals/tasks", params={"project_id": work["id"]}).json()["rows"]
    assert [r["task"]["title"] for r in rows] == ["見積"]
    assert rows[0]["task"]["project_path"] == "仕事 / 案件 A"

    periods = client.get(
        "/api/actuals/periods",
        params={"unit": "closing", "from": "2026-09-01", "to": "2026-09-15", "project_id": work["id"]},
    ).json()["periods"]
    assert periods[0]["confirmed_seconds"] == 2 * 3600

    spans = client.get("/api/actuals/gantt", params={"project_id": work["id"]}).json()
    assert [s["task_id"] for s in spans] == [inside["id"]]
