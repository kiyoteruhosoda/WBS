from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.work_log_dto import CreateWorkLogDTO, UpdateWorkLogDTO
from src.application.use_cases.ownership import owned_by
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ConflictError, NotFoundError
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository


class WorkLogUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyWorkLogRepository(session)
        self._task_repo = SqlAlchemyTaskRepository(session)
        self._session = session

    def list_work_logs(self, task_id: int, user_id: int) -> list[WorkLog]:
        # 作業ログはタスク単位で引くので、まずそのタスクが自分のものか確かめる
        self._owned_task(task_id, user_id)
        return self._repo.find_by_task(task_id)

    def get_work_log(self, work_log_id: int, user_id: int) -> WorkLog:
        return self._owned(work_log_id, user_id)

    def create_work_log(self, dto: CreateWorkLogDTO) -> WorkLog:
        # 他人のタスクに実績を書き込めないようにする
        self._owned_task(dto.task_id, dto.user_id)
        wl = WorkLog(id=None, user_id=dto.user_id, task_id=dto.task_id, work_date=dto.work_date, hours=dto.hours, memo=dto.memo)
        saved = self._repo.save(wl)
        self._session.commit()
        return saved

    def update_work_log(self, work_log_id: int, user_id: int, dto: UpdateWorkLogDTO) -> WorkLog:
        wl = self._owned(work_log_id, user_id)
        self._ensure_not_from_closing(wl)
        if dto.work_date is not None:
            wl.work_date = dto.work_date
        if dto.hours is not None:
            wl.hours = dto.hours
        if dto.memo is not None:
            wl.memo = dto.memo
        saved = self._repo.save(wl)
        self._session.commit()
        return saved

    def delete_work_log(self, work_log_id: int, user_id: int) -> None:
        self._ensure_not_from_closing(self._owned(work_log_id, user_id))
        self._repo.soft_delete(work_log_id)
        self._session.commit()

    @staticmethod
    def _ensure_not_from_closing(work_log: WorkLog) -> None:
        """締めで作った実績は直接は直させない（打刻を直すには期間を開け直す。ADR-0012）。"""
        if work_log.is_from_closing:
            raise ConflictError(
                "This work log was created by closing a period; reopen the period to change it"
            )

    def _owned(self, work_log_id: int, user_id: int) -> WorkLog:
        return owned_by(
            self._repo.find_by_id(work_log_id), user_id,
            resource="WorkLog", resource_id=work_log_id,
        )

    def _owned_task(self, task_id: int, user_id: int) -> None:
        if self._task_repo.find_by_id_for_user(task_id, user_id) is None:
            raise NotFoundError("Task", task_id)
