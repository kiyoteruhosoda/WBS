from __future__ import annotations

from decimal import Decimal

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.project_member import ProjectMember
from src.domain.repositories.project_member_repository import ProjectMemberRepository
from src.domain.value_objects.project_role import ProjectRole
from src.infrastructure.database.models import ProjectMemberModel


class SqlAlchemyProjectMemberRepository(ProjectMemberRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_project(self, project_id: int) -> list[ProjectMember]:
        stmt = (
            select(ProjectMemberModel)
            .where(ProjectMemberModel.project_id == project_id)
            .order_by(ProjectMemberModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def find_by_user(self, user_id: int) -> list[ProjectMember]:
        stmt = select(ProjectMemberModel).where(ProjectMemberModel.user_id == user_id)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def find(self, project_id: int, user_id: int) -> ProjectMember | None:
        model = self._model(project_id, user_id)
        return self._to_entity(model) if model is not None else None

    def save(self, member: ProjectMember) -> ProjectMember:
        model = self._model(member.project_id, member.user_id)
        if model is None:
            model = ProjectMemberModel(
                project_id=member.project_id,
                user_id=member.user_id,
                role=member.role.value,
                daily_hours=member.daily_hours,
                engagement_percent=member.engagement_percent,
            )
            self._session.add(model)
        else:
            model.role = member.role.value
            model.daily_hours = member.daily_hours
            model.engagement_percent = member.engagement_percent
        self._session.flush()
        return self._to_entity(model)

    def delete(self, project_id: int, user_id: int) -> None:
        self._session.execute(
            delete(ProjectMemberModel).where(
                ProjectMemberModel.project_id == project_id,
                ProjectMemberModel.user_id == user_id,
            )
        )
        self._session.flush()

    def delete_all(self, project_id: int) -> None:
        self._session.execute(
            delete(ProjectMemberModel).where(ProjectMemberModel.project_id == project_id)
        )
        self._session.flush()

    def _model(self, project_id: int, user_id: int) -> ProjectMemberModel | None:
        return self._session.scalar(
            select(ProjectMemberModel).where(
                ProjectMemberModel.project_id == project_id,
                ProjectMemberModel.user_id == user_id,
            )
        )

    @staticmethod
    def _to_entity(model: ProjectMemberModel) -> ProjectMember:
        return ProjectMember(
            id=model.id,
            project_id=model.project_id,
            user_id=model.user_id,
            role=ProjectRole(model.role),
            daily_hours=Decimal(model.daily_hours),
            engagement_percent=model.engagement_percent,
            created_at=model.created_at,
        )
