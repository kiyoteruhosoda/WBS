"""利用者ごとの端末への通知の設定（task #193 / ADR-0031）。

種類ごとの入り / 切りと、止め忘れと見なす時間。行が無い利用者は既定（すべて入り・4 時間）。
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from src.domain.exceptions import ValidationError
from src.domain.value_objects.push_kind import PushKind

DEFAULT_TIMER_LEFT_RUNNING_HOURS = 4
MIN_TIMER_LEFT_RUNNING_HOURS = 1
MAX_TIMER_LEFT_RUNNING_HOURS = 24


@dataclass(frozen=True)
class PushPreferences:
    event_alarm: bool = True
    routine_start: bool = True
    timer_left_running: bool = True
    closing_due: bool = True
    timer_left_running_hours: int = DEFAULT_TIMER_LEFT_RUNNING_HOURS

    def __post_init__(self) -> None:
        if not (
            MIN_TIMER_LEFT_RUNNING_HOURS
            <= self.timer_left_running_hours
            <= MAX_TIMER_LEFT_RUNNING_HOURS
        ):
            raise ValidationError(
                "timer_left_running_hours must be between "
                f"{MIN_TIMER_LEFT_RUNNING_HOURS} and {MAX_TIMER_LEFT_RUNNING_HOURS}"
            )

    def allows(self, kind: PushKind) -> bool:
        return {
            PushKind.EVENT_ALARM: self.event_alarm,
            PushKind.ROUTINE_START: self.routine_start,
            PushKind.TIMER_LEFT_RUNNING: self.timer_left_running,
            PushKind.CLOSING_DUE: self.closing_due,
        }[kind]

    def changed(self, **fields: object) -> PushPreferences:
        """省いた欄は今のまま（``None`` も今のまま）。"""
        return replace(self, **{k: v for k, v in fields.items() if v is not None})


__all__ = [
    "DEFAULT_TIMER_LEFT_RUNNING_HOURS",
    "MAX_TIMER_LEFT_RUNNING_HOURS",
    "MIN_TIMER_LEFT_RUNNING_HOURS",
    "PushPreferences",
]
