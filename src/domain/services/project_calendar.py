"""プロジェクトのカレンダーを、自分と先祖の休日・稼働日から組む（ADR-0059 決定 1・ADR-0060）。

同じ日に休日と稼働日の両方があれば、**近いプロジェクト（自分 → 親 → … → 根）の指定が勝つ**。
同じプロジェクトに同じ日の休日と稼働日は並ばない（入れるときに片方を消す）。
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date

from src.domain.entities.team_day_off import TeamDayOff, TeamExtraWorkday


@dataclass(frozen=True)
class LayeredCalendarDays:
    """近いほうが勝ったあとの休日と稼働日（どちらも日付の順。同じ日は重ならない）。"""

    days_off: list[TeamDayOff]
    extra_workdays: list[TeamExtraWorkday]


def layer_calendar_days(
    lineage: Sequence[int],
    days_off: Iterable[TeamDayOff],
    extra_workdays: Iterable[TeamExtraWorkday],
) -> LayeredCalendarDays:
    """``lineage`` は自分から根までの id（自分が先頭）。それ以外のプロジェクトのものは捨てる。"""
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
