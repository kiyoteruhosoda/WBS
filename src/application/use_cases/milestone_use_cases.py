from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.milestone_dto import CreateMilestoneDTO, UpdateMilestoneDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.ownership import owned_by
from src.domain.entities.milestone import Milestone
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository


class MilestoneUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyMilestoneRepository(session)
        self._session = session

    def list_milestones(self, user_id: int) -> list[Milestone]:
        return self._repo.find_all(user_id)

    def get_milestone(self, milestone_id: int, user_id: int) -> Milestone:
        return self._owned(milestone_id, user_id)

    def create_milestone(self, dto: CreateMilestoneDTO) -> Milestone:
        m = Milestone(id=None, user_id=dto.user_id, name=dto.name, due_date=dto.due_date, description=dto.description)
        saved = self._repo.save(m)
        self._session.commit()
        return saved

    def update_milestone(self, milestone_id: int, user_id: int, dto: UpdateMilestoneDTO) -> Milestone:
        m = self._owned(milestone_id, user_id)
        if dto.name is not UNSET:
            m.name = dto.name
        if dto.due_date is not UNSET:
            m.due_date = dto.due_date
        if dto.description is not UNSET:
            m.description = dto.description
        saved = self._repo.save(m)
        self._session.commit()
        return saved

    def delete_milestone(self, milestone_id: int, user_id: int) -> None:
        self._owned(milestone_id, user_id)
        self._repo.soft_delete(milestone_id)
        self._session.commit()

    def _owned(self, milestone_id: int, user_id: int) -> Milestone:
        return owned_by(
            self._repo.find_by_id(milestone_id), user_id,
            resource="Milestone", resource_id=milestone_id,
        )
