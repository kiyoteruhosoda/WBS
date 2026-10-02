"""表示の組み合わせ（task #191 / ADR-0027）。

どのカレンダーを出すかを名前を付けて覚えておき、1 回で切り替える（例: 「計画」= 全部、
「仕事だけ」= 仕事の予定と休みの層）。当てると、入っているカレンダーだけが表示になる。
入っているカレンダーが後で消えたら、その id は当てるときに飛ばす。
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from src.domain.entities.calendar import NAME_MAX_LENGTH
from src.domain.exceptions import ValidationError


def preset_name(raw: str) -> str:
    name = raw.strip()
    if not name:
        raise ValidationError("a view preset needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a view preset name must be at most {NAME_MAX_LENGTH} characters")
    return name


def _unique(ids: Iterable[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(ids))


@dataclass
class CalendarViewPreset:
    id: int | None
    user_id: int
    name: str
    calendar_ids: tuple[int, ...] = field(default_factory=tuple)
    """表示にするカレンダー（入っていないものは隠す）。"""
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = preset_name(self.name)
        self.calendar_ids = _unique(self.calendar_ids)

    def change(self, *, name: str, calendar_ids: Iterable[int], updated_at: datetime) -> None:
        self.name = preset_name(name)
        self.calendar_ids = _unique(calendar_ids)
        self.updated_at = updated_at

    def forget_calendar(self, calendar_id: int, updated_at: datetime) -> bool:
        """消したカレンダーを外す。外したら ``True``。"""
        if calendar_id not in self.calendar_ids:
            return False
        self.calendar_ids = tuple(i for i in self.calendar_ids if i != calendar_id)
        self.updated_at = updated_at
        return True


__all__ = ["CalendarViewPreset", "preset_name"]
