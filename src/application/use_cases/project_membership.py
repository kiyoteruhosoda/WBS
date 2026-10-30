"""タスク・マイルストーンがどのプロジェクトに属するか・だれに見えるかの決まり（task #187 / ADR-0024・task #544 / ADR-0055）。

- 絞り込みは**子孫を含む**（プロジェクトを指すと、その下の全部の枝のものが出る）
- マイルストーンは、そのプロジェクトか子孫のタスクにだけ付く（未分類のマイルストーンはどこにでも付く）。
  プロジェクトが替わって届かなくなったタスクからは**外す**
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
        """利用者に見えるプロジェクト（根のメンバーなら子孫も。ADR-0055）。見えない・無いものは 404。"""
        project = self._projects.find_by_id_for_user(project_id, user_id)
        if project is None:
            raise NotFoundError("Project", project_id)
        return project

    def member_ids(self, root_project_id: int) -> set[int]:
        """いちばん上のプロジェクトのメンバーの利用者 id（ADR-0055）。"""
        return {m.user_id for m in self._members.find_by_project(root_project_id)}

    def roles_of(self, user_id: int) -> dict[int, ProjectRole]:
        """その人がメンバーになっている根ごとの役割。"""
        return {m.project_id: m.role for m in self._members.find_by_user(user_id)}

    def make_manager(self, user_id: int, root_project_id: int) -> None:
        self._members.save(ProjectMember(id=None, project_id=root_project_id, user_id=user_id, role=ProjectRole.MANAGER))

    def copy_members(self, from_root_id: int, to_project_id: int) -> None:
        """下のプロジェクトを根へ出すとき、元の木のメンバーをそのまま写す（見える人を変えない。ADR-0055 決定 6）。"""
        for member in self._members.find_by_project(from_root_id):
            self._members.save(
                ProjectMember(
                    id=None, project_id=to_project_id, user_id=member.user_id, role=member.role,
                    daily_hours=member.daily_hours, engagement_percent=member.engagement_percent,
                )
            )

    def forget_members(self, project_id: int) -> None:
        """根でなくなったプロジェクトの行を消す（移った先の木のメンバーに見える）。"""
        self._members.delete_all(project_id)

    def require_manager(self, user_id: int, root_project_id: int) -> None:
        """管理者でなければ 403（見えていることは呼ぶ側が確かめる）。"""
        member = self._members.find(root_project_id, user_id)
        if member is None or not member.is_manager:
            raise ProjectManagerRequiredError()

    def require_manager_to_cross(
        self, user_id: int, from_project_id: int | None, to_project_id: int | None
    ) -> None:
        """木（根）をまたいで移すなら、元と先の両方の根の管理者でなければ 403（ADR-0066）。

        同じ木の中の移動はメンバーのまま。未分類（``None``）は自分のものなので、その側は確かめない。
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
        """絞り込みに使う id（自分と子孫）。見えない・無いプロジェクトは 404。"""
        ids = self._projects.subtree_ids(user_id, project_id)
        if not ids:
            raise NotFoundError("Project", project_id)
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
