"""タスクごとの「予定済みの時間」を引く口（task #159、ADR-0014）。

実装は ``CalendarEventUseCases.scheduled_minutes_by_task``。``get_task_use_cases`` が渡す。
渡されなかったとき（ダッシュボードなど）は、タスクの応答の予定済みの時間を null のままにする。
"""

from __future__ import annotations

from datetime import date
from typing import Protocol


class ScheduledTimeLookup(Protocol):
    def scheduled_minutes_by_task(
        self, user_id: int, from_date: date, to_date: date, time_zone: str
    ) -> dict[int, int]:
        """``[from_date, to_date]``（``time_zone`` のローカル日、両端を含む）に始まる回の長さを、
        結ばれたタスクごとに足した分。

        ⚠ 数えるのは**その利用者の予定**だけ。終日の回とタスクに結ばれていない回は数えない。
        """
        ...


__all__ = ["ScheduledTimeLookup"]
