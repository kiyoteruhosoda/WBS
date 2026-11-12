"""Build a project's calendar from the days off and working days of itself and its ancestors (ADR-0059 decision 1, ADR-0060).

If one day has both a day off and a working day, **the nearest project's setting wins (self → parent → … → root)**.
One project never has both a day off and a working day on the same day (one is removed when adding).
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from src.domain.entities.team_day_off import TeamDayOff, TeamExtraWorkday


@dataclass(frozen=True)
class LayeredCalendarDays:
    """Days off and working days after the nearest wins (both in date order; no day appears in both)."""

    days_off: list[TeamDayOff]
    extra_workdays: list[TeamExtraWorkday]


def layer_calendar_days(
    lineage: Sequence[int],
    days_off: Iterable[TeamDayOff],
    extra_workdays: Iterable[TeamExtraWorkday],
) -> LayeredCalendarDays:
    """``lineage`` is the ids from self up to the root (self first). Entries of any other project are discarded."""
    rank = {project_id: i for i, project_id in enumerate(lineage)}
    by_day: dict[date, tuple[int, TeamDayOff | TeamExtraWorkday]] = {}
    for item in [*days_off, *extra_workdays]:
        if item.project_id not in rank:
            continue
        kept = by_day.get(item.day)
        if kept is None or rank[item.project_id] < kept[0]:
            by_day[item.day] = (rank[item.project_id], item)
    ordered = [by_day[day][1] for day in sorted(by_day)]
    return LayeredCalendarDays(
        days_off=[d for d in ordered if isinstance(d, TeamDayOff)],
        extra_workdays=[d for d in ordered if isinstance(d, TeamExtraWorkday)],
    )


__all__ = ["LayeredCalendarDays", "layer_calendar_days"]
