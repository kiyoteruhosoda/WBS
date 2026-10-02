"""取り込んだカレンダーの回 1 つ（ADR-0037）。

外の iCalendar を読み込むときに、繰り返しを展開して回ごとに持つ（読み込み直すたびに丸ごと入れ替える）。

- 時刻のある回: 開始と終わりの UTC の瞬間（naive。``src.shared.clock`` と同じ約束）
- 終日の回: 開始日と終わりの日（終わりの日は含まない。iCalendar の ``DTEND`` と同じ）
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from src.domain.exceptions import ValidationError

TITLE_MAX_LENGTH = 500
LOCATION_MAX_LENGTH = 500


@dataclass(frozen=True)
class ImportedOccurrence:
    title: str
    location: str | None = None
    start_utc: datetime | None = None
    end_utc: datetime | None = None
    start_date: date | None = None
    end_date: date | None = None
    """終日の回の終わりの日（含まない）。"""

    def __post_init__(self) -> None:
        timed = self.start_utc is not None and self.end_utc is not None
        all_day = self.start_date is not None and self.end_date is not None
        if timed == all_day:
            raise ValidationError("an imported occurrence is either timed or all-day")
        if timed and self.end_utc < self.start_utc:  # type: ignore[operator]
            raise ValidationError("an imported occurrence cannot end before it starts")
        if all_day and self.end_date <= self.start_date:  # type: ignore[operator]
            raise ValidationError("an all-day imported occurrence needs at least one day")

    @property
    def is_all_day(self) -> bool:
        return self.start_date is not None

    @classmethod
    def timed(
        cls, title: str, start_utc: datetime, end_utc: datetime, location: str | None = None
    ) -> ImportedOccurrence:
        return cls(
            title=_clip(title, TITLE_MAX_LENGTH), location=_clip_optional(location),
            start_utc=start_utc, end_utc=end_utc,
        )

    @classmethod
    def all_day(
        cls, title: str, start_date: date, end_date: date, location: str | None = None
    ) -> ImportedOccurrence:
        return cls(
            title=_clip(title, TITLE_MAX_LENGTH), location=_clip_optional(location),
            start_date=start_date, end_date=end_date,
        )


def _clip(text: str, limit: int) -> str:
    return text.strip()[:limit]


def _clip_optional(text: str | None) -> str | None:
    if text is None:
        return None
    clipped = _clip(text, LOCATION_MAX_LENGTH)
    return clipped or None


__all__ = ["LOCATION_MAX_LENGTH", "TITLE_MAX_LENGTH", "ImportedOccurrence"]
