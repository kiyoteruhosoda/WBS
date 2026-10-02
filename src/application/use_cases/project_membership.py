"""タスク・マイルストーンがどのプロジェクトに属するかの決まり（task #187 / ADR-0024）。

- 絞り込みは**子孫を含む**（プロジェクトを指すと、その下の全部の枝のものが出る）
- マイルストーンは、そのプロジェクトか子孫のタスクにだけ付く（未分類のマイルストーンはどこにでも付く）。
  プロジェクトが替わって届かなくなったタスクからは**外す**
"""

from __future__ import annotations

from src.application.use_cases.ownership import owned_by
from src.domain.entities.project import Project
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.project_tree import ProjectTree


class ProjectMembership:
    def __init__(
        self,
        *,
        projects: ProjectRepository,
        tasks: TaskRepository,
        milestones: MilestoneRepository,
    ) -> None:
        self._projects = projects
        self._tasks = tasks
        self._milestones = milestones

    def tree(self, user_id: int) -> ProjectTree:
        return ProjectTree(self._projects.find_all(user_id))

    def owned_project(self, user_id: int, project_id: int) -> Project:
        return owned_by(
            self._projects.find_by_id(project_id), user_id,
            resource="Project", resource_id=project_id,
        )

    def scope_ids(self, user_id: int, project_id: int) -> list[int]:
        """絞り込みに使う id（自分と子孫）。他人の・無いプロジェクトは 404。"""
        ids = self._projects.subtree_ids(user_id, project_id)
        if not ids:
            self.owned_project(user_id, project_id)  # NotFoundError を上げる
        return ids

    def detach_unreachable_milestones(self, user_id: int) -> list[int]:
        """付いているマイルストーンへ届かなくなったタスクから外す。外したタスクの id を返す。"""
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
