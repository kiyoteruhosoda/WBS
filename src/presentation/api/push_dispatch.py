"""送る係の足回り（60 秒ごとに、時刻の来た通知を端末へ送る。task #193 / ADR-0031 の 4）。

``sso-reconciliation``（``reconciliation.py``）と同じ形で、API のプロセスの中の
``IntervalWorker`` が回す。⚠ **判断はユースケース（``DispatchPushNotices``）にある。**
ここが持つのは「いつ走るか」と、この配備のもの（DB のセッション・送り口）を渡すことだけ。

⚠ **web のプロセスで動く。** ワーカーが複数なら同じ周回が複数回走るが、送る前に送った記録の
権利を取る（表の一意制約）ので、同じ通知は 1 度だけ出る。⚠ 鍵が無い配備では起動しない。
"""

from __future__ import annotations

import logging

from src.application.ports.push_sender import PushSender
from src.application.use_cases.closing_use_cases import ClosingUseCases
from src.application.use_cases.push_dispatch_use_cases import DispatchPushNotices, DispatchReport
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.closing_period_repository import (
    SqlAlchemyClosingPeriodRepository,
)
from src.infrastructure.repositories.push_dispatch_repository import (
    SqlAlchemyPushDispatchRepository,
)
from src.infrastructure.repositories.push_preferences_repository import (
    SqlAlchemyPushPreferencesRepository,
)
from src.infrastructure.repositories.push_subscription_repository import (
    SqlAlchemyPushSubscriptionRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.time_entry_repository import SqlAlchemyTimeEntryRepository
from src.infrastructure.repositories.user_account_repository import (
    SqlAlchemyUserAccountRepository,
)
from src.infrastructure.repositories.work_log_repository import SqlAlchemyWorkLogRepository
from src.infrastructure.scheduling.interval_worker import IntervalWorker
from src.presentation.api.dependencies import get_calendar_event_use_cases
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

WORKER_NAME = "push-dispatch"
#: 周回の間隔。予定の通知の遅れはこれ以下（遅れても ``DUE_GRACE`` の 5 分までは送る）。
DISPATCH_INTERVAL_SECONDS = 60.0
#: 起動から最初の 1 回まで。起動処理と取り合わない程度に置く。
FIRST_RUN_DELAY_SECONDS = 20.0


def dispatch_once(sender: PushSender) -> DispatchReport:
    """1 周回ぶん走らせる。"""
    session = get_db_session()
    try:
        now = utcnow()
        calendar = get_calendar_event_use_cases(session)
        report = DispatchPushNotices(
            subscriptions=SqlAlchemyPushSubscriptionRepository(session),
            preferences=SqlAlchemyPushPreferencesRepository(session),
            dispatches=SqlAlchemyPushDispatchRepository(session),
            users=SqlAlchemyUserAccountRepository(session),
            occurrences=calendar,
            entries=SqlAlchemyTimeEntryRepository(session),
            tasks=SqlAlchemyTaskRepository(session),
            closings=ClosingUseCases(
                periods=SqlAlchemyClosingPeriodRepository(session),
                entries=SqlAlchemyTimeEntryRepository(session),
                work_logs=SqlAlchemyWorkLogRepository(session),
                tasks=SqlAlchemyTaskRepository(session),
                unit_of_work=session,
                now=lambda: now,
            ),
            sender=sender,
            unit_of_work=session,
            now=lambda: now,
        ).execute()
    finally:
        session.close()
    if report.notices:
        logger.info(
            "端末へ通知を送りました",
            extra={
                "event": "push.dispatch.finished",
                "notices": report.notices,
                "delivered": report.delivered,
                "gone": report.gone,
                "failed": report.failed,
            },
        )
    return report


def start_push_dispatch_worker(sender: PushSender) -> IntervalWorker | None:
    """送る係を開始する（送れる設定のときだけ）。"""
    if not sender.enabled:
        logger.info(
            "端末への通知は送りません（鍵の設定がありません）",
            extra={"event": "push.dispatch.disabled"},
        )
        return None
    worker = IntervalWorker(
        WORKER_NAME,
        lambda: dispatch_once(sender),
        interval_seconds=DISPATCH_INTERVAL_SECONDS,
        first_delay_seconds=FIRST_RUN_DELAY_SECONDS,
    )
    worker.start()
    return worker


__all__ = [
    "DISPATCH_INTERVAL_SECONDS",
    "WORKER_NAME",
    "dispatch_once",
    "start_push_dispatch_worker",
]
