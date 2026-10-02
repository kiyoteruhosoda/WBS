"""iCalendar（.ics）を取り込んだ回の一覧にする（ADR-0037）。

``icalendar`` で読み、``recurring_ical_events`` で繰り返し（RRULE・RDATE・EXDATE・この回だけの変更）を
期間の中で展開する。どのサービスのものかで分けない:

- Outlook のタイムゾーン名（``Tokyo Standard Time`` など Windows の名前）は ``icalendar`` が IANA へ読み替える
- Google の ``X-WR-TIMEZONE`` は ``recurring_ical_events`` が読み替える
- ゾーンの無い時刻（floating）は利用者のタイムゾーンの壁時計とみなす
- ``STATUS:CANCELLED`` の回は持たない（Google は消した回をこれで出す）
- 終わりが無い回は、終日なら 1 日、時刻があれば長さ 0
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import recurring_ical_events
from icalendar import Calendar as ICalendar

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure
from src.domain.value_objects.imported_occurrence import ImportedOccurrence
from src.domain.value_objects.local_schedule_point import to_naive_utc

_MAGIC = b"BEGIN:VCALENDAR"


class IcsCalendarParser:
    def parse(
        self, content: bytes, *, from_date: date, to_date: date, default_time_zone: str
    ) -> list[ImportedOccurrence]:
        if _MAGIC not in content.lstrip(b"\xef\xbb\xbf \t\r\n")[: len(_MAGIC) + 16].upper():
            raise CalendarFeedError(FeedFailure.NOT_ICALENDAR)
        floating_zone = ZoneInfo(default_time_zone)
        try:
            calendar = ICalendar.from_ical(content)
            components = recurring_ical_events.of(calendar, skip_bad_series=True).between(
                from_date, to_date + timedelta(days=1)
            )
            occurrences = [
                occurrence
                for component in components
                if (occurrence := _occurrence(component, floating_zone)) is not None
            ]
        except CalendarFeedError:
            raise
        except Exception as exc:  # 壊れた中身は形がさまざまで、ライブラリの例外も揃っていない
            raise CalendarFeedError(FeedFailure.NOT_ICALENDAR) from exc
        occurrences.sort(key=_sort_key)
        return occurrences


def _occurrence(component, floating_zone: ZoneInfo) -> ImportedOccurrence | None:
    if str(component.get("STATUS", "")).upper() == "CANCELLED":
        return None
    start = component.start
    try:
        end = component.end
    except Exception:  # 終わりも長さも無い
        end = None
    title = str(component.get("SUMMARY", "") or "")
    location = component.get("LOCATION")
    location_text = str(location) if location is not None else None
    if isinstance(start, datetime):
        start_utc = _utc(start, floating_zone)
        end_utc = _utc(end, floating_zone) if isinstance(end, datetime) else start_utc
        if end_utc < start_utc:
            end_utc = start_utc
        return ImportedOccurrence.timed(title, start_utc, end_utc, location_text)
    end_date = end if isinstance(end, date) and not isinstance(end, datetime) else None
    if end_date is None or end_date <= start:
        end_date = start + timedelta(days=1)
    return ImportedOccurrence.all_day(title, start, end_date, location_text)


def _utc(moment: datetime, floating_zone: ZoneInfo) -> datetime:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=floating_zone)
    return to_naive_utc(moment)


def _sort_key(occurrence: ImportedOccurrence) -> tuple:
    if occurrence.start_date is not None:
        return (datetime.combine(occurrence.start_date, datetime.min.time()), occurrence.title)
    assert occurrence.start_utc is not None
    return (occurrence.start_utc, occurrence.title)


__all__ = ["IcsCalendarParser"]
