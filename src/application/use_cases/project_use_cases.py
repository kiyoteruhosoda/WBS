"""プロジェクトを作る・直す・動かす・保管する・消す（task #187 / ADR-0024）。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from src.application.dto.project_dto import CreateProjectDTO, MoveProjectDTO, UpdateProjectDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.project import Project, project_code, project_name
from src.domain.exceptions import ProjectCycleError, ProjectNotEmptyError
from src.domain.services.project_tree import ProjectTree
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository


@dataclass(frozen=True)
class ProjectView:
    """応答の 1 行: プロジェクトと、表示用の道筋（「親 / 子」）。"""

    project: Project
    path: str


class ProjectUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = SqlAlchemyProjectRepository(session)
        self._membership = ProjectMembership(
            projects=self._repo,
            tasks=SqlAlchemyTaskRepository(session),
            milestones=SqlAlchemyMilestoneRepository(session),
        )

    def list_projects(self, user_id: int) -> list[ProjectView]:
        """全部（保管したものも）。木の順（親の直後に子、兄弟は並び順）に並べる。"""
        tree = self._membership.tree(user_id)
        ordered: list[ProjectView] = []

        def walk(parent_id: int | None) -> None:
            for project in tree.children_of(parent_id):
                ordered.append(ProjectView(project, tree.path(project.id) or project.name))
                walk(project.id)

        walk(None)
        return ordered

    def get_project(self, project_id: int, user_id: int) -> ProjectView:
        project = self._membership.owned_project(user_id, project_id)
        return self._view(project, self._membership.tree(user_id))

    def create_project(self, dto: CreateProjectDTO) -> ProjectView:
        if dto.parent_project_id is not None:
            self._membership.owned_project(dto.user_id, dto.parent_project_id)
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
        self._session.commit()
        return self._view(saved, self._membership.tree(dto.user_id))

    def update_project(self, project_id: int, user_id: int, dto: UpdateProjectDTO) -> ProjectView:
        project = self._membership.owned_project(user_id, project_id)
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
        saved = self._repo.save(project)
        self._session.commit()
        return self._view(saved, self._membership.tree(user_id))

    def move_project(self, project_id: int, user_id: int, dto: MoveProjectDTO) -> ProjectView:
        """親を替える・兄弟の中で並べ替える。⚠ 自分と自分の子孫の下へは移さない（環になる）。"""
        project = self._membership.owned_project(user_id, project_id)
        new_parent = dto.parent_project_id
        if new_parent is not None:
            self._membership.owned_project(user_id, new_parent)
        tree = self._membership.tree(user_id)
        if tree.would_cycle(project_id, new_parent):
            raise ProjectCycleError()

        old_parent = project.parent_project_id
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
        self._membership.owned_project(user_id, project_id)
        if self._repo.has_contents(project_id):
            raise ProjectNotEmptyError()
        self._repo.delete(project_id)
        self._session.commit()

    def _view(self, project: Project, tree: ProjectTree) -> ProjectView:
        return ProjectView(project, tree.path(project.id) or project.name)


__all__ = ["ProjectUseCases", "ProjectView"]
