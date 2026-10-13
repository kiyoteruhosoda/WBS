"""休み（WinTrack、task #392 / ADR-0048）。

打刻とは別に持つ（打刻を切り抜かない。走っている打刻も走ったまま）。**実績の長さは打刻の長さから、
その打刻と重なる休みの時間を引いたもの**（締めの確定・締めの画面・実績の表示で同じ計算。
``daily_time_allocation``）。いまは WinTrack が送る自動の休み（``source=auto``）だけ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class WorkBreakSource(StrEnum):
    """DB へはこの文字列で入れる（ネイティブ ENUM にしない）。"""

    AUTO = "auto"
    """PC の自動記録（WinTrack）が送った。日ごとに丸ごと置き換わる。"""


@dataclass
class WorkBreak:
    id: int | None
    user_id: int
    started_at: datetime
    ended_at: datetime
    source: WorkBreakSource = WorkBreakSource.AUTO
    created_at: datetime | None = None
