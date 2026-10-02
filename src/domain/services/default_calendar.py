"""既定のカレンダー（ADR-0027）。

利用者には既定のカレンダーが 1 つある。移行 0009 で作ったが、その後に来た利用者には無いので、
初めて要るとき（カレンダーの一覧・予定を作る）にここで作る。
"""

from __future__ import annotations

from datetime import datetime

from src.domain.entities.calendar import LAYER_ORDER, Calendar, CalendarKind
from src.domain.repositories.calendar_repository import CalendarRepository


def ensure_default_calendar(calendars: CalendarRepository, user_id: int, now: datetime) -> Calendar:
    """その利用者の既定のカレンダー。無ければ作る（flush まで。確定は呼び出し側）。

    既定の印の付いたものが無いのにカレンダーがある（手で直した DB など）なら、並びの先頭を既定にする。
    """
    found = [c for c in calendars.find_all(user_id) if c.kind == CalendarKind.EVENTS]
    for calendar in found:
        if calendar.is_default:
            return calendar
    if found:
        first = found[0]
        first.is_default = True
        first.updated_at = now
        return calendars.save(first)
    return calendars.save(Calendar.create_default(user_id, now))


def ensure_day_off_layers(calendars: CalendarRepository, user_id: int, now: datetime) -> bool:
    """休みの 4 層（ADR-0029）のうち無いものを作る。作ったら ``True``（flush まで）。"""
    existing = calendars.find_all(user_id)
    has_workweek = any(c.kind == CalendarKind.WORKWEEK for c in existing)
    reasons = {c.day_off_reason for c in existing if c.kind == CalendarKind.DAYS_OFF}
    created = False
    for reason in LAYER_ORDER:
        if (reason is None and has_workweek) or (reason is not None and reason in reasons):
            continue
        calendars.save(Calendar.create_layer(user_id, reason, now))
        created = True
    return created


__all__ = ["ensure_day_off_layers", "ensure_default_calendar"]
