from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.work_log_dto import CreateWorkLogDTO, UpdateWorkLogDTO
from src.application.use_cases.work_log_use_cases import WorkLogUseCases
from src.presentation.api.dependencies import DbDep
from src.presentation.api.schemas.work_log_schemas import (
    WorkLogCreateRequest,
    WorkLogResponse,
    WorkLogUpdateRequest,
)

router = APIRouter(prefix="/work-logs", tags=["work-logs"])
USER_ID = 1


@router.get("", response_model=list[WorkLogResponse])
def list_work_logs(task_id: int, db: DbDep) -> list[WorkLogResponse]:
    uc = WorkLogUseCases(db)
    return [WorkLogResponse.model_validate(w, from_attributes=True) for w in uc.list_work_logs(task_id)]


@router.post("", response_model=WorkLogResponse, status_code=status.HTTP_201_CREATED)
def create_work_log(body: WorkLogCreateRequest, db: DbDep) -> WorkLogResponse:
    uc = WorkLogUseCases(db)
    dto = CreateWorkLogDTO(user_id=USER_ID, task_id=body.task_id, work_date=body.work_date, hours=body.hours, memo=body.memo)
    return WorkLogResponse.model_validate(uc.create_work_log(dto), from_attributes=True)


@router.get("/{work_log_id}", response_model=WorkLogResponse)
def get_work_log(work_log_id: int, db: DbDep) -> WorkLogResponse:
    uc = WorkLogUseCases(db)
    return WorkLogResponse.model_validate(uc.get_work_log(work_log_id), from_attributes=True)


@router.put("/{work_log_id}", response_model=WorkLogResponse)
def update_work_log(work_log_id: int, body: WorkLogUpdateRequest, db: DbDep) -> WorkLogResponse:
    uc = WorkLogUseCases(db)
    dto = UpdateWorkLogDTO(work_date=body.work_date, hours=body.hours, memo=body.memo)
    return WorkLogResponse.model_validate(uc.update_work_log(work_log_id, dto), from_attributes=True)


@router.delete("/{work_log_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_work_log(work_log_id: int, db: DbDep) -> None:
    uc = WorkLogUseCases(db)
    uc.delete_work_log(work_log_id)
