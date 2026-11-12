"""Handling of time.

Contract (HANDOVER §14): storage, comparison and logs are all in UTC; conversion to local time happens
only at the moment of display. There is exactly one place that reads "now": here.

Plain ``datetime.now()`` returns the container's local time, so it is not used.
``datetime.now(UTC)`` is also **not called anywhere but here** (with two sources, the next
policy change would leave one behind). `tests/unit/test_time_contract.py` guards this.

``utcnow()`` returns **naive UTC**. ``DATETIME`` in the DB (SQLite / MariaDB)
has no time zone, and written values come back naive. Making only the producer aware would give
"freshly inserted values are aware, re-read values are naive", and comparing the two
fails with ``TypeError: can't compare offset-naive and offset-aware datetimes``.
Matching the stored form means that combination never happens.

To convert to local time, treat naive as UTC, attach the zone, then convert
(`src/application/user_clock.py`). Strings leaving the boundary use `isoformat_utc()`.
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """Return the current time as naive UTC (same form as stored values)."""
    return datetime.now(UTC).replace(tzinfo=None)


def isoformat_utc(value: datetime) -> str:
    """ISO string for leaving the API. Always ends with ``Z``.

    Naive values are treated as UTC. A browser's ``new Date()`` reads an ISO string without ``Z``
    as local time, so every value leaving the boundary must go through here.
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


def to_naive_utc(value: datetime) -> datetime:
    """Convert a time coming in from the boundary to the stored form (naive UTC).

    If aware, convert to UTC and then drop the zone. Naive values are taken as UTC already.
    """
    return value if value.tzinfo is None else value.astimezone(UTC).replace(tzinfo=None)


__all__ = ["isoformat_utc", "to_naive_utc", "utcnow"]
