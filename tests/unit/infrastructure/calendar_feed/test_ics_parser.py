"""iCalendar を取り込んだ回にする（task #196 / ADR-0037）。

Google（X-WR-TIMEZONE・繰り返し・消した回）・Outlook（Windows のタイムゾーン名）・終日・ゾーンの無い時刻・
壊れた中身を確かめる。
"""

from __future__ import annotations

from datetime import date, datetime

import pytest

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure
from src.infrastructure.calendar_feed.ics_parser import IcsCalendarParser

PARSER = IcsCalendarParser()
WINDOW = {"from_date": date(2026, 10, 1), "to_date": date(2026, 10, 31)}


def _parse(text: str, time_zone: str = "Asia/Tokyo"):
    return PARSER.parse(text.encode("utf-8"), default_time_zone=time_zone, **WINDOW)


GOOGLE = """BEGIN:VCALENDAR
PRODID:-//Google Inc//Google Calendar 70.9054//EN
VERSION:2.0
X-WR-CALNAME:仕事
X-WR-TIMEZONE:Asia/Tokyo
BEGIN:VEVENT
DTSTART;TZID=Asia/Tokyo:20261005T100000
DTEND;TZID=Asia/Tokyo:20261005T110000
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Asia/Tokyo:20261012T100000
UID:weekly@google.com
SUMMARY:定例
LOCATION:会議室 A
END:VEVENT
BEGIN:VEVENT
DTSTART;TZID=Asia/Tokyo:20261019T100000
DTEND;TZID=Asia/Tokyo:20261019T110000
RECURRENCE-ID;TZID=Asia/Tokyo:20261019T100000
UID:weekly@google.com
STATUS:CANCELLED
SUMMARY:定例
END:VEVENT
BEGIN:VEVENT
DTSTART:20261007T060000Z
DTEND:20261007T063000Z
UID:once@google.com
SUMMARY:1on1
END:VEVENT
END:VCALENDAR
"""


def test_google_recurrence_is_expanded_without_excluded_and_cancelled_occurrences() -> None:
    occurrences = _parse(GOOGLE)
    weekly = [o for o in occurrences if o.title == "定例"]
    # 10/5・10/12（EXDATE）・10/19（CANCELLED）・10/26 → 10/5 と 10/26
    assert [o.start_utc for o in weekly] == [datetime(2026, 10, 5, 1), datetime(2026, 10, 26, 1)]
    assert all(o.end_utc is not None and (o.end_utc - o.start_utc).seconds == 3600 for o in weekly)
    assert weekly[0].location == "会議室 A"
    once = next(o for o in occurrences if o.title == "1on1")
    assert once.start_utc == datetime(2026, 10, 7, 6) and once.end_utc == datetime(2026, 10, 7, 6, 30)


OUTLOOK = """BEGIN:VCALENDAR
METHOD:PUBLISH
PRODID:Microsoft Exchange Server 2010
VERSION:2.0
BEGIN:VTIMEZONE
TZID:Tokyo Standard Time
BEGIN:STANDARD
DTSTART:16010101T000000
TZOFFSETFROM:+0900
TZOFFSETTO:+0900
END:STANDARD
END:VTIMEZONE
BEGIN:VEVENT
DTSTART;TZID=Tokyo Standard Time:20261008T140000
DTEND;TZID=Tokyo Standard Time:20261008T153000
UID:040000008200E00074C5B7101A82E008
SUMMARY:予定あり
TRANSP:OPAQUE
END:VEVENT
END:VCALENDAR
"""


def test_outlook_windows_time_zone_is_read() -> None:
    [occurrence] = _parse(OUTLOOK)
    assert occurrence.title == "予定あり"
    assert occurrence.start_utc == datetime(2026, 10, 8, 5)
    assert occurrence.end_utc == datetime(2026, 10, 8, 6, 30)


ALL_DAY_AND_FLOATING = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261010
DTEND;VALUE=DATE:20261013
UID:trip
SUMMARY:出張
END:VEVENT
BEGIN:VEVENT
DTSTART;VALUE=DATE:20261020
UID:single-day
SUMMARY:記念日
END:VEVENT
BEGIN:VEVENT
DTSTART:20261015T090000
DTEND:20261015T100000
UID:floating
SUMMARY:浮いた時刻
END:VEVENT
BEGIN:VEVENT
DTSTART:20261201T090000Z
DTEND:20261201T100000Z
UID:outside
SUMMARY:期間の外
END:VEVENT
END:VCALENDAR
"""


def test_all_day_floating_and_window() -> None:
    occurrences = {o.title: o for o in _parse(ALL_DAY_AND_FLOATING)}
    assert set(occurrences) == {"出張", "記念日", "浮いた時刻"}
    trip = occurrences["出張"]
    assert trip.is_all_day and (trip.start_date, trip.end_date) == (date(2026, 10, 10), date(2026, 10, 13))
    single = occurrences["記念日"]
    assert (single.start_date, single.end_date) == (date(2026, 10, 20), date(2026, 10, 21))
    # ゾーンの無い時刻は利用者のタイムゾーン（Asia/Tokyo）の壁時計
    assert occurrences["浮いた時刻"].start_utc == datetime(2026, 10, 15, 0)


@pytest.mark.parametrize(
    "content",
    [
        "<!DOCTYPE html><html><body>Sign in</body></html>",
        "",
        "BEGIN:VCARD\nVERSION:3.0\nFN:名刺\nEND:VCARD\n",
    ],
)
def test_content_that_is_not_icalendar_is_refused(content: str) -> None:
    with pytest.raises(CalendarFeedError) as caught:
        _parse(content)
    assert caught.value.reason == FeedFailure.NOT_ICALENDAR
