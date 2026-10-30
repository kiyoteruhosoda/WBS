"""iCalendar（.ics）を取り込んだ回の一覧にする（ADR-0037）。

``icalendar`` で読み、``recurring_ical_events`` で繰り返し（RRULE・RDATE・EXDATE・この回だけの変更）を
期間の中で展開する。どのサービスのものかで分けない:

- Outlook のタイムゾーン名（``Tokyo Standard Time`` など Windows の名前）は ``icalendar`` が IANA へ読み替える
- Google の ``X-WR-TIMEZONE`` は ``recurring_ical_events`` が読み替える
- ゾーンの無い時刻（floating）は利用者のタイムゾーンの壁時計とみなす
- ``STATUS:CANCELLED`` の回は持たない（Google は消した回をこれで出す）
- 終わりが無い回は、終日なら 1 日、時刻があれば長さ 0
- 展開する前に、繰り返しごとに期間の中の回を数え上げ、上限を超えたら展開せずに断る（nolumiatask #748。
  ``recurring_ical_events`` は期間の中を全部作ってから返すので、``FREQ=SECONDLY`` 1 行で何百万件も作る）
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from time import monotonic
from zoneinfo import ZoneInfo

import recurring_ical_events
from dateutil.rrule import rrulestr
from icalendar import Calendar as ICalendar

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure
from src.domain.value_objects.imported_occurrence import ImportedOccurrence
from src.domain.value_objects.local_schedule_point import to_naive_utc

_MAGIC = b"BEGIN:VCALENDAR"

#: 繰り返しを回す回数の、1 つのフィード全体の見積もりの上限（nolumiatask #748）。ふつうのフィードでは、毎日の予定を
#: 2010 年から続けても 1 本 6,000 回ほど。100 本でも収まる
MAX_RULE_STEPS = 2_000_000
#: 数え上げに使ってよい時間（秒）。ふつうのフィードは 1 秒も掛からない。当たらない条件の繰り返しは西暦 9999 年まで回る
MAX_COUNTING_SECONDS = 15.0

_DAY_SECONDS = 86_400
_FREQUENCY_SECONDS = {
    "SECONDLY": 1,
    "MINUTELY": 60,
    "HOURLY": 3_600,
    "DAILY": _DAY_SECONDS,
    "WEEKLY": 7 * _DAY_SECONDS,
    "MONTHLY": 28 * _DAY_SECONDS,
    "YEARLY": 365 * _DAY_SECONDS,
}
#: 日を増やす条件（月・年ごとの繰り返しでも、1 日ごとに回ることになる）
_DAY_PARTS = ("BYDAY", "BYMONTHDAY", "BYYEARDAY", "BYWEEKNO")
#: 1 日の中の時刻を増やす条件
_TIME_PARTS = ("BYHOUR", "BYMINUTE", "BYSECOND")


class IcsCalendarParser:
    def parse(
        self,
        content: bytes,
        *,
        from_date: date,
        to_date: date,
        default_time_zone: str,
        max_occurrences: int | None = None,
    ) -> list[ImportedOccurrence]:
        if _MAGIC not in content.lstrip(b"\xef\xbb\xbf \t\r\n")[: len(_MAGIC) + 16].upper():
            raise CalendarFeedError(FeedFailure.NOT_ICALENDAR)
        floating_zone = ZoneInfo(default_time_zone)
        try:
            calendar = ICalendar.from_ical(content)
            if max_occurrences is not None:
                _refuse_too_many(calendar, from_date, to_date, max_occurrences)
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


def _refuse_too_many(calendar: ICalendar, from_date: date, to_date: date, limit: int) -> None:
    """展開する前に、期間の中の回を繰り返しごとに上限＋1 件まで数える。超えれば断る。

    数えるのは多めでよい（取り消し・この回だけの変更・EXDATE は引かない）。⚠ 数え上げも展開も繰り返しの
    始まりから順に回すので、先に手間を見積もって、大きければ回さずに断る（期間の外だけを回す繰り返しもある）。
    """
    window_start = datetime(from_date.year, from_date.month, from_date.day, tzinfo=UTC)
    window_end = datetime(to_date.year, to_date.month, to_date.day, tzinfo=UTC) + timedelta(days=1)
    deadline = monotonic() + MAX_COUNTING_SECONDS
    total = 0
    steps = 0
    for event in calendar.walk("VEVENT"):
        rules = _rules_of(event)
        steps += sum(_steps_until(rule, event, window_end) for rule in rules)
        if steps > MAX_RULE_STEPS:
            raise CalendarFeedError(FeedFailure.TOO_MANY_EVENTS)
        total += _count_in_window(event, rules, window_start, window_end, limit + 1 - total)
        if total > limit or monotonic() > deadline:
            raise CalendarFeedError(FeedFailure.TOO_MANY_EVENTS)


def _rules_of(event) -> list:
    rules = event.get("RRULE")
    if rules is None:
        return []
    return rules if isinstance(rules, list) else [rules]


def _start_of(event) -> datetime | None:
    start = event.get("DTSTART")
    if start is None:
        return None
    at = start.dt
    if isinstance(at, datetime):
        return at
    return datetime(at.year, at.month, at.day)


def _as_utc(at: datetime) -> datetime:
    return at.replace(tzinfo=UTC) if at.tzinfo is None else at.astimezone(UTC)


def _steps_until(rule, event, window_end: datetime) -> int:
    """繰り返しの始まりから期間の終わりまでに、ライブラリが回す回数の見積もり（多めに）。"""
    start = _start_of(event)
    if start is None:
        return 0
    return _steps_between(rule, _as_utc(start), window_end)


def _steps_between(rule, start: datetime, end: datetime) -> int:
    seconds = (end - start).total_seconds()
    if seconds <= 0:
        return 0
    frequency = str((rule.get("FREQ") or [""])[0]).upper()
    period = _FREQUENCY_SECONDS.get(frequency)
    if period is None:
        return 0
    if period > _DAY_SECONDS and any(rule.get(part) for part in _DAY_PARTS):
        period = _DAY_SECONDS
    interval = (rule.get("INTERVAL") or [1])[0]
    interval = interval if isinstance(interval, int) and interval > 0 else 1
    times_per_step = 1
    for part in _TIME_PARTS:
        times_per_step *= max(1, len(rule.get(part) or []))
    return (int(seconds // (period * interval)) + 1) * times_per_step


def _count_in_window(event, rules: list, window_start: datetime, window_end: datetime, budget: int) -> int:
    start = _start_of(event)
    if start is None:
        return 0
    if not rules:
        return 1 if window_start <= _as_utc(start) < window_end else 0
    count = 0
    for rule in rules:
        count += _count_rule(rule, start, window_start, window_end, budget - count)
        if count >= budget:
            break
    return count + len(event.get("RDATE") or [])


def _count_rule(rule, start: datetime, window_start: datetime, window_end: datetime, budget: int) -> int:
    # 比べる相手を繰り返しの始まりの形（ゾーンの有無）に揃える
    first, last = window_start, window_end
    if start.tzinfo is None:
        first, last = first.replace(tzinfo=None), last.replace(tzinfo=None)
    count = 0
    try:
        for at in rrulestr(rule.to_ical().decode(), dtstart=start):
            if at >= last:
                break
            if at >= first:
                count += 1
                if count >= budget:
                    break
    except (ValueError, TypeError):
        # dateutil が読めない形でも、展開のほうは読むことがある（ゾーン付きの始まりにゾーンの無い UNTIL など）。
        # 数えないと上限をすり抜けるので、期間の中の最大の回数で数える
        return min(_steps_between(rule, max(_as_utc(start), window_start), window_end), budget)
    return count


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
