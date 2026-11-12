"""A resident thread that repeats the same job at a fixed interval.

This app has no scheduling infrastructure (no Celery, no cron). For jobs that need
**something only the web process holds** -- the key for talking to the IdP --
this is the minimal in-process mechanism.

⚠ **Pass only idempotent jobs.** The web app runs with multiple workers, so the same job
runs once per process at the same time. There is no locking.

It does not compare times, so it is unaffected by clock skew between the container and the DB.
"""

from __future__ import annotations

import logging
import threading
from collections.abc import Callable

logger = logging.getLogger(__name__)


class IntervalWorker:
    """Thread that calls *job* once after *first_delay_seconds*, then every *interval_seconds*."""

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
        """Start the thread (calling it twice still runs only one)."""
        if self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name=self._name, daemon=True)
        self._thread.start()
        logger.info(
            "periodic job started",
            extra={
                "event": "scheduling.worker.start",
                "worker": self._name,
                "interval_seconds": self._interval_seconds,
            },
        )

    def stop(self) -> None:
        self._stop_event.set()

    def run_once(self) -> None:
        """Run the job once. Never raises, even on failure.

        A single failure (e.g. a transient DB outage) must not kill the thread. If it died, later runs would
        silently stop and nobody would notice until the process restarts.
        """
        try:
            self._job()
        except Exception:
            logger.warning(
                "periodic job failed",
                exc_info=True,
                extra={"event": "scheduling.worker.failed", "worker": self._name},
            )

    def _run(self) -> None:
        # Run once shortly after startup. Even with a long interval, a restart runs it right away.
        # Not immediately, so it does not compete with startup work.
        if self._stop_event.wait(self._first_delay_seconds):
            return
        self.run_once()
        while not self._stop_event.wait(self._interval_seconds):
            self.run_once()


__all__ = ["IntervalWorker"]
