"""予定まわりを Scheduler へ移す設定（task #535 / Scheduler の ADR-0054 の段 0・1。WBS の ADR-0054）。

- ``SCHEDULER_CUTOVER_HOLD``: ``true`` の間、予定まわりの書き込みを 503 で待たせる（切り替えの数分だけ）
- ``SCHEDULER_FORWARD_URL``: Scheduler の api のクラスタの中の番地。入っていれば「移転モード」
  （Bearer の予定のアラームは Scheduler へ中継、Cookie の書き込みは 409）
- ``SCHEDULER_PUBLIC_URL``: 画面と 409 の理由に出す Scheduler の番地（既定 ``https://scheduler.nolumia.com``）

⚠ **どれも無ければ今までと何も変わらない**（既定は切）。読み方は Tracker の関所（``TRACKER_*``）と同じで、
互いに独立している（片方だけ移すこともできる）。
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass

DEFAULT_PUBLIC_URL = "https://scheduler.nolumia.com"
#: 503 の ``Retry-After``（秒）。切り替え（写して突き合わせる）に掛かる長さの目安
DEFAULT_RETRY_AFTER_SECONDS = 120


class SchedulerMovePhase(enum.StrEnum):
    #: 移していない（WBS が予定の正本）
    OFF = "off"
    #: 切り替え中（書き込みは 503）
    HOLD = "hold"
    #: 移した（Scheduler が正本。WBS は中継と案内だけ）
    MOVED = "moved"


@dataclass(frozen=True)
class SchedulerMoveSettings:
    cutover_hold: bool = False
    #: 末尾の ``/`` は落とす。空なら移転モードではない
    forward_url: str = ""
    public_url: str = DEFAULT_PUBLIC_URL
    retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS

    @property
    def moved(self) -> bool:
        return bool(self.forward_url)

    @property
    def frozen(self) -> bool:
        """WBS の予定の表に書いてはいけないか（切り替え中か、移した後）。"""
        return self.cutover_hold or self.moved

    @property
    def phase(self) -> SchedulerMovePhase:
        # 切り替えの 503 が先（移転モードと同時に入っていても、書き込みは待たせる）
        if self.cutover_hold:
            return SchedulerMovePhase.HOLD
        return SchedulerMovePhase.MOVED if self.moved else SchedulerMovePhase.OFF


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_scheduler_move_settings() -> SchedulerMoveSettings:
    return SchedulerMoveSettings(
        cutover_hold=_flag("SCHEDULER_CUTOVER_HOLD"),
        forward_url=os.getenv("SCHEDULER_FORWARD_URL", "").strip().rstrip("/"),
        public_url=(
            os.getenv("SCHEDULER_PUBLIC_URL", "").strip().rstrip("/") or DEFAULT_PUBLIC_URL
        ),
    )


__all__ = [
    "DEFAULT_PUBLIC_URL",
    "DEFAULT_RETRY_AFTER_SECONDS",
    "SchedulerMovePhase",
    "SchedulerMoveSettings",
    "load_scheduler_move_settings",
]
