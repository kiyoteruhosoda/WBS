"""だれに何が見えるか（task #544 / ADR-0055）。タスク・プロジェクト・マイルストーン・依存の倉庫が共有する述語。

- プロジェクト: 自分がメンバーになっている根と、その子孫全部（再帰 CTE で 1 回に引く）
- タスク・マイルストーン: 見えるプロジェクトに入っているもの、または未分類で自分が作ったもの

⚠ **述語はここだけに置く。** 倉庫ごとに書くと、どこか 1 か所の書き漏れで他人の木に届く。
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

#: CTE の名前の通し番号。⚠ 1 つの文の中で述語を 2 度使う（依存の両端・再帰の起点と子）と、
#: 同じ名前の CTE がぶつかって組み立てられない（CompileError）。呼ぶたびに別の名前にする
_cte_numbers = count()


def visible_project_ids(user_id: int) -> Select[tuple[int]]:
    """自分に見えるプロジェクトの id（根のメンバー → 子孫）。``IN`` の右辺に使う。"""
    # UNION（重複を落とす）なので、親子が万一環になっていても止まる
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
    """``task`` は別名（``aliased(TaskModel)``）も渡せる（依存の両端を見るため）。"""
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
