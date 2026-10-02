"""購読しているカレンダーを読み込み直す係の足回り（task #196 / ADR-0037）。

``push_dispatch.py`` と同じ形で、API のプロセスの中の ``IntervalWorker`` が回す。⚠ **判断はユースケース
（``CalendarImportUseCases.refresh_due_subscriptions``）にある。** ここが持つのは「いつ走るか」と、この配備の
もの（DB のセッション・URL を読む口・封じる鍵）を渡すことだけ。

⚠ **web のプロセスで動く。** ワーカーが複数なら同じ周回が重なりうるが、間隔の来たものだけを読み、
入れ替えは冪等なので同じ中身になるだけ。⚠ 封じる鍵の無い配備では起動しない（購読がありえない）。
"""

from __future__ import annotations

import logging

from src.application.ports.calendar_feed import CalendarFeedFetcher, FeedUrlCipher
from src.infrastructure.database.session import get_db_session
from src.infrastructure.scheduling.interval_worker import IntervalWorker
from src.presentation.api.dependencies import build_calendar_import_use_cases

logger = logging.getLogger(__name__)

WORKER_NAME = "calendar-feed-refresh"
#: 周回の間隔。読み込み直す間隔（15 分）はユースケースが決め、ここは見回る頻度。
CHECK_INTERVAL_SECONDS = 300.0
#: 起動から最初の 1 回まで。起動処理と取り合わない程度に置く。
FIRST_RUN_DELAY_SECONDS = 60.0


def refresh_once(fetcher: CalendarFeedFetcher, cipher: FeedUrlCipher) -> int:
    """1 周回ぶん走らせる。読み込めた数を返す。"""
    session = get_db_session()
    try:
        refreshed = build_calendar_import_use_cases(
            session, fetcher, cipher
        ).refresh_due_subscriptions()
    finally:
        session.close()
    if refreshed:
        logger.info(
            "購読しているカレンダーを読み込み直しました",
            extra={"event": "calendar.import.refreshed", "calendars": refreshed},
        )
    return refreshed


def start_calendar_feed_refresh_worker(
    fetcher: CalendarFeedFetcher, cipher: FeedUrlCipher
) -> IntervalWorker | None:
    """読み込み直す係を開始する（購読できる配備のときだけ）。"""
    if not cipher.available:
        logger.info(
            "カレンダーの購読は使えません（封じる鍵の設定がありません）",
            extra={"event": "calendar.import.subscription_disabled"},
        )
        return None
    worker = IntervalWorker(
        WORKER_NAME,
        lambda: refresh_once(fetcher, cipher),
        interval_seconds=CHECK_INTERVAL_SECONDS,
        first_delay_seconds=FIRST_RUN_DELAY_SECONDS,
    )
    worker.start()
    return worker


__all__ = ["WORKER_NAME", "refresh_once", "start_calendar_feed_refresh_worker"]
