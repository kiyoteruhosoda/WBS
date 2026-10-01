"""依存（task_dependencies）が利用者を跨がないこと（task #164）。

``task_dependencies`` には持ち主の列が無く、以前は全員分を引いてから絞っていた。
利用者を 2 人にして、ガント・依存の取得・追加・削除のどれでも他人の分に届かないことを見る。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import UserModel
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "other@example.com"


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id,
            email=email,
            display_name=email,
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
def other_user_id(db) -> int:
    user = UserModel(email=OTHER_EMAIL, display_name="他人")
    db.add(user)
    db.flush()
    user_id = user.id
    db.commit()
    return user_id


@pytest.fixture
def two_users(client, other_user_id):
    """``me`` / ``other`` で current user を切り替える。既定は自分（単独利用者）。"""

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_user_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _task(client, title: str) -> int:
    res = client.post("/api/tasks", json={"title": title})
    assert res.status_code == 201, res.text
    return res.json()["id"]


def _depend(client, successor: int, predecessor: int):
    return client.post(
        f"/api/tasks/{successor}/dependencies",
        json={"predecessor_task_id": predecessor, "dependency_type": "FS", "lag_days": 0},
    )


@pytest.fixture
def world(client, two_users):
    """自分に A→B、他人に X→Y の依存を作る。"""
    a = _task(client, "自分の A")
    b = _task(client, "自分の B")
    assert _depend(client, b, a).status_code == 201

    two_users.other()
    x = _task(client, "他人の X")
    y = _task(client, "他人の Y")
    assert _depend(client, y, x).status_code == 201
    two_users.me()
    return {"a": a, "b": b, "x": x, "y": y}


def test_gantt_shows_only_my_dependencies(client, two_users, world) -> None:
    mine = client.get("/api/gantt").json()
    assert {t["id"] for t in mine} == {world["a"], world["b"]}
    deps = [(t["id"], d["predecessor_task_id"]) for t in mine for d in t["dependencies"]]
    assert deps == [(world["b"], world["a"])]

    two_users.other()
    theirs = client.get("/api/gantt").json()
    assert {t["id"] for t in theirs} == {world["x"], world["y"]}
    deps = [(t["id"], d["predecessor_task_id"]) for t in theirs for d in t["dependencies"]]
    assert deps == [(world["y"], world["x"])]


def test_repository_returns_only_dependencies_whose_both_ends_are_mine(
    db, world, other_user_id
) -> None:
    repo = SqlAlchemyTaskDependencyRepository(db)

    mine = repo.find_all_for_user(SINGLE_USER_ID)
    assert [(d.predecessor_task_id, d.successor_task_id) for d in mine] == [
        (world["a"], world["b"])
    ]
    theirs = repo.find_all_for_user(other_user_id)
    assert [(d.predecessor_task_id, d.successor_task_id) for d in theirs] == [
        (world["x"], world["y"])
    ]
    # 他人のタスクを名指ししても、自分の分としては何も返らない。
    assert repo.find_by_task_for_user(world["y"], SINGLE_USER_ID) == []


def test_cannot_read_dependencies_of_someone_elses_task(client, world) -> None:
    assert client.get(f"/api/tasks/{world['y']}/dependencies").status_code == 404

    mine = client.get(f"/api/tasks/{world['b']}/dependencies").json()
    assert [p["predecessor_task_id"] for p in mine["predecessors"]] == [world["a"]]
    assert mine["successors"] == []


def test_cannot_add_a_dependency_that_touches_someone_elses_task(client, world) -> None:
    # 他人のタスクを先行に指す
    assert _depend(client, world["b"], world["x"]).status_code == 404
    # 他人のタスクに後続として依存を足す
    assert _depend(client, world["y"], world["a"]).status_code == 404
    # 他人のタスク同士
    assert _depend(client, world["x"], world["y"]).status_code == 404

    gantt = client.get("/api/gantt").json()
    assert [d["predecessor_task_id"] for t in gantt for d in t["dependencies"]] == [world["a"]]


def test_cannot_remove_someone_elses_dependency(client, two_users, world) -> None:
    res = client.delete(f"/api/tasks/{world['y']}/dependencies/{world['x']}")
    assert res.status_code == 404

    two_users.other()
    still = client.get(f"/api/tasks/{world['y']}/dependencies").json()
    assert [p["predecessor_task_id"] for p in still["predecessors"]] == [world["x"]]


def test_cycle_check_still_works_within_my_tasks(client, world) -> None:
    # A→B があるので B→A は循環
    assert _depend(client, world["a"], world["b"]).status_code == 409


def test_cycle_check_follows_a_longer_chain(client, world) -> None:
    c = _task(client, "自分の C")
    assert _depend(client, c, world["b"]).status_code == 201  # A→B→C
    assert _depend(client, world["a"], c).status_code == 409  # C→A で循環
    assert _depend(client, world["a"], world["a"]).status_code == 409  # 自分自身


def test_i_can_still_remove_my_own_dependency(client, world) -> None:
    res = client.delete(f"/api/tasks/{world['b']}/dependencies/{world['a']}")
    assert res.status_code == 204
    assert client.get(f"/api/tasks/{world['b']}/dependencies").json()["predecessors"] == []
