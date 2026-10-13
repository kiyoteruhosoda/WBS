"""例外作業（``override``）で切り抜いた手の打刻の記録（WinTrack、task #386 / ADR-0045）。

自動の打刻が手の打刻に勝つ、ただ 1 つの場面なので、**切り抜く前の手の打刻が何だったか**を残す。
1 行が 1 本の手の打刻への 1 回の切り抜き。打刻が後で直されたり消されたりしても、この行は残る。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


class CarvingAction(StrEnum):
    """切り抜きで手の打刻に起きたこと（DB へはこの文字列で入れる）。"""

    SHRUNK_END = "shrunk_end"
    """終わりを例外作業の始まりまで縮めた。"""
    SHRUNK_START = "shrunk_start"
    """始まりを例外作業の終わりまでずらした（走っている打刻なら、そのまま走り続ける）。"""
    SPLIT = "split"
    """例外作業をまたいでいたので、前後の 2 本に分けた。"""
    REMOVED = "removed"
    """例外作業の中に収まっていたので消した。"""
    RESTARTED = "restarted"
    """走っている打刻を例外作業の始まりで閉じ、終わりから同じタスクで走らせ直した。"""


@dataclass
class TimeEntryCarving:
    id: int | None
    user_id: int
    # 切り抜いた例外作業の送り手の ID
    client_ref: str
    # 切り抜かれた手の打刻（消したときも、元の id を残す）
    time_entry_id: int
    action: CarvingAction
    # 切り抜く前の手の打刻
    task_id: int | None
    source: str
    memo: str | None
    started_at: datetime
    ended_at: datetime | None
    # 切り抜いた例外作業の区間
    window_started_at: datetime
    window_ended_at: datetime
    carved_at: datetime
