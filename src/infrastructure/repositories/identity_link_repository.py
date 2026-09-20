from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from src.domain.entities.identity_link import IdentityLink
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.infrastructure.database.models import FederatedIdentityModel


class SqlAlchemyIdentityLinkRepository(IdentityLinkRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_for_issuer(self, issuer: str) -> list[IdentityLink]:
        stmt = select(FederatedIdentityModel).where(FederatedIdentityModel.issuer == issuer)
        return [
            IdentityLink(
                id=model.id,
                user_id=model.user_id,
                identity=FederatedIdentity(issuer=model.issuer, subject=model.subject),
            )
            for model in self._session.scalars(stmt)
        ]

    def unlink(self, link_id: int) -> None:
        self._session.execute(
            delete(FederatedIdentityModel).where(FederatedIdentityModel.id == link_id)
        )
        self._session.commit()
