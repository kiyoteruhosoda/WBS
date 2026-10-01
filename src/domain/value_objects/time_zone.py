"""予定が属するタイムゾーン（IANA 名）。

保持は UTC の瞬間なので、このタイムゾーンは「どのローカル日か」を決めるための
メタデータ（繰り返しの評価・営業日シフト・表示の既定）として使う。
移植元 NolumiaScheduler の ``TimeZoneId``（docs/time-model.md §4-3）。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from src.domain.exceptions import ValidationError


@dataclass(frozen=True)
class TimeZoneId:
    name: str
    _zone: ZoneInfo = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.name or not self.name.strip():
            raise ValidationError("time zone must not be empty")
        try:
            zone = ZoneInfo(self.name)
        except (ZoneInfoNotFoundError, ValueError) as exc:
            raise ValidationError(f"unknown time zone: {self.name}") from exc
        object.__setattr__(self, "_zone", zone)

    @property
    def zone(self) -> ZoneInfo:
        return self._zone

    def __str__(self) -> str:
        return self.name


__all__ = ["TimeZoneId"]
