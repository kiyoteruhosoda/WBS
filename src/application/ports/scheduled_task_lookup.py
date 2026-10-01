"""「いまの予定に結ばれたタスク」を引く口（打刻の Start の既定のタスク）。

task #154 の順番は **いまの予定のタスク → 直前の打刻のタスク → 未割当**（ADR-0008）。
実装は ``CalendarEventUseCases.task_scheduled_at``（ADR-0009）で、``get_time_entry_use_cases`` が渡す。
``NoScheduledTask`` は渡されなかったとき（試験など）の既定。
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol


class ScheduledTaskLookup(Protocol):
    def task_scheduled_at(self, user_id: int, at: datetime) -> int | None:
        """``at``（naive な UTC）に掛かっている予定の回に結ばれたタスク。無ければ None。

        ⚠ 返すのは**その利用者のタスク**に限る（打刻の側でも持ち主を確かめ直す）。
        予定が重なっていて候補が複数あるときの選び方は実装が決める。
        """
        ...


class NoScheduledTask:
    """いつも「予定は無い」と答える（予定の口を渡さないときの既定）。"""

    def task_scheduled_at(self, user_id: int, at: datetime) -> int | None:
        return None


__all__ = ["NoScheduledTask", "ScheduledTaskLookup"]
