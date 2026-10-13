"""PC の自動記録の規則の API（task #381 / ADR-0043）。編集・PC へ渡す一覧・付け替え先のタスク。"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_app_or_web_user, get_current_user, get_db

OTHER_EMAIL = "other-rules@example.com"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email, timezone="Asia/Tokyo", language="ja"
        )

    return current


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def as_other(client, db):
    user = UserModel(email=OTHER_EMAIL, display_name="他人")
    db.add(user)
    db.flush()
    other = _as_user(user.id, OTHER_EMAIL)
    db.commit()

    def switch() -> None:
        client.app.dependency_overrides[get_current_user] = other
        client.app.dependency_overrides[get_app_or_web_user] = other

    yield switch
    client.app.dependency_overrides.pop(get_current_user, None)
    client.app.dependency_overrides.pop(get_app_or_web_user, None)


def _task(client, title: str, **extra) -> int:
    res = client.post("/api/tasks", json={"title": title, **extra})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _rule(client, task_id: int, app: str | None = None, title: str | None = None) -> dict:
    res = client.post(
        "/api/tracking-rules", json={"app": app, "title_contains": title, "task_id": task_id}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _feed(client) -> dict:
    res = client.get("/api/tracking-rules")
    assert res.status_code == 200, res.text
    return res.json()


def _instant(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def test_no_rules_at_first(client) -> None:
    feed = _feed(client)
    assert feed["rules"] == []
    assert feed["updated_at"].endswith("Z")


def test_rules_are_listed_top_down_for_the_pc(client) -> None:
    quote = _task(client, "見積書を作る")
    mail = _task(client, "メール")
    first = _rule(client, quote, app=" EXCEL.EXE ", title="見積")
    second = _rule(client, mail, app="OUTLOOK.EXE")
    third = _rule(client, quote, title="見積書")
    assert (first["app"], first["title_contains"]) == ("EXCEL.EXE", "見積")
    assert second["title_contains"] is None

    feed = _feed(client)
    assert [(r["id"], r["position"]) for r in feed["rules"]] == [
        (first["id"], 0), (second["id"], 1), (third["id"], 2),
    ]
    assert feed["rules"][0] == {
        "id": first["id"], "position": 0, "app": "EXCEL.EXE", "title_contains": "見積",
        "task_id": quote, "task_title": "見積書を作る",
    }


def test_one_everything_else_rule_is_always_last(client) -> None:
    """両方空の規則は「それ以外すべて」。1 人 1 つまで、いつも最後（ADR-0045）。"""
    default = _task(client, "ProjectA の作業")
    quote = _task(client, "見積")
    fallback = client.post("/api/tracking-rules", json={"task_id": default, "app": "  ", "title_contains": ""})
    assert fallback.status_code == 201, fallback.text
    assert (fallback.json()["app"], fallback.json()["title_contains"]) == (None, None)
    rule = _rule(client, quote, app="EXCEL.EXE")

    # 先に作っても最後に来る。並べ替えで先頭へ送っても最後のまま
    assert [r["id"] for r in _feed(client)["rules"]] == [rule["id"], fallback.json()["id"]]
    res = client.put("/api/tracking-rules/order", json={"rule_ids": [fallback.json()["id"], rule["id"]]})
    assert [r["id"] for r in res.json()] == [rule["id"], fallback.json()["id"]]
    assert [r["id"] for r in client.get("/api/tracking-rules/editor").json()] == [
        rule["id"], fallback.json()["id"],
    ]

    # 2 つ目は作れないし、直して 2 つ目にもできない
    assert client.post("/api/tracking-rules", json={"task_id": quote}).status_code == 422
    res = client.patch(f"/api/tracking-rules/{rule['id']}", json={"app": None})
    assert res.status_code == 422
    # 自分自身を直すのはよい
    res = client.patch(f"/api/tracking-rules/{fallback.json()['id']}", json={"task_id": quote})
    assert res.status_code == 200, res.text
    res = client.patch(f"/api/tracking-rules/{rule['id']}", json={"app": None, "title_contains": "WBS"})
    assert res.status_code == 200, res.text
    assert (res.json()["app"], res.json()["title_contains"]) == (None, "WBS")


def test_reorder_and_delete(client) -> None:
    task = _task(client, "設計")
    a, b, c = (_rule(client, task, app=f"{n}.exe")["id"] for n in "abc")
    res = client.put("/api/tracking-rules/order", json={"rule_ids": [c, a]})
    assert res.status_code == 200, res.text
    assert [r["id"] for r in res.json()] == [c, a, b]
    assert [r["id"] for r in _feed(client)["rules"]] == [c, a, b]

    before = _instant(_feed(client)["updated_at"])
    assert client.delete(f"/api/tracking-rules/{a}").status_code == 204
    feed = _feed(client)
    assert [r["id"] for r in feed["rules"]] == [c, b]
    # 消したことも PC に伝わる
    assert _instant(feed["updated_at"]) > before
    assert client.put("/api/tracking-rules/order", json={"rule_ids": [a]}).status_code == 404


def test_rules_of_done_or_deleted_tasks_stay_on_screen_but_leave_the_feed(client) -> None:
    done = _task(client, "終わる")
    gone = _task(client, "消える")
    kept = _task(client, "続く")
    r_done = _rule(client, done, app="a.exe")["id"]
    r_gone = _rule(client, gone, app="b.exe")["id"]
    r_kept = _rule(client, kept, app="c.exe")["id"]
    before = _instant(_feed(client)["updated_at"])

    for status in ("DOING", "DONE"):
        assert client.patch(f"/api/tasks/{done}", json={"status": status}).status_code == 200
    assert client.delete(f"/api/tasks/{gone}").status_code == 204

    feed = _feed(client)
    assert [r["id"] for r in feed["rules"]] == [r_kept]
    assert _instant(feed["updated_at"]) > before
    editor = {r["id"]: r for r in client.get("/api/tracking-rules/editor").json()}
    assert (editor[r_done]["task_available"], editor[r_done]["task_title"]) == (False, "終わる")
    assert (editor[r_gone]["task_available"], editor[r_gone]["task_title"]) == (False, None)
    assert editor[r_kept]["task_available"] is True

    # 付け替えれば戻る。閉じたタスクへは向けられない
    assert client.patch(f"/api/tracking-rules/{r_gone}", json={"task_id": done}).status_code == 422
    assert client.patch(f"/api/tracking-rules/{r_gone}", json={"task_id": kept}).status_code == 200
    assert [r["id"] for r in _feed(client)["rules"]] == [r_gone, r_kept]


def test_renaming_the_task_moves_updated_at(client) -> None:
    task = _task(client, "前の名前")
    _rule(client, task, app="a.exe")
    before = _feed(client)
    assert client.patch(f"/api/tasks/{task}", json={"title": "新しい名前"}).status_code == 200
    after = _feed(client)
    assert after["rules"][0]["task_title"] == "新しい名前"
    assert _instant(after["updated_at"]) > _instant(before["updated_at"])


def test_trackable_tasks_are_open_ones_with_their_project(client) -> None:
    project = client.post("/api/projects", json={"name": "案件A"})
    assert project.status_code == 201, project.text
    in_project = _task(client, "見積", project_id=project.json()["id"])
    loose = _task(client, "雑務")
    done = _task(client, "済み")
    for status in ("DOING", "DONE"):
        client.patch(f"/api/tasks/{done}", json={"status": status})
    res = client.get("/api/tracking-rules/tasks")
    assert res.status_code == 200, res.text
    tasks = res.json()["tasks"]
    assert {t["id"] for t in tasks} == {in_project, loose}
    assert {t["id"]: t["project_title"] for t in tasks} == {in_project: "案件A", loose: None}


def test_someone_elses_rules_and_tasks_are_out_of_reach(client, as_other) -> None:
    mine = _task(client, "私の")
    rule = _rule(client, mine, app="a.exe")["id"]
    as_other()
    assert _feed(client)["rules"] == []
    assert client.get("/api/tracking-rules/tasks").json()["tasks"] == []
    assert client.patch(f"/api/tracking-rules/{rule}", json={"app": "x.exe"}).status_code == 404
    assert client.delete(f"/api/tracking-rules/{rule}").status_code == 404
    assert client.post(
        "/api/tracking-rules", json={"app": "a.exe", "task_id": mine}
    ).status_code == 404
