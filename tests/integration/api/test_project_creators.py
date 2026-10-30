"""いちばん上のプロジェクトを作れるのは印のある人だけ（task #734 / ADR-0065）。

だれでも根を作って管理者になれると、WBS に入ったことのある人を同意なしにメンバーへ足し、その人の休み・稼働時間を
読み書きできた（休みは人に付くので、その人の別のチームの見込みまで動く）。管理者ができることは変えず、
管理者になれる人を絞る。ここでは、印の無い人が根を作れないこと、管理者にならないまま他人を足したり
他人の休みを読み書きしたりできないこと、印の付け外しを見る。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.use_cases.project_creator_use_cases import ProjectCreatorUseCases
from src.domain.exceptions import NotFoundError
from src.infrastructure.auth.auth_settings import SINGLE_USER_ID
from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_current_user, get_db

OTHER_EMAIL = "outsider@example.com"


def allow_project_creation(database_path: str, email: str) -> None:
    """SSO で入った人に印を付ける（他の試験から借りる。運用では scripts/grant_project_creator.py）。"""
    engine = create_engine(f"sqlite:///{database_path}")
    try:
        with Session(engine) as session:
            ProjectCreatorUseCases(session).allow(email)
    finally:
        engine.dispose()


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id,
            email=email,
            display_name="外の人",
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
    # 印の無い人（WBS に入ったことはある）
    user = UserModel(email=OTHER_EMAIL, display_name="外の人", timezone="Asia/Tokyo")
    db.add(user)
    db.flush()
    user_id = user.id
    db.commit()
    return user_id


@pytest.fixture
def as_(client, other_id):
    class Switch:
        def me(self) -> None:
            client.app.dependency_overrides.pop(get_current_user, None)

        def other(self) -> None:
            client.app.dependency_overrides[get_current_user] = _as_user(other_id, OTHER_EMAIL)

    switch = Switch()
    yield switch
    switch.me()


def _project(client, name: str, parent: int | None = None):
    return client.post("/api/projects", json={"name": name, "parent_project_id": parent})


def test_someone_without_the_mark_cannot_create_a_top_project(client, as_) -> None:
    as_.other()
    res = _project(client, "自分の根")
    assert res.status_code == 403, res.text
    assert client.get("/api/projects").json() == []


def test_the_default_user_has_the_mark(client) -> None:
    assert _project(client, "根").status_code == 201


def test_without_the_mark_nobody_can_be_added_or_have_their_leave_read(client, as_, other_id) -> None:
    """AC1: 印の無い人は、自分の根に他人を足して、その人の休みを読むことができない。"""
    # 自分（印あり）が自分の根で休みを入れておく
    mine = _project(client, "自分のチーム").json()
    client.post(f"/api/projects/{mine['id']}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-12-24"})

    as_.other()
    assert _project(client, "外の人の根").status_code == 403
    # 根が無いので、足す先も読む先も無い。人のチームは見えない
    assert client.get(f"/api/projects/{mine['id']}/calendar").status_code == 404
    assert client.post(
        f"/api/projects/{mine['id']}/members", json={"user_id": other_id}
    ).status_code == 404


def test_a_member_without_the_mark_cannot_rewrite_someone_elses_leave(client, as_, other_id) -> None:
    """AC2: 印の無い人は、メンバーとして入った木でも、管理者にならないまま他人の休みを書き換えられない。
    下のプロジェクトを根へ出しても管理者にはならない（元の木のメンバーと役割がそのまま写る）。"""
    team = _project(client, "チーム").json()
    client.post(f"/api/projects/{team['id']}/members", json={"user_id": other_id})
    other_team = _project(client, "別のチーム").json()
    client.post(f"/api/projects/{other_team['id']}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-12-24"})

    as_.other()
    part = _project(client, "部分", parent=team["id"])
    assert part.status_code == 201, part.text
    assert client.post(
        f"/api/projects/{team['id']}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-12-25", "hours": 12}
    ).status_code == 403
    assert client.delete(
        f"/api/projects/{team['id']}/members/{SINGLE_USER_ID}/leave/2026-12-24"
    ).status_code == 403

    # 下のものを根へ出しても、自分はメンバーのまま（他人を足せない・他人の休みを書けない）
    moved = client.post(f"/api/projects/{part.json()['id']}/move", json={"parent_project_id": None})
    assert moved.status_code == 200, moved.text
    assert moved.json()["my_role"] == "member"
    pid = part.json()["id"]
    assert client.post(f"/api/projects/{pid}/members", json={"user_id": SINGLE_USER_ID}).status_code == 403
    assert client.post(
        f"/api/projects/{pid}/members/{SINGLE_USER_ID}/leave", json={"day": "2026-12-25", "hours": 12}
    ).status_code == 403

    as_.me()
    view = client.get(f"/api/projects/{other_team['id']}/calendar").json()
    assert view["leave"] == [{"user_id": SINGLE_USER_ID, "day": "2026-12-24", "off_percent": 100, "hours": None}]


def test_the_mark_is_granted_and_revoked(client, db, as_) -> None:
    as_.other()
    assert _project(client, "根").status_code == 403

    user = ProjectCreatorUseCases(db).allow(OTHER_EMAIL)
    assert user.can_create_projects is True
    created = _project(client, "根")
    assert created.status_code == 201, created.text
    assert created.json()["my_role"] == "manager"

    assert ProjectCreatorUseCases(db).allow(OTHER_EMAIL, allowed=False).can_create_projects is False
    assert _project(client, "もう一つ").status_code == 403
    # 外しても、作った根の管理者のまま
    assert client.get(f"/api/projects/{created.json()['id']}").json()["my_role"] == "manager"


def test_the_mark_needs_someone_who_has_signed_in(db) -> None:
    with pytest.raises(NotFoundError):
        ProjectCreatorUseCases(db).allow("nobody@example.com")


def test_me_tells_whether_the_mark_is_there(client) -> None:
    assert client.get("/api/auth/me").json()["can_create_projects"] is True
