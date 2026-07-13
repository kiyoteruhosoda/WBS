from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.work_log_dto import CreateWorkLogDTO, UpdateWorkLogDTO
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import NotFoundError
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository


class WorkLogUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyWorkLogRepository(session)
        self._session = session

    def list_work_logs(self, task_id: int) -> list[WorkLog]:
        return self._repo.find_by_task(task_id)

    def get_work_log(self, work_log_id: int) -> WorkLog:
        wl = self._repo.find_by_id(work_log_id)
        if wl is None:
            raise NotFoundError("WorkLog", work_log_id)
        return wl

    def create_work_log(self, dto: CreateWorkLogDTO) -> WorkLog:
        wl = WorkLog(id=None, user_id=dto.user_id, task_id=dto.task_id, work_date=dto.work_date, hours=dto.hours, memo=dto.memo)
        saved = self._repo.save(wl)
        self._session.commit()
        return saved

    def update_work_log(self, work_log_id: int, dto: UpdateWorkLogDTO) -> WorkLog:
        wl = self._repo.find_by_id(work_log_id)
        if wl is None:
            raise NotFoundError("WorkLog", work_log_id)
        if dto.work_date is not None:
            wl.work_date = dto.work_date
        if dto.hours is not None:
            wl.hours = dto.hours
        if dto.memo is not None:
            wl.memo = dto.memo
        saved = self._repo.save(wl)
        self._session.commit()
        return saved

    def delete_work_log(self, work_log_id: int) -> None:
        wl = self._repo.find_by_id(work_log_id)
        if wl is None:
            raise NotFoundError("WorkLog", work_log_id)
        self._repo.soft_delete(work_log_id)
        self._session.commit()
