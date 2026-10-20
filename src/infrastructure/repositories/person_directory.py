"""``PersonDirectory`` の実装（task #544 / ADR-0055）。"""

from __future__ import annotations

from sqlalchemy import exists, select
from sqlalchemy.orm import Session

from src.application.ports.person_directory import Person
from src.infrastructure.database.models import FederatedIdentityModel, UserModel


class SqlAlchemyPersonDirectory:
    def __init__(self, session: Session, *, require_identity: bool) -> None:
        self._session = session
        # SSO（AUTH_MODE=oidc）では assay の結び付きのある人だけを候補にする
        self._require_identity = require_identity

    def choosable(self) -> list[Person]:
        stmt = select(UserModel).where(UserModel.is_active.is_(True))
        if self._require_identity:
            stmt = stmt.where(
                exists().where(FederatedIdentityModel.user_id == UserModel.id)
            )
        stmt = stmt.order_by(UserModel.display_name, UserModel.id)
        return [self._person(m) for m in self._session.scalars(stmt)]

    def by_ids(self, user_ids: set[int]) -> dict[int, Person]:
        if not user_ids:
            return {}
        stmt = select(UserModel).where(UserModel.id.in_(user_ids))
        return {m.id: self._person(m) for m in self._session.scalars(stmt)}

    @staticmethod
    def _person(model: UserModel) -> Person:
        return Person(id=model.id, display_name=model.display_name, email=model.email)


__all__ = ["SqlAlchemyPersonDirectory"]
