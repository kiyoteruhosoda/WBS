from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.domain.entities.milestone import Milestone
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.infrastructure.database.models import MilestoneModel


class SqlAlchemyMilestoneRepository(MilestoneRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, milestone_id: int) -> Milestone | None:
        model = self._session.get(MilestoneModel, milestone_id)
        if model is None or model.deleted_at is not None:
            return None
        return self._to_entity(model)

    def find_all(self, user_id: int) -> list[Milestone]:
        stmt = select(MilestoneModel).where(
            MilestoneModel.user_id == user_id,
            MilestoneModel.deleted_at.is_(None),
        ).order_by(MilestoneModel.due_date.nullslast(), MilestoneModel.id)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, milestone: Milestone) -> Milestone:
        if milestone.id is None:
            model = MilestoneModel(
                user_id=milestone.user_id,
                name=milestone.name,
                due_date=milestone.due_date,
                description=milestone.description,
            )
            self._session.add(model)
            self._session.flush()
            return self._to_entity(model)
        else:
            model = self._session.get(MilestoneModel, milestone.id)
            if model is None:
                raise ValueError(f"Milestone {milestone.id} not found")
            model.name = milestone.name
            model.due_date = milestone.due_date
            model.description = milestone.description
            model.updated_at = datetime.utcnow()
            self._session.flush()
            return self._to_entity(model)

    def soft_delete(self, milestone_id: int) -> None:
        model = self._session.get(MilestoneModel, milestone_id)
        if model:
            model.deleted_at = datetime.utcnow()
            self._session.flush()

    def _to_entity(self, model: MilestoneModel) -> Milestone:
        return Milestone(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            due_date=model.due_date,
            description=model.description,
            deleted_at=model.deleted_at,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
