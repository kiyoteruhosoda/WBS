"""Endpoints another app's server uses to read/write on a user's behalf (ADR-0056).

- Assigned tasks: ``GET /machine/assigned-tasks`` (the task picker in Tracker. task #539)
- Visible projects: ``GET /machine/projects`` (the project picker when adding a task in Tracker)
- Closed time: ``PUT`` / ``DELETE /machine/closed-periods/{first_day}`` (confirming/cancelling a Tracker closing. task #540)

⚠ Accepts **only machine tokens (``Authorization: Bearer``)**. The audience is ``MACHINE_AUDIENCE``,
apps allowed to read/write are ``MACHINE_READER_CLIENT_IDS``. The user is passed as ``issuer`` and ``subject``.
Write endpoints are recorded in ``machine_operation_logs``; read endpoints only in the app log (task #802 / ADR-0068).
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
    """One assigned task (Tracker uses it to add/update its copy of the task)."""

    id: int = Field(description="WBS task id (wbs_task_id of the Tracker copy)")
    title: str
    project_path: str | None = Field(description="Project path ('parent / child'). null if uncategorized")
    project_id: int | None = Field(
        default=None, description="WBS project id (wbs_project_id of the Tracker copy. task #711). null if uncategorized"
    )
    updated_at: UtcDatetime | None = None


class AssignedTasksResponse(BaseModel):
    tasks: list[AssignedTaskResponse]


@router.get("/assigned-tasks", response_model=AssignedTasksResponse)
def list_assigned_tasks(user: MachineReaderUserDep, uc: TaskUseCasesDep) -> AssignedTasksResponse:
    """Tasks assigned to the user, visible to them, and still workable (not done, cancelled or archived) (ADR-0056 decision 2).

    Copies not listed here are closed by Tracker (unassigned or finished). 404 if the user is not in WBS,
    403 for a disabled user. 401 if the token does not match.
    """
    return AssignedTasksResponse(
        tasks=[
            AssignedTaskResponse(
                id=task.id or 0,
                title=task.title,
                project_path=path,
                project_id=task.project_id if path is not None else None,
                updated_at=task.updated_at,
            )
            for task, path in uc.assigned_open_tasks(user.user_id)
        ]
    )


class MachineProjectResponse(BaseModel):
    """One project (Tracker and Scheduler link by this id and show the path as its name)."""

    id: int = Field(description="WBS project id")
    path: str = Field(description="Project path ('parent / child')")
    code: str | None = Field(description="Project code (optional, not unique)")


class MachineProjectsResponse(BaseModel):
    projects: list[MachineProjectResponse] = Field(description="In tree order")


@router.get("/projects", response_model=MachineProjectsResponse)
def list_projects(user: MachineReaderUserDep, uc: TaskUseCasesDep) -> MachineProjectsResponse:
    """Projects visible to the user and not archived (ADR-0056 decision 4).

    Shown in the project pickers of Tracker and Scheduler. 404 if the user is not in WBS,
    403 for a disabled user. 401 if the token does not match.
    """
    return MachineProjectsResponse(
        projects=[
            MachineProjectResponse(id=project.id or 0, path=path, code=project.code)
            for project, path in uc.open_projects(user.user_id)
        ]
    )


class ClosedTimeEntryRequest(BaseModel):
    wbs_task_id: int
    work_date: dt.date
    seconds: int = Field(ge=0)


class ClosedPeriodRequest(BaseModel):
    """One Tracker closing period (replaces all rows received for this period)."""

    last_day: dt.date
    entries: list[ClosedTimeEntryRequest]


class ClosedPeriodResponse(BaseModel):
    stored: int = Field(description="Number of rows stored (same task and same day are merged)")
    unknown_task_ids: list[int] = Field(description="Tasks missing from WBS or deleted (not accepted)")


class ClosedPeriodRemovedResponse(BaseModel):
    removed: int


@router.put("/closed-periods/{first_day}", response_model=ClosedPeriodResponse)
def put_closed_period(
    first_day: dt.date, body: ClosedPeriodRequest, user: MachineReaderUserDep, db: DbDep
) -> ClosedPeriodResponse:
    """Receive the time of a period confirmed in Tracker (ADR-0056 decision 3). Sending it again gives the same result.

    WBS's own closing rows for the same period (from before the move to Tracker) are removed.
    """
    receipt = TrackerClosedTimeUseCases(db, client_id=user.machine_client_id or "").replace(
        user.user_id,
        first_day,
        body.last_day,
        [ClosedTimeEntry(e.wbs_task_id, e.work_date, e.seconds) for e in body.entries],
    )
    return ClosedPeriodResponse(stored=receipt.stored, unknown_task_ids=receipt.unknown_task_ids)


@router.delete("/closed-periods/{first_day}", response_model=ClosedPeriodRemovedResponse)
def delete_closed_period(
    first_day: dt.date, user: MachineReaderUserDep, db: DbDep
) -> ClosedPeriodRemovedResponse:
    """Remove the time of a period whose closing was reopened in Tracker. 0 if nothing was received (safe to resend)."""
    use_cases = TrackerClosedTimeUseCases(db, client_id=user.machine_client_id or "")
    return ClosedPeriodRemovedResponse(removed=use_cases.remove(user.user_id, first_day))
