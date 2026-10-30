"""いちばん上のプロジェクトを作れる人の印を付け外しする（task #734 / ADR-0065）。

画面は持たない（付け外しは scripts/grant_project_creator.py から）。印は ``users.can_create_projects``。
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
        """メールで指した人の印を付ける（``allowed=False`` で外す）。WBS に入ったことの無い人は 404。"""
        user = self._users.find_by_email(email)
        if user is None:
            raise NotFoundError("User", email)
        if user.can_create_projects == allowed:
            return user
        user.can_create_projects = allowed
        return self._users.save(user)


__all__ = ["ProjectCreatorUseCases"]
