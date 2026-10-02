"""予定のカレンダー（task #191 / ADR-0027）。

利用者ごとに複数持つ（名前・色・並び順）。予定はどれか 1 つに属する。Google カレンダーと
同じく、画面に出すかどうか（``is_visible``）はカレンダーごとに持ち、サーバーに覚える
（端末をまたいで同じ）。

各利用者に **既定のカレンダー** が 1 つある（``is_default``）。移行で作り、無い利用者には
初めて使うときに作る。既定のカレンダーは消せない（消したカレンダーの予定の行き先）。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.event_color import EventColorKey

NAME_MAX_LENGTH = 200

DEFAULT_CALENDAR_NAME = "予定"
"""移行・初めて使うときに作る既定のカレンダーの名前（利用者が後から変えられる）。"""


class CalendarKind(enum.StrEnum):
    """カレンダーの種類。いまは予定を入れるカレンダーだけ。"""

    EVENTS = "EVENTS"


def calendar_name(raw: str) -> str:
    """前後の空白を落とした名前。空・長すぎるものは断る。"""
    name = raw.strip()
    if not name:
        raise ValidationError("a calendar needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a calendar name must be at most {NAME_MAX_LENGTH} characters")
    return name


@dataclass
class Calendar:
    id: int | None
    user_id: int
    name: str
    color_key: EventColorKey = EventColorKey.DEFAULT
    """``DEFAULT`` は色の指定なし（予定は結んだタスクのカテゴリの色・標準の予定色で描く）。"""
    sort_order: int = 0
    is_default: bool = False
    is_visible: bool = True
    """カレンダーの画面に出すか。⚠ 出すかどうかだけで、分類・打刻の既定のタスク・「今日」・締めは
    これに関係なく全部のカレンダーを見る。"""
    kind: CalendarKind = CalendarKind.EVENTS
    created_at: datetime | None = None
    updated_at: datetime | None = None

    def __post_init__(self) -> None:
        self.name = calendar_name(self.name)

    @classmethod
    def create(
        cls,
        *,
        user_id: int,
        name: str,
        color_key: EventColorKey,
        sort_order: int,
        created_at: datetime,
        is_default: bool = False,
    ) -> Calendar:
        """新しいカレンダー。最初から表示する（毎回選び直させない）。"""
        return cls(
            id=None, user_id=user_id, name=name, color_key=color_key, sort_order=sort_order,
            is_default=is_default, is_visible=True, created_at=created_at, updated_at=created_at,
        )

    @classmethod
    def create_default(cls, user_id: int, created_at: datetime) -> Calendar:
        return cls.create(
            user_id=user_id, name=DEFAULT_CALENDAR_NAME, color_key=EventColorKey.DEFAULT,
            sort_order=0, created_at=created_at, is_default=True,
        )

    def change(self, *, name: str, color_key: EventColorKey, updated_at: datetime) -> None:
        self.name = calendar_name(name)
        self.color_key = color_key
        self.updated_at = updated_at

    def show(self, visible: bool, updated_at: datetime) -> None:
        if self.is_visible == visible:
            return
        self.is_visible = visible
        self.updated_at = updated_at

    def place_at(self, sort_order: int, updated_at: datetime) -> None:
        if self.sort_order == sort_order:
            return
        self.sort_order = sort_order
        self.updated_at = updated_at


__all__ = [
    "DEFAULT_CALENDAR_NAME",
    "NAME_MAX_LENGTH",
    "Calendar",
    "CalendarKind",
    "calendar_name",
]
