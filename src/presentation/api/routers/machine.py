"""ほかのアプリのサーバーが、利用者の代わりに読み書きする口（ADR-0056）。

- 担当タスク: ``GET /machine/assigned-tasks``（Tracker のタスクを選ぶ欄。task #539）
- 見えるプロジェクト: ``GET /machine/projects``（Tracker でタスクを足すときのプロジェクトを選ぶ欄）
- 締めた時間: ``PUT`` / ``DELETE /machine/closed-periods/{first_day}``（Tracker の締めの確定・取り消し。task #540。
  タスクの無いプロジェクトだけの時間は task #708 / ADR-0064）

⚠ **機械のトークン（``Authorization: Bearer``）だけ**を受ける。宛名は ``MACHINE_AUDIENCE``、
読み書きしてよいアプリは ``MACHINE_READER_CLIENT_IDS``。利用者は ``issuer`` と ``subject`` で渡す。
"""

from __future__ import annotations

import datetime as dt

from fastapi import APIRouter
from pydantic import BaseModel, Field

from src.application.use_cases.tracker_closed_time_use_cases import (
    ClosedTimeEntry,
    TrackerClosedTimeUseCases,
)
from src.presentation.api.dependencies import DbDep, MachineReaderUserDep, TaskUseCasesDep
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


class MachineProjectResponse(BaseModel):
    """プロジェクトの 1 件（Tracker・Scheduler はこの id で結び、道筋を名前として見せる）。"""

    id: int = Field(description="WBS のプロジェクトの id")
    path: str = Field(description="プロジェクトの道筋（「親 / 子」）")
    code: str | None = Field(description="プロジェクトのコード（任意・一意ではない）")


class MachineProjectsResponse(BaseModel):
    projects: list[MachineProjectResponse] = Field(description="木の順")


@router.get("/projects", response_model=MachineProjectsResponse)
def list_projects(user: MachineReaderUserDep, uc: TaskUseCasesDep) -> MachineProjectsResponse:
    """本人に見えて、保管していないプロジェクト（ADR-0056 決定 4）。

    Tracker と Scheduler がプロジェクトを選ぶ欄に出す。利用者が WBS に居なければ 404、
    止めた利用者は 403。トークンが合わなければ 401。
    """
    return MachineProjectsResponse(
        projects=[
            MachineProjectResponse(id=project.id or 0, path=path, code=project.code)
            for project, path in uc.open_projects(user.user_id)
        ]
    )


class ClosedTimeEntryRequest(BaseModel):
    """1 行。``wbs_task_id``（WBS のタスクの時間）か ``wbs_project_id``（タスクの無いプロジェクトの時間）のどちらか 1 つ。"""

    wbs_task_id: int | None = None
    wbs_project_id: int | None = Field(
        default=None, description="タスクに結ばない時間のプロジェクト（ADR-0064）。wbs_task_id と同時には持たない"
    )
    work_date: dt.date
    seconds: int = Field(ge=0)


class ClosedPeriodRequest(BaseModel):
    """Tracker の締めの期間 1 つぶん（この期間に受け取った行をまるごと置き換える）。"""

    last_day: dt.date
    entries: list[ClosedTimeEntryRequest]


class ClosedPeriodResponse(BaseModel):
    stored: int = Field(description="入れた行の数（同じタスク・同じ日はまとめる）")
    unknown_task_ids: list[int] = Field(description="WBS に無い・消したタスク（受け取らなかった）")
    unknown_project_ids: list[int] = Field(
        default_factory=list, description="WBS に無い・本人に見えないプロジェクト（受け取らなかった）"
    )


class ClosedPeriodRemovedResponse(BaseModel):
    removed: int


@router.put("/closed-periods/{first_day}", response_model=ClosedPeriodResponse)
def put_closed_period(
    first_day: dt.date, body: ClosedPeriodRequest, user: MachineReaderUserDep, db: DbDep
) -> ClosedPeriodResponse:
    """Tracker で確定した期間の時間を受け取る（ADR-0056 決定 3）。何度送っても同じ結果になる。

    同じ期間の、WBS 自身の締めの行（Tracker へ移る前のもの）は退ける。タスクの無い行（``wbs_project_id``）は
    そのプロジェクトの実績に数える（ADR-0064）。
    """
    receipt = TrackerClosedTimeUseCases(db).replace(
        user.user_id,
        first_day,
        body.last_day,
        [
            ClosedTimeEntry(e.wbs_task_id, e.work_date, e.seconds, wbs_project_id=e.wbs_project_id)
            for e in body.entries
        ],
    )
    return ClosedPeriodResponse(
        stored=receipt.stored,
        unknown_task_ids=receipt.unknown_task_ids,
        unknown_project_ids=receipt.unknown_project_ids,
    )


@router.delete("/closed-periods/{first_day}", response_model=ClosedPeriodRemovedResponse)
def delete_closed_period(
    first_day: dt.date, user: MachineReaderUserDep, db: DbDep
) -> ClosedPeriodRemovedResponse:
    """Tracker で締めを開け直した期間の時間を退ける。受け取っていなければ 0（何度送ってもよい）。"""
    return ClosedPeriodRemovedResponse(removed=TrackerClosedTimeUseCases(db).remove(user.user_id, first_day))
