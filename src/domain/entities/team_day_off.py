"""Project days off and each person's leave (task #554 / ADR-0058 decision 2, task #557 / ADR-0059).

- Days off attach to any project. A project's days off are the union of its own and its ancestors' (up to the root)
- Working days (days worked on a non-working weekday) also attach to any project like days off, and lower projects inherit them (ADR-0060)
- Personal leave attaches to the person (the same across projects). It holds only a date and a leave ratio (full day 100, half day 50),
  or that day's working hours (overtime, short day, working on a day off. ADR-0060)
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from src.domain.exceptions import ValidationError

DAY_OFF_NAME_MAX_LENGTH = 100
FULL_DAY_OFF_PERCENT = 100
HALF_DAY_OFF_PERCENT = 50
MAX_DAY_HOURS = 24


def team_day_off_name(raw: str | None) -> str | None:
    """The name with surrounding whitespace stripped (None if empty). Rejects too-long names."""
    if raw is None:
        return None
    name = raw.strip()
    if not name:
        return None
    if len(name) > DAY_OFF_NAME_MAX_LENGTH:
        raise ValidationError(f"a day off name must be at most {DAY_OFF_NAME_MAX_LENGTH} characters")
    return name


@dataclass(frozen=True)
class TeamDayOff:
    #: Project the day off belongs to (a team day off if it is a root)
    project_id: int
    day: date
    name: str | None = None


@dataclass(frozen=True)
class TeamExtraWorkday:
    """A day worked on that project on a non-working weekday (ADR-0060)."""

    project_id: int
    day: date
    name: str | None = None


@dataclass(frozen=True)
class MemberDayOff:
    """One day of a person's calendar: leave / half day (leave ratio) or that day's working hours."""

    user_id: int
    day: date
    #: Leave ratio (1–100; full day 100, half day 50). Ignored if ``hours`` is set
    off_percent: int = FULL_DAY_OFF_PERCENT
    #: That day's working hours (0–24; may exceed hours per day = overtime; on a non-working day it means working on a day off)
    hours: float | None = None

    def __post_init__(self) -> None:
        if not 1 <= self.off_percent <= FULL_DAY_OFF_PERCENT:
            raise ValidationError("a day off must take 1 to 100 percent of the day")
        if self.hours is not None and not 0 <= self.hours <= MAX_DAY_HOURS:
            raise ValidationError("working hours of a day must be 0 to 24")
