"""Create, edit, move, archive and delete projects (task #187 / ADR-0024)."""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy.orm import Session

from src.application.dto.project_dto import CreateProjectDTO, MoveProjectDTO, UpdateProjectDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.project import Project, project_code, project_name
from src.domain.exceptions import (
    ProjectCreatorRequiredError,
    ProjectCycleError,
    ProjectNotEmptyError,
)
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
from src.infrastructure.repositories.user_account_repository import SqlAlchemyUserAccountRepository


@dataclass(frozen=True)
class ProjectView:
    """One row of the response: the project and its display path ("parent / child")."""

    project: Project
    path: str
    #: The id of the top-level project and the caller's role there (ADR-0055)
    root_project_id: int
    my_role: ProjectRole | None


class ProjectUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._repo = SqlAlchemyProjectRepository(session)
        self._team_calendar = SqlAlchemyTeamCalendarRepository(session)
        self._users = SqlAlchemyUserAccountRepository(session)
        self._membership = ProjectMembership(
            projects=self._repo,
            tasks=SqlAlchemyTaskRepository(session),
            milestones=SqlAlchemyMilestoneRepository(session),
            members=SqlAlchemyProjectMemberRepository(session),
        )

    def list_projects(self, user_id: int) -> list[ProjectView]:
        """All of them (archived ones too), in tree order (children right after their parent, siblings by position)."""
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
        else:
            # Creating a new root makes its creator an admin, so restrict who can create one (ADR-0065)
            self._require_project_creator(dto.user_id)
        tree = self._membership.tree(dto.user_id)
        project = Project(
            id=None,
            user_id=dto.user_id,
            name=project_name(dto.name),
            parent_project_id=dto.parent_project_id,
            color=dto.color,
            code=project_code(dto.code),
            description=dto.description,
            # Append after the last sibling
            sort_order=len(tree.children_of(dto.parent_project_id)),
        )
        saved = self._repo.save(project)
        if saved.parent_project_id is None and saved.id is not None:
            # The creator of a new root is its admin (ADR-0055 decision 6; who can create one is restricted by ADR-0065)
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
        """Change the parent or reorder among siblings. ⚠ Never move under itself or its own descendants (that would make a cycle)."""
        project = self._membership.visible_project(user_id, project_id)
        new_parent = dto.parent_project_id
        if new_parent is not None:
            self._membership.visible_project(user_id, new_parent)
        tree = self._membership.tree(user_id)
        if tree.would_cycle(project_id, new_parent):
            raise ProjectCycleError()
        old_parent = project.parent_project_id
        if new_parent is not None:
            # Only admins of both the source and target trees may move it under another tree (ADR-0066). Moving a lower project out to a root does not change the tree
            self._membership.require_manager_to_cross(user_id, project_id, new_parent)
        if old_parent is None and new_parent is not None:
            # When a root is moved under another, this tree's members go away and it becomes visible to the target tree's members (ADR-0055 decision 6)
            self._membership.require_manager(user_id, project_id)
            self._membership.forget_members(project_id)
            # Working weekdays belong only to the root; use the target tree's (ADR-0058 decision 2).
            # Holidays stay as this project's own and are added on top of the target tree's holidays (ADR-0059 decision 1)
            self._team_calendar.forget_workdays(project_id)
        elif old_parent is not None and new_parent is None:
            # Moving a lower project out to a root: copy the old tree's members (who can see it does not change)
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
            # Close the gap in the old siblings' order
            self._repo.set_sort_orders(
                [p.id for p in tree.children_of(old_parent) if p.id is not None and p.id != project_id]
            )
            # Tasks that left the branch can no longer reach milestones of their old ancestors (ADR-0024)
            self._membership.detach_unreachable_milestones(user_id)
        self._session.commit()
        return self.get_project(project_id, user_id)

    def delete_project(self, project_id: int, user_id: int) -> None:
        """Delete only an empty project. 409 if it has contents (archive it, or move its contents first)."""
        project = self._membership.visible_project(user_id, project_id)
        if project.parent_project_id is None:
            # Only admins may delete a top-level project (ADR-0055 decision 2)
            self._membership.require_manager(user_id, project_id)
        if self._repo.has_contents(project_id):
            raise ProjectNotEmptyError()
        self._repo.delete(project_id)
        self._session.commit()

    def _require_project_creator(self, user_id: int) -> None:
        user = self._users.find_by_id(user_id)
        if user is None or not user.can_create_projects:
            raise ProjectCreatorRequiredError()

    def _copy_team_calendar(self, from_root_id: int, lineage: list[int], to_project_id: int) -> None:
        """When moving a lower project out to a root, copy the old root's weekdays and the holidays/extra working days it inherited from its ancestors (so forecasts do not change)."""
        workdays = self._team_calendar.workdays(from_root_id)
        if workdays is not None:
            self._team_calendar.set_workdays(to_project_id, workdays)
        own = {d.day for d in self._team_calendar.team_days_off([to_project_id])}
        own |= {d.day for d in self._team_calendar.extra_workdays([to_project_id])}
        ancestors = [p for p in lineage if p != to_project_id]
        # For ancestors' holidays/extra working days, copy the ones that won (the nearer one, ADR-0060)
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
