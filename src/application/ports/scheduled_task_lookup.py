"""「いまの予定に結ばれたタスク」を引く口（打刻の Start の既定のタスク）。

task #154 の順番は **いまの予定のタスク → 直前の打刻のタスク → 未割当**。予定の表と API は
別の段（task #156 の続き）で作っているので、今は何も返さない ``NoScheduledTask`` を繋いでおき、
予定の表ができたら、その時刻に掛かっている予定の回の ``task_id`` を返す実装に差し替える（ADR-0008）。
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
    """予定の表ができるまでのつなぎ。いつも「予定は無い」と答える。"""

    def task_scheduled_at(self, user_id: int, at: datetime) -> int | None:
        return None


__all__ = ["NoScheduledTask", "ScheduledTaskLookup"]
