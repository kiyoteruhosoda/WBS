"""Grant or revoke the mark for people who can create top-level projects (task #734 / ADR-0065).

There is no screen (grant/revoke via scripts/grant_project_creator.py). The mark is ``users.can_create_projects``.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import NotFoundError
from src.infrastructure.repositories.user_account_repository import SqlAlchemyUserAccountRepository


class ProjectCreatorUseCases:
    def __init__(self, session: Session) -> None:
        self._users = SqlAlchemyUserAccountRepository(session)

    def allow(self, email: str, allowed: bool = True) -> UserAccount:
        """Grant the mark to the person given by email (revoke with ``allowed=False``). 404 for someone who has never signed in to WBS."""
        user = self._users.find_by_email(email)
        if user is None:
            raise NotFoundError("User", email)
        if user.can_create_projects == allowed:
            return user
        user.can_create_projects = allowed
        return self._users.save(user)


__all__ = ["ProjectCreatorUseCases"]
