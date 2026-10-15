"""PC を使っていた時間（WinTrack → wbstimer、task #397 / ADR-0049）。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.entities.pc_activity import PcActivitySpan


@dataclass(frozen=True)
class PcActivityInPeriod:
    spans: list[PcActivitySpan]
    """``[start, end)`` に掛かる区間（始まりの順）。"""
    updated_at: datetime | None
    """範囲に掛かる日のうち、最後に受けた時刻。1 日も受けていなければ ``None``。"""
