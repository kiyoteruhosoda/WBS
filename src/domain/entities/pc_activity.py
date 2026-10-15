"""PC を使っていた時間（WinTrack、task #397 / ADR-0049）。

WinTrack が日ごとに送る「手が止まっていない区間（5 分未満の切れ目はつないだもの）」。wbstimer が開始・終了を
押したときに「PC で既に作業していたか」を聞くためだけに読む。**打刻・実績・締めには使わない**（表題やアプリ名も持たない）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime


@dataclass
class PcActivitySpan:
    id: int | None
    user_id: int
    started_at: datetime
    ended_at: datetime


@dataclass
class PcActivityDay:
    """送り手のタイムゾーンでの 1 日。送られるたびに区間を丸ごと置き換え、``updated_at`` を受けた時刻にする。"""

    id: int | None
    user_id: int
    local_date: date
    time_zone: str
    starts_at: datetime
    ends_at: datetime
    updated_at: datetime
    spans: list[PcActivitySpan] = field(default_factory=list)
