"""既定のカレンダー（ADR-0027）。

利用者には既定のカレンダーが 1 つある。移行 0009 で作ったが、その後に来た利用者には無いので、
初めて要るとき（カレンダーの一覧・予定を作る）にここで作る。
"""

from __future__ import annotations

from datetime import datetime

from src.domain.entities.calendar import Calendar
from src.domain.repositories.calendar_repository import CalendarRepository


def ensure_default_calendar(calendars: CalendarRepository, user_id: int, now: datetime) -> Calendar:
    """その利用者の既定のカレンダー。無ければ作る（flush まで。確定は呼び出し側）。

    既定の印の付いたものが無いのにカレンダーがある（手で直した DB など）なら、並びの先頭を既定にする。
    """
    found = calendars.find_all(user_id)
    for calendar in found:
        if calendar.is_default:
            return calendar
    if found:
        first = found[0]
        first.is_default = True
        first.updated_at = now
        return calendars.save(first)
    return calendars.save(Calendar.create_default(user_id, now))


__all__ = ["ensure_default_calendar"]
