"""ほかのアプリのサーバーが、利用者の代わりに読み書きする口（ADR-0056）。

- 担当タスク: ``GET /machine/assigned-tasks``（Tracker のタスクを選ぶ欄。task #539）

⚠ **機械のトークン（``Authorization: Bearer``）だけ**を受ける。宛名は ``MACHINE_AUDIENCE``、
読み書きしてよいアプリは ``MACHINE_READER_CLIENT_IDS``。利用者は ``issuer`` と ``subject`` で渡す。
"""

from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.presentation.api.dependencies import MachineReaderUserDep, TaskUseCasesDep
from src.presentation.api.schemas.types import UtcDatetime

router = APIRouter(prefix="/machine", tags=["machine"])


class AssignedTaskResponse(BaseModel):
    """担当タスクの 1 件（Tracker はこれでタスクの写しを足す・直す）。"""

    id: int = Field(description="WBS のタスクの id（Tracker の写しの wbs_task_id）")
    title: str
    project_path: str | None = Field(description="プロジェクトの道筋（「親 / 子」）。未分類は null")
    updated_at: UtcDatetime | None = None


class AssignedTasksResponse(BaseModel):
    tasks: list[AssignedTaskResponse]


@router.get("/assigned-tasks", response_model=AssignedTasksResponse)
def list_assigned_tasks(user: MachineReaderUserDep, uc: TaskUseCasesDep) -> AssignedTasksResponse:
    """担当が本人で、本人に見えて、まだ作業できる（完了・中止・アーカイブでない）タスク（ADR-0056 決定 2）。

    ここに無い写しは、Tracker が閉じる（担当が外れた・終わった）。利用者が WBS に居なければ 404、
    止めた利用者は 403。トークンが合わなければ 401。
    """
    return AssignedTasksResponse(
        tasks=[
            AssignedTaskResponse(
                id=task.id or 0, title=task.title, project_path=path, updated_at=task.updated_at
            )
            for task, path in uc.assigned_open_tasks(user.user_id)
        ]
    )
