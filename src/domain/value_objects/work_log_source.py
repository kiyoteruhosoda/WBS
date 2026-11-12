"""Where an actual (``work_logs``) came from (``work_logs.source``)."""

from __future__ import annotations

from enum import StrEnum


class WorkLogSource(StrEnum):
    """Stored in the DB as this string (not a native ENUM)."""

    MANUAL = "manual"
    """Written by hand on the actuals screen / API."""

    CLOSING = "closing"
    """Created from time entries when a closing was confirmed (task #161 / ADR-0012). Removed when reopened."""

    TRACKER = "tracker"
    """Time closed in Tracker and received from it (task #540 / ADR-0056). Replaced per Tracker period; removed on cancellation."""
