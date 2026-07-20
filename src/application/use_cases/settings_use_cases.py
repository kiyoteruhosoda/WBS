from __future__ import annotations

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.domain.exceptions import NotFoundError, ValidationError
from src.infrastructure.database.models import UserModel

SUPPORTED_LANGUAGES = ("ja", "en")


class UserSettingsUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_settings(self, user_id: int) -> dict:
        user = self._get_user(user_id)
        return self._to_dict(user)

    def update_settings(self, user_id: int, *, display_name: str | None = None,
                        timezone: str | None = None, language: str | None = None) -> dict:
        user = self._get_user(user_id)
        if display_name is not None:
            if not display_name.strip():
                raise ValidationError("display_name must not be empty")
            user.display_name = display_name.strip()
        if timezone is not None:
            try:
                ZoneInfo(timezone)
            except (ZoneInfoNotFoundError, ValueError) as exc:
                raise ValidationError(f"Unknown timezone: {timezone}") from exc
            user.timezone = timezone
        if language is not None:
            if language not in SUPPORTED_LANGUAGES:
                raise ValidationError(f"Unsupported language: {language}")
            user.language = language
        self._session.commit()
        return self._to_dict(user)

    def _get_user(self, user_id: int) -> UserModel:
        user = self._session.execute(
            select(UserModel).where(UserModel.id == user_id)
        ).scalar_one_or_none()
        if user is None:
            raise NotFoundError("User", user_id)
        return user

    @staticmethod
    def _to_dict(user: UserModel) -> dict:
        return {
            "display_name": user.display_name,
            "timezone": user.timezone,
            "language": user.language,
        }
