"""プロジェクトのメンバーを見る・加える・役割を変える・外す（task #544 / ADR-0055）。

メンバーはいちばん上のプロジェクトに付く。どの段のプロジェクトの id で呼んでも、その木の根のメンバーを扱う。
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy.orm import Session

from src.application.ports.person_directory import Person, PersonDirectory
from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.project_member import ProjectMember
from src.domain.exceptions import (
    LastProjectManagerError,
    NotFoundError,
    ValidationError,
)
from src.domain.value_objects.project_role import ProjectRole
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.user_account_repository import SqlAlchemyUserAccountRepository


@dataclass(frozen=True)
class MemberView:
    user_id: int
    display_name: str
    email: str
    role: ProjectRole
    #: 聞いた本人か（画面が「外す」を「抜ける」と出す）
    is_you: bool
    #: 1 日の工数（時間）と従事率（%）。ADR-0058
    daily_hours: Decimal
    engagement_percent: int


@dataclass(frozen=True)
class ProjectMembersView:
    #: メンバーが付いている根
    root_project_id: int
    #: 自分がこの木で管理者か（画面が出し入れのボタンを出すか決める）
    can_manage: bool
    members: list[MemberView]


class ProjectMemberUseCases:
    def __init__(self, session: Session, people: PersonDirectory) -> None:
        self._session = session
        self._members = SqlAlchemyProjectMemberRepository(session)
        self._people = people
        self._users = SqlAlchemyUserAccountRepository(session)
        self._membership = ProjectMembership(
            projects=SqlAlchemyProjectRepository(session),
            tasks=SqlAlchemyTaskRepository(session),
            milestones=SqlAlchemyMilestoneRepository(session),
            members=self._members,
        )

    def candidates(self, user_id: int) -> list[Person]:
        """メンバー・担当者に選べる人（WBS に 1 度でもログインした人。ADR-0055 決定 5）。

        全員を返すのは、どこかの木の管理者か、根を作れる印のある人だけ（メンバーを足すのに要る）。
        ほかの人には、自分と同じ木に居る人（と自分）だけを返す（ADR-0067）。
        """
        people = self._people.choosable()
        if self._may_see_everyone(user_id):
            return people
        mates = {user_id}
        for root in self._membership.roles_of(user_id):
            mates |= self._membership.member_ids(root)
        return [p for p in people if p.id in mates]

    def _may_see_everyone(self, user_id: int) -> bool:
        if any(role is ProjectRole.MANAGER for role in self._membership.roles_of(user_id).values()):
            return True
        user = self._users.find_by_id(user_id)
        return user is not None and user.can_create_projects

    def list_members(self, user_id: int, project_id: int) -> ProjectMembersView:
        root = self._root_of(user_id, project_id)
        members = self._members.find_by_project(root)
        names = self._people.by_ids({m.user_id for m in members})
        mine = next((m for m in members if m.user_id == user_id), None)
        return ProjectMembersView(
            root_project_id=root,
            can_manage=mine is not None and mine.is_manager,
            members=[self._view(m, names.get(m.user_id), user_id) for m in members],
        )

    def add_member(
        self, user_id: int, project_id: int, member_user_id: int, role: ProjectRole
    ) -> ProjectMembersView:
        """加える（もう居れば役割を書き換える）。選べるのは WBS に入ったことのある人だけ（422）。"""
        root = self._root_of(user_id, project_id)
        self._membership.require_manager(user_id, root)
        if member_user_id not in {p.id for p in self._people.choosable()}:
            raise ValidationError("the person has not signed in to WBS, or has been stopped")
        current = self._members.find(root, member_user_id)
        if current is not None:
            return self.change_role(user_id, project_id, member_user_id, role)
        self._members.save(
            ProjectMember(id=None, project_id=root, user_id=member_user_id, role=role)
        )
        self._session.commit()
        return self.list_members(user_id, project_id)

    def change_role(
        self, user_id: int, project_id: int, member_user_id: int, role: ProjectRole
    ) -> ProjectMembersView:
        root = self._root_of(user_id, project_id)
        self._membership.require_manager(user_id, root)
        member = self._members.find(root, member_user_id)
        if member is None:
            raise NotFoundError("ProjectMember", member_user_id)
        if member.is_manager and role is not ProjectRole.MANAGER:
            self._keep_a_manager(root, member_user_id)
        member.role = role
        self._members.save(member)
        self._session.commit()
        return self.list_members(user_id, project_id)

    def change_capacity(
        self,
        user_id: int,
        project_id: int,
        member_user_id: int,
        daily_hours: Decimal,
        engagement_percent: int,
    ) -> ProjectMembersView:
        """1 日の工数と従事率を変える。管理者は誰のでも、メンバーは自分のだけ（ADR-0058 決定 1）。"""
        root = self._root_of(user_id, project_id)
        if member_user_id != user_id:
            self._membership.require_manager(user_id, root)
        member = self._members.find(root, member_user_id)
        if member is None:
            raise NotFoundError("ProjectMember", member_user_id)
        member.set_capacity(daily_hours, engagement_percent)
        self._members.save(member)
        self._session.commit()
        return self.list_members(user_id, project_id)

    def remove_member(self, user_id: int, project_id: int, member_user_id: int) -> None:
        """外す。管理者は誰でも、メンバーは自分だけ（抜ける）を外せる。最後の管理者は外せない（409）。"""
        root = self._root_of(user_id, project_id)
        if member_user_id != user_id:
            self._membership.require_manager(user_id, root)
        member = self._members.find(root, member_user_id)
        if member is None:
            raise NotFoundError("ProjectMember", member_user_id)
        if member.is_manager:
            self._keep_a_manager(root, member_user_id)
        # 担当は消さずに残す（ADR-0055 決定 4）。見えなくなれば Tracker へも渡らない
        self._members.delete(root, member_user_id)
        self._session.commit()

    def _root_of(self, user_id: int, project_id: int) -> int:
        self._membership.visible_project(user_id, project_id)  # 見えなければ 404
        return self._membership.tree(user_id).root_of(project_id)

    def _keep_a_manager(self, root: int, leaving_user_id: int) -> None:
        others = [
            m for m in self._members.find_by_project(root)
            if m.is_manager and m.user_id != leaving_user_id
        ]
        if not others:
            raise LastProjectManagerError()

    @staticmethod
    def _view(member: ProjectMember, person: Person | None, viewer_id: int) -> MemberView:
        return MemberView(
            user_id=member.user_id,
            display_name=person.display_name if person is not None else "",
            email=person.email if person is not None else "",
            role=member.role,
            is_you=member.user_id == viewer_id,
            daily_hours=member.daily_hours,
            engagement_percent=member.engagement_percent,
        )


__all__ = [
    "MemberView",
    "ProjectMemberUseCases",
    "ProjectMembersView",
]
