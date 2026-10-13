"""打刻がどこから来たか（``time_entries.source``）。"""

from __future__ import annotations

from enum import StrEnum


class TimeEntrySource(StrEnum):
    """DB へはこの文字列で入れる（ネイティブ ENUM にしない）。"""

    TIMER = "timer"
    """Start / Stop のボタンで作られた。"""

    MANUAL = "manual"
    """締めの画面で手で足した（#161）。"""

    SPLIT = "split"
    """締めの画面で 1 本を分けてできた（#161）。"""

    SCHEDULE = "schedule"
    """締めの画面で予定の回をそのまま打刻にした（#161）。"""

    AUTO = "auto"
    """PC の自動記録（WinTrack、#379）がまとめて送ってきた。``client_ref`` を持つ。"""
