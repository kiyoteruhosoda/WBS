"""The user's "today".

Where a day starts depends on the user's time zone. The server runs in UTC, so
`date.today()` gives the UTC date, and for a JST user "today" is shifted to the
previous day every day between 0:00 and 9:00.

Storage and comparisons stay in UTC (contract HANDOVER §14). This only handles dates as
"boundaries shown on screen". When matching a range cut by the user's dates against
stored UTC values, go through `utc_window()`.
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import UserModel
from src.shared.clock import utcnow


class UserClock:
    """Gives dates in the user's time zone. Not re-read within one request."""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._zones: dict[int, tzinfo] = {}
        self._today: dict[int, date] = {}

    def zone(self, user_id: int) -> tzinfo:
        """The user's time zone. Unset or invalid values fall back to UTC."""
        cached = self._zones.get(user_id)
        if cached is not None:
            return cached
        timezone_name = (
            self._session.execute(
                select(UserModel.timezone).where(UserModel.id == user_id)
            ).scalar()
            or "UTC"
        )
        try:
            resolved: tzinfo = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            resolved = UTC
        self._zones[user_id] = resolved
        return resolved

    def zone_name(self, user_id: int) -> str:
        """IANA name of the user's time zone (``"UTC"`` when ``zone`` fell back to UTC)."""
        zone = self.zone(user_id)
        return zone.key if isinstance(zone, ZoneInfo) else "UTC"

    def today(self, user_id: int) -> date:
        cached = self._today.get(user_id)
        if cached is not None:
            return cached
        # utcnow() is naive UTC like the stored values. Attach the zone, then convert to the user's TZ.
        resolved = utcnow().replace(tzinfo=UTC).astimezone(self.zone(user_id)).date()
        self._today[user_id] = resolved
        return resolved

    def utc_window(self, user_id: int, first_day: date, last_day: date) -> tuple[datetime, datetime]:
        """Return the span from 0:00 of the user's ``first_day`` to the end of ``last_day`` in UTC.

        Returns a half-open interval ``[start, end)`` (naive UTC, like the stored values).

        Stored values are UTC, so comparing dates cut in the user's time zone directly with DATETIME columns
        shifts the boundary by the time difference. With JST, rows created Monday 0:00-9:00 would fall into
        neither the previous week nor this week and never be counted. Passing dates as is would also make the end
        "0:00 of the last day" and drop that day; the half-open interval here prevents that too.
        """
        zone = self.zone(user_id)
        start = datetime.combine(first_day, time.min, tzinfo=zone)
        end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=zone)
        return (
            start.astimezone(UTC).replace(tzinfo=None),
            end.astimezone(UTC).replace(tzinfo=None),
        )


__all__ = ["UserClock"]
