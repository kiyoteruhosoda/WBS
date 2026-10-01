"""展開した回を閲覧者のタイムゾーンへ投影する（移植元 ``OccurrenceDisplayProjection``、time-model §2-3・§4）。

返す回の日付・時刻は閲覧者のローカル。元の回の身元（予定のタイムゾーンでの鍵）は
``series_key`` に残すので、どのタイムゾーンから見ても飛ばす・移動・切り出しは正しい回を指す。

終日（00:00 ＋ 24 時間）は「浮いた日」として扱い、ずらさない。0:00 始まりの丸 1 日を
別のゾーンへ直すと前日の途中から始まる帯になり、終日の予定として期待される見え方ではない。
"""

from __future__ import annotations

from dataclasses import replace

from src.domain.value_objects.event_schedule import EventOccurrence, OccurrenceKey
from src.domain.value_objects.local_schedule_point import (
    local_date_of,
    local_time_of,
    start_instant,
)
from src.domain.value_objects.time_zone import TimeZoneId


def to_display_time_zone(
    occurrence: EventOccurrence, event_time_zone: TimeZoneId, viewer_time_zone: TimeZoneId
) -> EventOccurrence:
    canonical_key = occurrence.series_key or OccurrenceKey(occurrence.date, occurrence.start_time)

    if event_time_zone == viewer_time_zone or occurrence.is_all_day:
        return replace(occurrence, series_key=canonical_key)

    instant = start_instant(occurrence.date, occurrence.start_time, event_time_zone.zone)
    return replace(
        occurrence,
        date=local_date_of(instant, viewer_time_zone.zone),
        start_time=local_time_of(instant, viewer_time_zone.zone),
        series_key=canonical_key,
    )


__all__ = ["to_display_time_zone"]
