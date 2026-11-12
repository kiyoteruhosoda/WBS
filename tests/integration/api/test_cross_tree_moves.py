"""Moving across trees (top-level projects) is only for admins of both the source and the destination (task #735 / ADR-0066).

Members could take the team's tasks, child projects and milestones out to their own tree, hiding them from the original team.
Moving within the same tree is still allowed for members, as before.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.use_cases.project_creator_use_cases import ProjectCreatorUseCases
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "member@example.com"


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
    # Make the teammate someone who can own their own root too (ADR-0065)
    ProjectCreatorUseCases(db).allow(OTHER_EMAIL)
    return user_id


@pytest.fixture
def as_(client, other_id):
    """Switch the current user with ``as_.me()`` / ``as_.other()``. Default is me (the team's admin)."""

    def other() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=other_id, email=OTHER_EMAIL, display_name="仲間", timezone="Asia/Tokyo", language="ja"
        )

    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = other

    switch = Switch()
    yield switch
    switch.me()


def _created(res) -> dict:
    assert res.status_code == 201, res.text
    return res.json()


@pytest.fixture
def team(client, as_, other_id) -> dict:
    """A team tree where I am admin (root, two children, a task, a milestone) and a root owned only by the teammate. The teammate is a team member."""
    root = _created(client.post("/api/projects", json={"name": "チーム"}))
    child = _created(client.post("/api/projects", json={"name": "子", "parent_project_id": root["id"]}))
    sibling = _created(client.post("/api/projects", json={"name": "隣", "parent_project_id": root["id"]}))
    task = _created(client.post("/api/tasks", json={"title": "チームのタスク", "project_id": root["id"]}))
    milestone = _created(client.post("/api/milestones", json={"name": "出荷", "project_id": root["id"]}))
    res = client.post(f"/api/projects/{root['id']}/members", json={"user_id": other_id})
    assert res.status_code == 200, res.text
    as_.other()
    own = _created(client.post("/api/projects", json={"name": "仲間だけの根"}))
    own_task = _created(client.post("/api/tasks", json={"title": "仲間のタスク", "project_id": own["id"]}))
    loose = _created(client.post("/api/tasks", json={"title": "仲間の未分類"}))
    as_.me()
    return {
        "root": root, "child": child, "sibling": sibling, "task": task, "milestone": milestone,
        "own": own, "own_task": own_task, "loose": loose,
    }


def test_a_member_cannot_carry_a_team_task_to_another_tree(client, as_, team) -> None:
    task_id, own_id = team["task"]["id"], team["own"]["id"]
    as_.other()
    assert client.put(f"/api/tasks/{task_id}", json={"project_id": own_id}).status_code == 403
    assert client.patch(f"/api/tasks/{task_id}", json={"project_id": own_id}).status_code == 403
    assert client.put(f"/api/tasks/{task_id}", json={"project_id": None}).status_code == 403
    for target in (own_id, None):
        res = client.post("/api/tasks/move-to-project", json={"task_ids": [task_id], "project_id": target})
        assert res.status_code == 403, res.text
    # Same for putting it under a task in my own tree and taking it out
    res = client.put(f"/api/tasks/{task_id}", json={"parent_task_id": team["own_task"]["id"]})
    assert res.status_code == 403, res.text

    as_.me()
    res = client.get(f"/api/tasks/{task_id}")
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] == team["root"]["id"]
    assert res.json()["parent_task_id"] is None


def test_a_member_cannot_carry_a_sub_project_or_milestone_to_another_tree(client, as_, team) -> None:
    child_id, own_id = team["child"]["id"], team["own"]["id"]
    as_.other()
    res = client.post(f"/api/projects/{child_id}/move", json={"parent_project_id": own_id})
    assert res.status_code == 403, res.text
    res = client.put(f"/api/milestones/{team['milestone']['id']}", json={"project_id": own_id})
    assert res.status_code == 403, res.text

    as_.me()
    assert client.get(f"/api/projects/{child_id}").json()["root_project_id"] == team["root"]["id"]
    assert client.get(f"/api/milestones/{team['milestone']['id']}").status_code == 200


def test_a_member_cannot_push_own_things_into_a_team_tree(client, as_, team) -> None:
    # Cannot hand over to a tree you don't administer (only admins of both source and destination)
    as_.other()
    root_id = team["root"]["id"]
    res = client.post(f"/api/projects/{team['own']['id']}/move", json={"parent_project_id": root_id})
    assert res.status_code == 403, res.text
    res = client.put(f"/api/tasks/{team['loose']['id']}", json={"project_id": root_id})
    assert res.status_code == 403, res.text


def test_a_member_still_moves_things_within_the_tree(client, as_, team) -> None:
    child_id, sibling_id = team["child"]["id"], team["sibling"]["id"]
    as_.other()
    res = client.put(f"/api/tasks/{team['task']['id']}", json={"project_id": child_id})
    assert res.status_code == 200, res.text
    assert res.json()["project_id"] == child_id
    res = client.post("/api/tasks/move-to-project", json={"task_ids": [team["task"]["id"]], "project_id": sibling_id})
    assert res.status_code == 200, res.text
    res = client.post(f"/api/projects/{child_id}/move", json={"parent_project_id": sibling_id})
    assert res.status_code == 200, res.text
    assert res.json()["root_project_id"] == team["root"]["id"]
    res = client.put(f"/api/milestones/{team['milestone']['id']}", json={"project_id": sibling_id})
    assert res.status_code == 200, res.text
    # Between my uncategorized items and my own tree too, as before
    res = client.put(f"/api/tasks/{team['loose']['id']}", json={"project_id": team["own"]["id"]})
    assert res.status_code == 200, res.text


def test_a_manager_of_both_trees_can_move_across(client, as_, other_id, team) -> None:
    res = client.put(f"/api/projects/{team['root']['id']}/members/{other_id}", json={"role": "manager"})
    assert res.status_code == 200, res.text
    as_.other()
    res = client.put(f"/api/tasks/{team['task']['id']}", json={"project_id": team["own"]["id"]})
    assert res.status_code == 200, res.text
    res = client.post(f"/api/projects/{team['child']['id']}/move", json={"parent_project_id": team["own"]["id"]})
    assert res.status_code == 200, res.text
    assert res.json()["root_project_id"] == team["own"]["id"]
