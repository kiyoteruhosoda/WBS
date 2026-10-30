"""プロジェクトのメンバー・担当者（task #544 / ADR-0055）。

利用者を 2 人にして、根のメンバーにするとその木のタスクが見え、外すと見えなくなること、
役割（管理者・メンバー）の境、担当者の付け方と絞り込み、プロジェクトを動かしたときのメンバーを見る。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.use_cases.project_creator_use_cases import ProjectCreatorUseCases
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "member@example.com"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id,
            email=email,
            display_name="仲間",
            timezone="Asia/Tokyo",
            language="ja",
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
def other_id(db) -> int:
    user = UserModel(email=OTHER_EMAIL, display_name="仲間", timezone="Asia/Tokyo")
    db.add(user)
    db.flush()
    user_id = user.id
    db.commit()
    return user_id


@pytest.fixture
def as_(client, other_id):
    """``as_.me()`` / ``as_.other()`` で current user を切り替える。既定は自分（単独利用者）。"""

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _project(client, name: str, parent: int | None = None) -> dict:
    res = client.post("/api/projects", json={"name": name, "parent_project_id": parent})
    assert res.status_code == 201, res.text
    return res.json()


def _task(client, title: str, **fields) -> dict:
    res = client.post("/api/tasks", json={"title": title, **fields})
    assert res.status_code == 201, res.text
    return res.json()


def _titles(client, **params) -> list[str]:
    res = client.get("/api/tasks", params=params)
    assert res.status_code == 200, res.text
    return sorted(t["title"] for t in res.json())


def test_a_new_top_project_makes_its_creator_the_manager(client) -> None:
    root = _project(client, "根")
    child = _project(client, "子", parent=root["id"])
    assert root["my_role"] == "manager"
    assert child["root_project_id"] == root["id"]
    assert child["my_role"] == "manager"
    members = client.get(f"/api/projects/{child['id']}/members").json()
    assert members["root_project_id"] == root["id"]
    assert members["can_manage"] is True
    assert [(m["user_id"], m["role"]) for m in members["members"]] == [(SINGLE_USER_ID, "manager")]


def test_adding_a_member_shares_the_whole_tree(client, as_, other_id) -> None:
    root = _project(client, "根")
    child = _project(client, "子", parent=root["id"])
    _task(client, "根のタスク", project_id=root["id"])
    _task(client, "子のタスク", project_id=child["id"])
    _task(client, "自分だけのタスク")

    as_.other()
    assert client.get("/api/projects").json() == []
    assert _titles(client) == []
    assert client.get(f"/api/projects/{root['id']}").status_code == 404

    as_.me()
    res = client.post(f"/api/projects/{child['id']}/members", json={"user_id": other_id})
    assert res.status_code == 200, res.text
    assert {m["user_id"]: m["role"] for m in res.json()["members"]} == {
        SINGLE_USER_ID: "manager",
        other_id: "member",
    }

    as_.other()
    assert [p["name"] for p in client.get("/api/projects").json()] == ["根", "子"]
    assert _titles(client) == ["子のタスク", "根のタスク"]
    # メンバーはタスクを作れ、作ったものは持ち主にも見える
    _task(client, "仲間のタスク", project_id=child["id"])
    as_.me()
    assert _titles(client, project_id=root["id"]) == ["仲間のタスク", "子のタスク", "根のタスク"]

    # 外すと見えなくなる
    assert client.delete(f"/api/projects/{root['id']}/members/{other_id}").status_code == 204
    as_.other()
    assert _titles(client) == []


def test_only_managers_manage_members(client, as_, other_id) -> None:
    root = _project(client, "根")
    client.post(f"/api/projects/{root['id']}/members", json={"user_id": other_id})

    as_.other()
    listing = client.get(f"/api/projects/{root['id']}/members").json()
    assert listing["can_manage"] is False
    assert client.post(
        f"/api/projects/{root['id']}/members", json={"user_id": SINGLE_USER_ID, "role": "member"}
    ).status_code == 403
    assert client.put(
        f"/api/projects/{root['id']}/members/{SINGLE_USER_ID}", json={"role": "member"}
    ).status_code == 403
    assert client.delete(f"/api/projects/{root['id']}/members/{SINGLE_USER_ID}").status_code == 403
    # 根を消すのも管理者だけ
    assert client.delete(f"/api/projects/{root['id']}").status_code == 403
    # 自分で抜けるのはよい
    assert client.delete(f"/api/projects/{root['id']}/members/{other_id}").status_code == 204
    assert client.get(f"/api/projects/{root['id']}").status_code == 404


def test_the_last_manager_cannot_leave_or_step_down(client, as_, other_id) -> None:
    root = _project(client, "根")
    url = f"/api/projects/{root['id']}/members"
    assert client.delete(f"{url}/{SINGLE_USER_ID}").status_code == 409
    assert client.put(f"{url}/{SINGLE_USER_ID}", json={"role": "member"}).status_code == 409

    client.post(url, json={"user_id": other_id, "role": "manager"})
    assert client.put(f"{url}/{SINGLE_USER_ID}", json={"role": "member"}).status_code == 200
    roles = {m["user_id"]: m["role"] for m in client.get(url).json()["members"]}
    assert roles == {SINGLE_USER_ID: "member", other_id: "manager"}


def test_people_who_never_signed_in_cannot_be_added(client) -> None:
    root = _project(client, "根")
    res = client.post(f"/api/projects/{root['id']}/members", json={"user_id": 99999})
    assert res.status_code == 422, res.text


def test_people_lists_active_users(client, db, other_id) -> None:
    stopped = UserModel(email="stopped@example.com", display_name="止めた人", is_active=False)
    db.add(stopped)
    db.commit()
    ids = {p["id"] for p in client.get("/api/projects/people").json()}
    assert other_id in ids
    assert SINGLE_USER_ID in ids
    assert stopped.id not in ids


def test_assignee_defaults_to_the_creator_and_must_be_a_member(client, as_, other_id) -> None:
    root = _project(client, "根")
    task = _task(client, "設計", project_id=root["id"])
    assert task["assignee_user_id"] == SINGLE_USER_ID
    assert task["assignee_name"]

    # メンバーでない人は 422
    res = client.put(f"/api/tasks/{task['id']}", json={"assignee_user_id": other_id})
    assert res.status_code == 422, res.text

    client.post(f"/api/projects/{root['id']}/members", json={"user_id": other_id})
    res = client.put(f"/api/tasks/{task['id']}", json={"assignee_user_id": other_id})
    assert res.status_code == 200, res.text
    assert res.json()["assignee_user_id"] == other_id
    assert res.json()["assignee_name"] == "仲間"

    unassigned = _task(client, "だれか", project_id=root["id"], assignee_user_id=None)
    assert unassigned["assignee_user_id"] is None

    # 未分類のタスクは作った本人だけ
    mine = _task(client, "自分だけ")
    res = client.put(f"/api/tasks/{mine['id']}", json={"assignee_user_id": other_id})
    assert res.status_code == 422, res.text

    as_.other()
    assert _titles(client, assignee="me") == ["設計"]
    as_.me()
    assert _titles(client, assignee="me") == ["自分だけ"]
    assert _titles(client, assignee=str(other_id)) == ["設計"]
    assert _titles(client, assignee="none") == ["だれか"]


def test_a_removed_member_keeps_the_assignment_but_cannot_see_it(client, as_, other_id) -> None:
    root = _project(client, "根")
    client.post(f"/api/projects/{root['id']}/members", json={"user_id": other_id})
    task = _task(client, "設計", project_id=root["id"], assignee_user_id=other_id)
    client.delete(f"/api/projects/{root['id']}/members/{other_id}")

    assert client.get(f"/api/tasks/{task['id']}").json()["assignee_user_id"] == other_id
    as_.other()
    assert _titles(client, assignee="me") == []


def test_moving_projects_keeps_or_hands_over_the_members(client, as_, other_id) -> None:
    team = _project(client, "チーム")
    client.post(f"/api/projects/{team['id']}/members", json={"user_id": other_id})
    part = _project(client, "部分", parent=team["id"])
    solo = _project(client, "ひとり")
    _task(client, "ひとりのタスク", project_id=solo["id"])

    # 下のものを根へ出しても、見える人は変わらない
    res = client.post(f"/api/projects/{part['id']}/move", json={"parent_project_id": None})
    assert res.status_code == 200, res.text
    assert res.json()["root_project_id"] == part["id"]
    assert {m["user_id"] for m in client.get(f"/api/projects/{part['id']}/members").json()["members"]} == {
        SINGLE_USER_ID,
        other_id,
    }

    # 根を他の木へ入れると、移った先のメンバーに見える
    res = client.post(f"/api/projects/{solo['id']}/move", json={"parent_project_id": team["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["root_project_id"] == team["id"]
    as_.other()
    assert "ひとりのタスク" in _titles(client)


def test_a_member_cannot_move_someone_elses_top_project(client, db, as_, other_id) -> None:
    team = _project(client, "チーム")
    client.post(f"/api/projects/{team['id']}/members", json={"user_id": other_id})
    # 仲間も根を作れる人にする（ADR-0065）
    ProjectCreatorUseCases(db).allow(OTHER_EMAIL)
    as_.other()
    own = _project(client, "仲間の根")
    # 仲間は自分の根でも「チーム」へは入れられない（チームの管理者ではない。ADR-0066）
    assert client.post(
        f"/api/projects/{own['id']}/move", json={"parent_project_id": team["id"]}
    ).status_code == 403
    # でも「チーム」を自分の根の下へ入れることはできない（管理者ではない）
    another = _project(client, "もう一つ")
    assert client.post(
        f"/api/projects/{team['id']}/move", json={"parent_project_id": another["id"]}
    ).status_code == 403
