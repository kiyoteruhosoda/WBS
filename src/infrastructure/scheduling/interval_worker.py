"""一定間隔で同じ仕事を繰り返す常駐スレッド。

このアプリには定期実行の足回りが無い（Celery も cron も持たない）。**web の
プロセスでしか持てないもの**——IdP と話すための鍵——が要る仕事のために、
プロセスの中で回す最小限の口をここに置く。

⚠ **冪等な仕事だけを渡すこと。** web は複数のワーカーで動くため、同じ仕事が
同じ時刻にプロセスの数だけ走る。排他の仕組みは持たない。

時刻の比較をしないので、コンテナと DB の時計のずれに影響されない。
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class IntervalWorker:
    """*first_delay_seconds* 後に 1 回、その後 *interval_seconds* ごとに *job* を呼ぶスレッド。"""

    def __init__(
        self,
        name: str,
        job: Callable[[], object],
        *,
        interval_seconds: float,
        first_delay_seconds: float = 0.0,
    ) -> None:
        self._name = name
        self._job = job
        self._interval_seconds = interval_seconds
        self._first_delay_seconds = first_delay_seconds
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def name(self) -> str:
        return self._name

    def start(self) -> None:
        """スレッドを開始する（二重に呼んでも 1 つだけ動く）。"""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        logger.info(
            "定期処理を開始しました",
            extra={
                "event": "scheduling.worker.start",
                "worker": self._name,
                "interval_seconds": self._interval_seconds,
            },
        )

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> None:
        """仕事を 1 回実行する。失敗しても例外を投げない。

        1 回の失敗（DB の一時障害など）でスレッドを死なせない。死ぬと次の間隔以降が
        黙って止まり、プロセスを再起動するまで誰も気付けない。
        """
        try:
            self._job()
        except Exception:
            logger.warning(
                "定期処理に失敗しました",
                exc_info=True,
                extra={"event": "scheduling.worker.failed", "worker": self._name},
            )

    def _run(self) -> None:
        # 起動の少し後に 1 回走らせる。間隔を長くしても、起動し直せばすぐ実行できる。
        # 直後にしないのは、起動処理と取り合わないため。
        if self._stop_event.wait(self._first_delay_seconds):
            return
        self.run_once()
        while not self._stop_event.wait(self._interval_seconds):
            self.run_once()


__all__ = ["IntervalWorker"]
