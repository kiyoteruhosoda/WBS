from __future__ import annotations

from sqlalchemy.orm import Session

from src.domain.repositories.push_preferences_repository import PushPreferencesRepository
from src.domain.value_objects.push_preferences import PushPreferences
from src.infrastructure.database.models import PushPreferencesModel
from src.shared.clock import utcnow


class SqlAlchemyPushPreferencesRepository(PushPreferencesRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get(self, user_id: int) -> PushPreferences:
        model = self._session.get(PushPreferencesModel, user_id)
        if model is None:
            return PushPreferences()
        return PushPreferences(
            event_alarm=model.event_alarm,
            routine_start=model.routine_start,
            timer_left_running=model.timer_left_running,
            closing_due=model.closing_due,
            timer_left_running_hours=model.timer_left_running_hours,
        )

    def save(self, user_id: int, preferences: PushPreferences) -> None:
        model = self._session.get(PushPreferencesModel, user_id)
        if model is None:
            model = PushPreferencesModel(user_id=user_id)
            self._session.add(model)
        model.event_alarm = preferences.event_alarm
        model.routine_start = preferences.routine_start
        model.timer_left_running = preferences.timer_left_running
        model.closing_due = preferences.closing_due
        model.timer_left_running_hours = preferences.timer_left_running_hours
        model.updated_at = utcnow()
        self._session.flush()
