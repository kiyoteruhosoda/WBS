"""時刻の来た通知を、購読している端末へ送る（送る係。task #193 / ADR-0031 の 4・5）。

API のプロセスの定期処理（``src/presentation/api/push_dispatch.py``、60 秒ごと）が呼ぶ。1 周回で:

1. 送れる設定でなければ何もしない（⚠ 鍵が無い配備では通知を送らずに動き続ける。既定は閉じる）
2. 古い送った記録を消す
3. 購読を持つ利用者ごとに、いま送る通知を決め（``PushNoticePlanner``）、送った記録の権利を取れた
   ものだけを、その人の購読へ送る

⚠ **送る前に記録の権利を取る**（``PushDispatchRepository.claim``）。web は複数のワーカーで動き、
この周回もプロセスの数だけ同時に走る。権利を取れたプロセスだけが送るので、同じ通知は 1 度だけ出る。
送るのに失敗しても送り直さない（遅れた通知は意味が薄い。予定は画面とアプリにもある）。

⚠ 宛先は**通知を決めた利用者の購読だけ**（他人の購読へは送らない）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, tzinfo
from typing import Protocol
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.application.dto.closing_dto import PendingClosings
from src.application.ports.occurrence_source import OccurrenceSource
from src.application.ports.push_sender import PushOutcome, PushSender
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.push_notice_planner import PushNoticePlanner, RunningTimer
from src.domain.entities.user_account import UserAccount
from src.domain.exceptions import ValidationError
from src.domain.repositories.push_dispatch_repository import PushDispatchRepository
from src.domain.repositories.push_preferences_repository import PushPreferencesRepository
from src.domain.repositories.push_subscription_repository import PushSubscriptionRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.half_month_period import local_date_of
from src.domain.value_objects.push_notice import PushNotice
from src.domain.value_objects.push_preferences import PushPreferences
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

#: 送った記録を残す長さ。鍵の時刻（予定の回・締めの期間）がこれより古い通知は二度と来ないので
#: 消してよい。止め忘れの打刻は 7 日までしか見ない（``TIMER_LOOKBACK``）。
DISPATCH_RETENTION = timedelta(days=30)


class PendingClosingSource(Protocol):
    """未確定の締めの期間（``ClosingUseCases`` がそのまま満たす）。"""

    def pending(self, user_id: int, time_zone: str) -> PendingClosings: ...


@dataclass
class DispatchReport:
    users: int = 0
    notices: int = 0
    delivered: int = 0
    gone: int = 0
    failed: int = 0
    skipped: bool = False


def _zone_of(user: UserAccount) -> tuple[str, tzinfo]:
    try:
        return user.timezone, ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError):
        return "UTC", ZoneInfo("UTC")


class DispatchPushNotices:
    def __init__(
        self,
        *,
        subscriptions: PushSubscriptionRepository,
        preferences: PushPreferencesRepository,
        dispatches: PushDispatchRepository,
        users: UserAccountRepository,
        occurrences: OccurrenceSource,
        entries: TimeEntryRepository,
        tasks: OwnedTaskLookup,
        closings: PendingClosingSource,
        sender: PushSender,
        unit_of_work: UnitOfWork,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._subscriptions = subscriptions
        self._preferences = preferences
        self._dispatches = dispatches
        self._users = users
        self._occurrences = occurrences
        self._entries = entries
        self._tasks = tasks
        self._closings = closings
        self._sender = sender
        self._uow = unit_of_work
        self._now = now

    def execute(self) -> DispatchReport:
        report = DispatchReport()
        if not self._sender.enabled:
            report.skipped = True
            return report
        now = self._now()
        self._dispatches.purge_before(now - DISPATCH_RETENTION)
        for user_id in self._subscriptions.user_ids_with_subscriptions():
            user = self._users.find_by_id(user_id)
            if user is None or not user.is_active:
                continue
            report.users += 1
            try:
                notices = self._plan(user, self._preferences.get(user_id), now)
            except ValidationError:
                # 1 人の壊れたデータで、ほかの人の通知を止めない
                logger.warning(
                    "通知を決められませんでした",
                    exc_info=True,
                    extra={"event": "push.plan.failed", "user_id": user_id},
                )
                continue
            for notice in notices:
                self._deliver(notice, now, report)
        return report

    def _plan(self, user: UserAccount, preferences: PushPreferences, now: datetime) -> list[PushNotice]:
        assert user.id is not None
        zone_name, zone = _zone_of(user)
        planner = PushNoticePlanner(user.id, zone, user.language)
        notices: list[PushNotice] = []
        if preferences.event_alarm or preferences.routine_start:
            today = local_date_of(now, zone)
            occurrences = self._occurrences.list_occurrence_views(
                user.id, today - timedelta(days=1), today + timedelta(days=1), zone_name
            )
            notices.extend(planner.calendar_notices(occurrences, now, preferences))
        if preferences.timer_left_running:
            entry = self._entries.find_running(user.id)
            running = None
            if entry is not None:
                task = (
                    self._tasks.find_by_id_for_user(entry.task_id, user.id)
                    if entry.task_id is not None
                    else None
                )
                running = RunningTimer(entry, task.title if task is not None else None)
            if (notice := planner.timer_notice(running, now, preferences)) is not None:
                notices.append(notice)
        if preferences.closing_due and (
            notice := planner.closing_notice(self._closings.pending(user.id, zone_name), now, preferences)
        ) is not None:
            notices.append(notice)
        return notices

    def _deliver(self, notice: PushNotice, now: datetime, report: DispatchReport) -> None:
        targets = [
            s
            for s in self._subscriptions.list_for_user(notice.user_id)
            if s.user_id == notice.user_id
            and (s.receives_calendar or not notice.kind.comes_from_calendar)
        ]
        if not targets:
            return
        if not self._dispatches.claim(notice.user_id, notice.kind, notice.key, now):
            return
        report.notices += 1
        for subscription in targets:
            assert subscription.id is not None
            outcome = self._sender.send(subscription, notice)
            if outcome is PushOutcome.DELIVERED:
                report.delivered += 1
                self._subscriptions.mark_sent(subscription.id, now)
            elif outcome is PushOutcome.GONE:
                report.gone += 1
                self._subscriptions.delete(subscription.id)
            else:
                report.failed += 1
        self._uow.commit()


__all__ = ["DISPATCH_RETENTION", "DispatchPushNotices", "DispatchReport", "PendingClosingSource"]
