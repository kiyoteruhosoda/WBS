"""Rules for which project a task or milestone belongs to and who can see it (task #187 / ADR-0024, task #544 / ADR-0055).

- Filtering **includes descendants** (pointing at a project returns everything in all branches below it)
- A milestone can only be attached to tasks of its project or descendants (unclassified milestones can be attached anywhere).
  It is **detached** from tasks that can no longer reach it after their project changed
"""

from __future__ import annotations

from src.domain.entities.project import Project
from src.domain.entities.project_member import ProjectMember
from src.domain.exceptions import NotFoundError, ProjectManagerRequiredError
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.project_member_repository import ProjectMemberRepository
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.project_tree import ProjectTree
from src.domain.value_objects.project_role import ProjectRole


class ProjectMembership:
    def __init__(
        self,
        *,
        projects: ProjectRepository,
        tasks: TaskRepository,
        milestones: MilestoneRepository,
        members: ProjectMemberRepository,
    ) -> None:
        self._projects = projects
        self._tasks = tasks
        self._milestones = milestones
        self._members = members

    def tree(self, user_id: int) -> ProjectTree:
        return ProjectTree(self._projects.find_all(user_id))

    def visible_project(self, user_id: int, project_id: int) -> Project:
        """A project visible to the user (descendants too if a member of the root, ADR-0055). 404 if not visible or missing."""
        project = self._projects.find_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        return project

    def member_ids(self, root_project_id: int) -> set[int]:
        """User ids of the members of the top-level project (ADR-0055)."""
        return {m.user_id for m in self._members.find_by_project(root_project_id)}

    def roles_of(self, user_id: int) -> dict[int, ProjectRole]:
        """The person's role per root they are a member of."""
        return {m.project_id: m.role for m in self._members.find_by_user(user_id)}

    def make_manager(self, user_id: int, root_project_id: int) -> None:
        self._members.save(ProjectMember(id=None, project_id=root_project_id, user_id=user_id, role=ProjectRole.MANAGER))

    def copy_members(self, from_root_id: int, to_project_id: int) -> None:
        """When moving a lower project out to a root, copy the old tree's members as is (who can see it does not change, ADR-0055 decision 6)."""
        for member in self._members.find_by_project(from_root_id):
            self._members.save(
                ProjectMember(
                    id=None, project_id=to_project_id, user_id=member.user_id, role=member.role,
                    daily_hours=member.daily_hours, engagement_percent=member.engagement_percent,
                )
            )

    def forget_members(self, project_id: int) -> None:
        """Delete the rows of a project that is no longer a root (it becomes visible to the target tree's members)."""
        self._members.delete_all(project_id)

    def require_manager(self, user_id: int, root_project_id: int) -> None:
        """403 unless an admin (the caller checks that it is visible)."""
        member = self._members.find(root_project_id, user_id)
        if member is None or not member.is_manager:
            raise ProjectManagerRequiredError()

    def require_manager_to_cross(
        self, user_id: int, from_project_id: int | None, to_project_id: int | None
    ) -> None:
        """When moving across trees (roots), 403 unless an admin of both the source and target roots (ADR-0066).

        Moving within the same tree only needs membership. Unclassified (``None``) belongs to the caller, so that side is not checked.
        """
        tree = self.tree(user_id)
        from_root = None if from_project_id is None else tree.root_of(from_project_id)
        to_root = None if to_project_id is None else tree.root_of(to_project_id)
        if from_root == to_root:
            return
        for root in (from_root, to_root):
            if root is not None:
                self.require_manager(user_id, root)

    def scope_ids(self, user_id: int, project_id: int) -> list[int]:
        """Ids used for filtering (the project and its descendants). 404 for a project that is not visible or missing."""
        ids = self._projects.subtree_ids(user_id, project_id)
        if not ids:
            raise NotFoundError("Project", project_id)
        return ids

    def detach_unreachable_milestones(self, user_id: int) -> list[int]:
        """Detach milestones from tasks that can no longer reach them. Returns the ids of the detached tasks."""
        tree = self.tree(user_id)
        milestone_projects = {
            m.id: m.project_id for m in self._milestones.find_all(user_id) if m.id is not None
        }
        stale = [
            t.id
            for t in self._tasks.find_all(user_id, {})
            if t.id is not None
            and t.milestone_id is not None
            and t.milestone_id in milestone_projects
            and not tree.milestone_reachable(milestone_projects[t.milestone_id], t.project_id)
        ]
        self._tasks.detach_milestone(stale)
        return stale


__all__ = ["ProjectMembership"]
