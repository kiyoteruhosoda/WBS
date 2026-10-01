"""閲覧者のタイムゾーンへの投影（移植元 CoreTests/OccurrenceDisplayProjectionTests.cs）。"""

from __future__ import annotations

from datetime import date, time

from src.domain.services.occurrence_display_projection import to_display_time_zone
from src.domain.value_objects.event_schedule import EventOccurrence, OccurrenceKey
from tests.unit.domain.scheduling.support import NEW_YORK, TOKYO


def _occ(y: int, mo: int, d: int, h: int, mi: int, duration: int, series_key=None) -> EventOccurrence:
    return EventOccurrence(1, date(y, mo, d), time(h, mi), duration, "t", series_key=series_key)


def test_jst_occurrence_projected_to_new_york_shifts_date_and_time() -> None:
    shown = to_display_time_zone(_occ(2026, 6, 15, 10, 0, 60), TOKYO, NEW_YORK)
    assert (shown.date, shown.start_time, shown.duration_minutes) == (date(2026, 6, 14), time(21, 0), 60)


def test_jst_occurrence_in_new_york_differs_between_summer_and_winter() -> None:
    assert to_display_time_zone(_occ(2026, 7, 1, 10, 0, 60), TOKYO, NEW_YORK).start_time == time(21, 0)
    assert to_display_time_zone(_occ(2026, 1, 15, 10, 0, 60), TOKYO, NEW_YORK).start_time == time(20, 0)


def test_new_york_recurrence_in_tokyo_shifts_one_hour_across_dst() -> None:
    assert to_display_time_zone(_occ(2026, 7, 1, 9, 0, 60), NEW_YORK, TOKYO).start_time == time(22, 0)
    assert to_display_time_zone(_occ(2026, 1, 15, 9, 0, 60), NEW_YORK, TOKYO).start_time == time(23, 0)


def test_projection_preserves_canonical_key_for_recurring_series() -> None:
    key = OccurrenceKey(date(2026, 6, 15), time(10, 0))
    shown = to_display_time_zone(_occ(2026, 6, 15, 10, 0, 60, key), TOKYO, NEW_YORK)
    assert shown.date == date(2026, 6, 14)
    assert shown.series_key == key


def test_projection_of_single_sets_canonical_key_to_event_local() -> None:
    shown = to_display_time_zone(_occ(2026, 6, 15, 10, 0, 60), TOKYO, NEW_YORK)
    assert shown.series_key == OccurrenceKey(date(2026, 6, 15), time(10, 0))


def test_same_time_zone_returns_equivalent_occurrence() -> None:
    shown = to_display_time_zone(_occ(2026, 6, 15, 10, 0, 60), TOKYO, TOKYO)
    assert (shown.date, shown.start_time) == (date(2026, 6, 15), time(10, 0))
    assert shown.series_key == OccurrenceKey(date(2026, 6, 15), time(10, 0))


def test_all_day_occurrence_is_not_shifted_across_zones() -> None:
    shown = to_display_time_zone(_occ(2026, 6, 15, 0, 0, 24 * 60), TOKYO, NEW_YORK)
    assert (shown.date, shown.start_time, shown.duration_minutes) == (date(2026, 6, 15), time(0, 0), 1440)
