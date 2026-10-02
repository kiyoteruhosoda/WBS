"""端末への通知の設定（購読の登録・一覧・外す、種類ごとの入り / 切り。task #193 / ADR-0031）。

どの口も ``user_id`` で持ち主を確かめる（他人の購読は「無い」として扱う）。
⚠ 送れる設定でない配備では購読を受け取らない（``ConflictError``）。設定・一覧は読める。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime

from src.application.ports.push_sender import PushSender
from src.application.ports.unit_of_work import UnitOfWork
from src.domain.entities.push_subscription import PushSubscription
from src.domain.exceptions import ConflictError, NotFoundError
from src.domain.repositories.push_preferences_repository import PushPreferencesRepository
from src.domain.repositories.push_subscription_repository import PushSubscriptionRepository
from src.domain.value_objects.push_preferences import PushPreferences
from src.shared.clock import utcnow


@dataclass(frozen=True)
class PushConfig:
    enabled: bool
    #: ブラウザの購読に渡す公開鍵（``applicationServerKey``）。送れないなら ``None``。
    public_key: str | None


class PushSettingsUseCases:
    def __init__(
        self,
        subscriptions: PushSubscriptionRepository,
        preferences: PushPreferencesRepository,
        sender: PushSender,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._subscriptions = subscriptions
        self._preferences = preferences
        self._sender = sender
        self._uow = unit_of_work
        self._now = now

    def config(self) -> PushConfig:
        public_key = self._sender.public_key() if self._sender.enabled else None
        return PushConfig(enabled=public_key is not None, public_key=public_key)

    # ── 購読 ───────────────────────────────────────────────────────────

    def list_subscriptions(self, user_id: int) -> list[PushSubscription]:
        return self._subscriptions.list_for_user(user_id)

    def subscribe(
        self, user_id: int, *, endpoint: str, p256dh: str, auth: str, label: str
    ) -> PushSubscription:
        if not self.config().enabled:
            raise ConflictError("Web Push is not configured on this server")
        subscription = PushSubscription.register(
            user_id=user_id, endpoint=endpoint, p256dh=p256dh, auth=auth, label=label, now=self._now()
        )
        saved = self._subscriptions.save(subscription)
        self._uow.commit()
        return saved

    def set_receives_calendar(
        self, user_id: int, subscription_id: int, receives_calendar: bool
    ) -> PushSubscription:
        self._owned(user_id, subscription_id)
        self._subscriptions.set_receives_calendar(subscription_id, receives_calendar)
        self._uow.commit()
        return self._owned(user_id, subscription_id)

    def unsubscribe(self, user_id: int, subscription_id: int) -> None:
        self._owned(user_id, subscription_id)
        self._subscriptions.delete(subscription_id)
        self._uow.commit()

    def _owned(self, user_id: int, subscription_id: int) -> PushSubscription:
        found = self._subscriptions.find_for_user(subscription_id, user_id)
        if found is None:
            raise NotFoundError("PushSubscription", subscription_id)
        return found

    # ── 種類ごとの入り / 切り ───────────────────────────────────────────

    def get_preferences(self, user_id: int) -> PushPreferences:
        return self._preferences.get(user_id)

    def update_preferences(
        self,
        user_id: int,
        *,
        event_alarm: bool | None = None,
        routine_start: bool | None = None,
        timer_left_running: bool | None = None,
        closing_due: bool | None = None,
        timer_left_running_hours: int | None = None,
    ) -> PushPreferences:
        updated = self._preferences.get(user_id).changed(
            event_alarm=event_alarm,
            routine_start=routine_start,
            timer_left_running=timer_left_running,
            closing_due=closing_due,
            timer_left_running_hours=timer_left_running_hours,
        )
        self._preferences.save(user_id, updated)
        self._uow.commit()
        return updated


__all__ = ["PushConfig", "PushSettingsUseCases"]
