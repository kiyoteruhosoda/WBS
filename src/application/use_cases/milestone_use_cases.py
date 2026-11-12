from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.milestone_dto import CreateMilestoneDTO, UpdateMilestoneDTO
from src.application.dto.unset import UNSET
from src.application.use_cases.project_membership import ProjectMembership
from src.domain.entities.milestone import Milestone
from src.domain.exceptions import NotFoundError
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository


class MilestoneUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyMilestoneRepository(session)
        self._membership = ProjectMembership(
            projects=SqlAlchemyProjectRepository(session),
            tasks=SqlAlchemyTaskRepository(session),
            milestones=self._repo,
            members=SqlAlchemyProjectMemberRepository(session),
        )
        self._session = session

    def list_milestones(
        self, user_id: int, *, project_id: int | None = None, unclassified: bool = False
    ) -> list[Milestone]:
        """``project_id`` filters **including descendant projects** (same as task filtering, ADR-0024)."""
        project_ids = (
            self._membership.scope_ids(user_id, project_id) if project_id is not None else None
        )
        return self._repo.find_all(user_id, project_ids=project_ids, unclassified=unclassified)

    def get_milestone(self, milestone_id: int, user_id: int) -> Milestone:
        return self._owned(milestone_id, user_id)

    def create_milestone(self, dto: CreateMilestoneDTO) -> Milestone:
        if dto.project_id is not None:
            self._membership.visible_project(dto.user_id, dto.project_id)
        m = Milestone(
            id=None, user_id=dto.user_id, name=dto.name, due_date=dto.due_date,
            description=dto.description, project_id=dto.project_id,
        )
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
        moved = dto.project_id is not UNSET and dto.project_id != m.project_id
        if dto.project_id is not UNSET:
            if dto.project_id is not None:
                self._membership.visible_project(user_id, dto.project_id)
            if moved:
                # Only admins of both the source and target trees may take it to another tree (ADR-0066)
                self._membership.require_manager_to_cross(user_id, m.project_id, dto.project_id)
            m.project_id = dto.project_id
        saved = self._repo.save(m)
        if moved:
            # Detach from tasks outside the new project (ADR-0024)
            self._membership.detach_unreachable_milestones(user_id)
        self._session.commit()
        return saved

    def delete_milestone(self, milestone_id: int, user_id: int) -> None:
        self._owned(milestone_id, user_id)
        self._repo.soft_delete(milestone_id)
        self._session.commit()

    def _owned(self, milestone_id: int, user_id: int) -> Milestone:
        milestone = self._repo.find_by_id_for_user(milestone_id, user_id)
        if milestone is None:
            raise NotFoundError("Milestone", milestone_id)
        return milestone
