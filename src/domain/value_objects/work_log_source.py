"""実績（``work_logs``）がどこから来たか（``work_logs.source``）。"""

from __future__ import annotations

from enum import StrEnum


class WorkLogSource(StrEnum):
    """DB へはこの文字列で入れる（ネイティブ ENUM にしない）。"""

    MANUAL = "manual"
    """実績の画面・API で手で書いた。"""

    CLOSING = "closing"
    """締めの確定で打刻から作った（task #161 / ADR-0011）。開け直すと消える。"""
