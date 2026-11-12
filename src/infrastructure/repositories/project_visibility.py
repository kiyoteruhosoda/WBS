"""Who can see what (task #544 / ADR-0055). Predicates shared by the task, project, milestone and dependency repositories.

- Projects: roots the user is a member of, plus all their descendants (fetched in one go with a recursive CTE)
- Tasks and milestones: those in a visible project, or uncategorized ones the user created

⚠ **Keep the predicates here only.** Writing them per repository means one omission somewhere reaches other people's trees.
"""

from __future__ import annotations

from itertools import count

from sqlalchemy import ColumnElement, Select, and_, or_, select

from src.infrastructure.database.models import (
    MilestoneModel,
    ProjectMemberModel,
    ProjectModel,
    TaskModel,
)

#: Sequence number for CTE names. ⚠ Using the predicate twice in one statement (both ends of a dependency, or the
#: recursion's anchor and child) makes same-named CTEs collide and fail to compile (CompileError). Use a new name per call
_cte_numbers = count()


def visible_project_ids(user_id: int) -> Select[tuple[int]]:
    """IDs of the projects visible to the user (root memberships -> descendants). Use as the right-hand side of ``IN``."""
    # UNION (drops duplicates), so it terminates even if parent/child links somehow form a cycle
    base = (
        select(ProjectModel.id)
        .join(ProjectMemberModel, ProjectMemberModel.project_id == ProjectModel.id)
        .where(ProjectMemberModel.user_id == user_id)
        .cte(f"visible_projects_{next(_cte_numbers)}", recursive=True)
    )
    child = select(ProjectModel.id).join(base, ProjectModel.parent_project_id == base.c.id)
    tree = base.union(child)
    return select(tree.c.id)


def project_visible_to(user_id: int) -> ColumnElement[bool]:
    return ProjectModel.id.in_(visible_project_ids(user_id))


def task_visible_to(user_id: int, task: type[TaskModel] = TaskModel) -> ColumnElement[bool]:
    """``task`` may also be an alias (``aliased(TaskModel)``), to check both ends of a dependency."""
    return or_(
        task.project_id.in_(visible_project_ids(user_id)),
        and_(task.project_id.is_(None), task.user_id == user_id),
    )


def milestone_visible_to(user_id: int) -> ColumnElement[bool]:
    return or_(
        MilestoneModel.project_id.in_(visible_project_ids(user_id)),
        and_(MilestoneModel.project_id.is_(None), MilestoneModel.user_id == user_id),
    )


__all__ = [
    "milestone_visible_to",
    "project_visible_to",
    "task_visible_to",
    "visible_project_ids",
]
