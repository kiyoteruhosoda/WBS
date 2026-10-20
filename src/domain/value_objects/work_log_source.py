"""実績（``work_logs``）がどこから来たか（``work_logs.source``）。"""

from __future__ import annotations

from enum import StrEnum


class WorkLogSource(StrEnum):
    """DB へはこの文字列で入れる（ネイティブ ENUM にしない）。"""

    MANUAL = "manual"
    """実績の画面・API で手で書いた。"""

    CLOSING = "closing"
    """締めの確定で打刻から作った（task #161 / ADR-0012）。開け直すと消える。"""

    TRACKER = "tracker"
    """Tracker で締めた時間を受け取った（task #540 / ADR-0056）。Tracker の期間ごとに置き換え、取り消しで消える。"""
