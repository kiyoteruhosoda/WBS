from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.value_objects.push_preferences import PushPreferences


class PushPreferencesRepository(ABC):
    @abstractmethod
    def get(self, user_id: int) -> PushPreferences:
        """行が無ければ既定（``PushPreferences()``）。"""

    @abstractmethod
    def save(self, user_id: int, preferences: PushPreferences) -> None:
        """⚠ 確定（commit）はしない。"""
