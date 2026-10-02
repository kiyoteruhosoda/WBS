"""休みの日の一覧の層の 1 日（task #191 の 2 本目、ADR-0029）。終日で、名前は任意。"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

NAME_MAX_LENGTH = 200


@dataclass(frozen=True)
class DayOff:
    calendar_id: int
    day: date
    name: str | None = None


__all__ = ["NAME_MAX_LENGTH", "DayOff"]
