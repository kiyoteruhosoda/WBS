"""プロジェクトを作る・直す・動かす・保管する・消す（task #187 / ADR-0024）。"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from src.application.dto.project_dto import CreateProjectDTO, MoveProjectDTO, UpdateProjectDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.project import Project, project_code, project_name
from src.domain.exceptions import ProjectCycleError, ProjectNotEmptyError
from src.domain.services.project_calendar import layer_calendar_days
from src.domain.services.project_tree import ProjectTree
from src.domain.value_objects.project_role import ProjectRole
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.team_calendar_repository import (
    SqlAlchemyTeamCalendarRepository,
)


@dataclass(frozen=True)
class ProjectView:
    """応答の 1 行: プロジェクトと、表示用の道筋（「親 / 子」）。"""

    project: Project
    path: str
    #: いちばん上のプロジェクトの id と、そこでの自分の役割（ADR-0055）
    root_project_id: int
    my_role: ProjectRole | None


class ProjectUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = SqlAlchemyProjectRepository(session)
        self._team_calendar = SqlAlchemyTeamCalendarRepository(session)
        self._membership = ProjectMembership(
            projects=self._repo,
            tasks=SqlAlchemyTaskRepository(session),
            milestones=SqlAlchemyMilestoneRepository(session),
            members=SqlAlchemyProjectMemberRepository(session),
        )

    def list_projects(self, user_id: int) -> list[ProjectView]:
        """全部（保管したものも）。木の順（親の直後に子、兄弟は並び順）に並べる。"""
        tree = self._membership.tree(user_id)
        roles = self._membership.roles_of(user_id)
        ordered: list[ProjectView] = []

        def walk(parent_id: int | None) -> None:
            for project in tree.children_of(parent_id):
                ordered.append(self._view(project, tree, roles))
                walk(project.id)

        walk(None)
        return ordered

    def get_project(self, project_id: int, user_id: int) -> ProjectView:
        project = self._membership.visible_project(user_id, project_id)
        return self._view(project, self._membership.tree(user_id), self._membership.roles_of(user_id))

    def create_project(self, dto: CreateProjectDTO) -> ProjectView:
        if dto.parent_project_id is not None:
            self._membership.visible_project(dto.user_id, dto.parent_project_id)
        tree = self._membership.tree(dto.user_id)
        project = Project(
            id=None,
            user_id=dto.user_id,
            name=project_name(dto.name),
            parent_project_id=dto.parent_project_id,
            color=dto.color,
            code=project_code(dto.code),
            description=dto.description,
            # 兄弟の末尾へ
            sort_order=len(tree.children_of(dto.parent_project_id)),
        )
        saved = self._repo.save(project)
        if saved.parent_project_id is None and saved.id is not None:
            # 新しい根は作った人が管理者（ADR-0055 決定 6）
            self._membership.make_manager(dto.user_id, saved.id)
        self._session.commit()
        return self.get_project(saved.id or 0, dto.user_id)

    def update_project(self, project_id: int, user_id: int, dto: UpdateProjectDTO) -> ProjectView:
        project = self._membership.visible_project(user_id, project_id)
        if dto.name is not UNSET:
            project.name = project_name(dto.name)
        if dto.color is not UNSET:
            project.color = dto.color
        if dto.code is not UNSET:
            project.code = project_code(dto.code)
        if dto.description is not UNSET:
            project.description = dto.description
        if dto.status is not UNSET:
            project.status = dto.status
        self._repo.save(project)
        self._session.commit()
        return self.get_project(project_id, user_id)

    def move_project(self, project_id: int, user_id: int, dto: MoveProjectDTO) -> ProjectView:
        """親を替える・兄弟の中で並べ替える。⚠ 自分と自分の子孫の下へは移さない（環になる）。"""
        project = self._membership.visible_project(user_id, project_id)
        new_parent = dto.parent_project_id
        if new_parent is not None:
            self._membership.visible_project(user_id, new_parent)
        tree = self._membership.tree(user_id)
        if tree.would_cycle(project_id, new_parent):
            raise ProjectCycleError()
        old_parent = project.parent_project_id
        if old_parent is None and new_parent is not None:
            # 根を他の下へ入れると、この木のメンバーは消え、移った先の木のメンバーに見える（ADR-0055 決定 6）
            self._membership.require_manager(user_id, project_id)
            self._membership.forget_members(project_id)
            # 稼働する曜日は根にだけ付く。移った先の木のものを使う（ADR-0058 決定 2）。
            # 休日はこのプロジェクト自身の休日として残し、移った先の木の休日に足す（ADR-0059 決定 1）
            self._team_calendar.forget_workdays(project_id)
        elif old_parent is not None and new_parent is None:
            # 下のものを根へ出す: 元の木のメンバーを写す（見える人は変わらない）
            old_root = tree.root_of(project_id)
            self._membership.copy_members(old_root, project_id)
            self._copy_team_calendar(old_root, tree.ancestors_or_self(project_id), project_id)

        siblings = [p.id for p in tree.children_of(new_parent) if p.id != project_id]
        position = dto.position
        if position is None or position < 0 or position > len(siblings):
            position = len(siblings)
        siblings.insert(position, project_id)

        project.parent_project_id = new_parent
        self._repo.save(project)
        self._repo.set_sort_orders([i for i in siblings if i is not None])
        if old_parent != new_parent:
            # 元の兄弟の並びを詰める
            self._repo.set_sort_orders(
                [p.id for p in tree.children_of(old_parent) if p.id is not None and p.id != project_id]
            )
            # 枝の外へ出たタスクは、元の祖先のマイルストーンへ届かなくなる（ADR-0024）
            self._membership.detach_unreachable_milestones(user_id)
        self._session.commit()
        return self.get_project(project_id, user_id)

    def delete_project(self, project_id: int, user_id: int) -> None:
        """空のプロジェクトだけ消す。中身があれば 409（保管するか、中身を移してから）。"""
        project = self._membership.visible_project(user_id, project_id)
        if project.parent_project_id is None:
            # いちばん上を消すのは管理者だけ（ADR-0055 決定 2）
            self._membership.require_manager(user_id, project_id)
        if self._repo.has_contents(project_id):
            raise ProjectNotEmptyError()
        self._repo.delete(project_id)
        self._session.commit()

    def _copy_team_calendar(self, from_root_id: int, lineage: list[int], to_project_id: int) -> None:
        """下のプロジェクトを根へ出すとき、元の根の曜日と先祖から引き継いでいた休日・稼働日を写す（見込みを変えない）。"""
        workdays = self._team_calendar.workdays(from_root_id)
        if workdays is not None:
            self._team_calendar.set_workdays(to_project_id, workdays)
        own = {d.day for d in self._team_calendar.team_days_off([to_project_id])}
        own |= {d.day for d in self._team_calendar.extra_workdays([to_project_id])}
        ancestors = [p for p in lineage if p != to_project_id]
        # 先祖の休日・稼働日は近いほうが勝ったものを写す（ADR-0060）
        inherited = layer_calendar_days(
            ancestors, self._team_calendar.team_days_off(ancestors), self._team_calendar.extra_workdays(ancestors),
        )
        for day_off in inherited.days_off:
            if day_off.day not in own:
                self._team_calendar.add_team_day_off(replace(day_off, project_id=to_project_id))
        for workday in inherited.extra_workdays:
            if workday.day not in own:
                self._team_calendar.add_extra_workday(replace(workday, project_id=to_project_id))

    def _view(
        self, project: Project, tree: ProjectTree, roles: dict[int, ProjectRole]
    ) -> ProjectView:
        root = tree.root_of(project.id) if project.id is not None else 0
        return ProjectView(project, tree.path(project.id) or project.name, root, roles.get(root))


__all__ = ["ProjectUseCases", "ProjectView"]
