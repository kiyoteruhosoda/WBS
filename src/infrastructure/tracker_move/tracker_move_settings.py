"""打刻まわりを Tracker へ移す設定（task #526 / ADR-0053 の段 0・1。WBS の ADR-0053）。

- ``TRACKER_CUTOVER_HOLD``: ``true`` の間、打刻まわりの書き込みを 503 で待たせる（切り替えの数分だけ）
- ``TRACKER_FORWARD_URL``: Tracker の api のクラスタの中の番地。入っていれば「移転モード」
  （Bearer の打刻まわりは Tracker へ中継、Cookie の書き込みは 409）
- ``TRACKER_PUBLIC_URL``: 画面と 409 の理由に出す Tracker の番地（既定 ``https://tracker.nolumia.com``）

⚠ **どれも無ければ今までと何も変わらない**（既定は切）。
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass

DEFAULT_PUBLIC_URL = "https://tracker.nolumia.com"
#: 503 の ``Retry-After``（秒）。切り替え（写して突き合わせる）に掛かる長さの目安
DEFAULT_RETRY_AFTER_SECONDS = 120


class TrackerMovePhase(enum.StrEnum):
    #: 移していない（WBS が打刻の正本）
    OFF = "off"
    #: 切り替え中（書き込みは 503）
    HOLD = "hold"
    #: 移した（Tracker が正本。WBS は中継と案内だけ）
    MOVED = "moved"


@dataclass(frozen=True)
class TrackerMoveSettings:
    cutover_hold: bool = False
    #: 末尾の ``/`` は落とす。空なら移転モードではない
    forward_url: str = ""
    public_url: str = DEFAULT_PUBLIC_URL
    retry_after_seconds: int = DEFAULT_RETRY_AFTER_SECONDS

    @property
    def moved(self) -> bool:
        return bool(self.forward_url)

    @property
    def phase(self) -> TrackerMovePhase:
        # 切り替えの 503 が先（移転モードと同時に入っていても、書き込みは待たせる）
        if self.cutover_hold:
            return TrackerMovePhase.HOLD
        return TrackerMovePhase.MOVED if self.moved else TrackerMovePhase.OFF


def _flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def load_tracker_move_settings() -> TrackerMoveSettings:
    return TrackerMoveSettings(
        cutover_hold=_flag("TRACKER_CUTOVER_HOLD"),
        forward_url=os.getenv("TRACKER_FORWARD_URL", "").strip().rstrip("/"),
        public_url=(os.getenv("TRACKER_PUBLIC_URL", "").strip().rstrip("/") or DEFAULT_PUBLIC_URL),
    )


__all__ = [
    "DEFAULT_PUBLIC_URL",
    "DEFAULT_RETRY_AFTER_SECONDS",
    "TrackerMovePhase",
    "TrackerMoveSettings",
    "load_tracker_move_settings",
]
