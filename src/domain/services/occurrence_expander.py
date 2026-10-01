"""予定を期間の中の具体的な回へ展開する（移植元 ``OccurrenceExpander``、time-model §4-2）。

繰り返しは規則を予定のタイムゾーンの「ローカル日のパターン」として評価し、各回の瞬間は
アンカーからの整数日の足し算で決める::

    occurrence_utc = anchor_utc + (回のローカル日 - アンカーのローカル日) 日

tz データベースを引き直さないので、制度（DST・政治的な時差）が変わっても各回の瞬間は
動かない。DST のあるゾーンではローカル時刻が季節で 1 時間ずれうる（JST には無い）。

展開した回の ``date`` / ``start_time`` は予定のタイムゾーンの壁時計。閲覧者のタイム
ゾーンへの投影は ``occurrence_display_projection`` で行う。
"""

from __future__ import annotations

import calendar as gregorian
from collections.abc import Iterator
from datetime import date, datetime, time, timedelta

from src.domain.entities.business_calendar import BusinessCalendar
from src.domain.entities.calendar_event import (
    PERIOD_OVERLAP_MARGIN_DAYS,
    CalendarEvent,
    EventException,
    EventMove,
    ExceptionType,
)
from src.domain.services.business_day_shift import BusinessDayShiftService
from src.domain.value_objects.event_schedule import EventOccurrence, OccurrenceKey
from src.domain.value_objects.local_schedule_point import local_date_of, local_time_of
from src.domain.value_objects.recurrence import (
    DayOfMonthMonthlyRule,
    DayOfMonthYearlyRule,
    LastDayOfMonthMonthlyRule,
    MonthlyRule,
    NthWeekdayMonthlyRule,
    NthWeekdayYearlyRule,
    RecurrenceRule,
    RecurrenceType,
    Weekday,
    WeeklyRule,
    YearlyRule,
)

_MAX_ORDINAL = date.max.toordinal()


def _add_days_clamped(day: date, days: int) -> date:
    return date.fromordinal(max(1, min(_MAX_ORDINAL, day.toordinal() + days)))


class OccurrenceExpander:
    def __init__(self, shift_service: BusinessDayShiftService | None = None) -> None:
        self._shift = shift_service or BusinessDayShiftService()

    def expand(
        self,
        event: CalendarEvent,
        from_date: date,
        to_date: date,
        business_calendar: BusinessCalendar | None = None,
    ) -> list[EventOccurrence]:
        """``[from_date, to_date]``（両端を含むローカル日）にある回を日付順に返す。"""
        if event.is_single():
            return self._expand_single(event, from_date, to_date)
        return self._expand_recurring(event, from_date, to_date, business_calendar)

    # ── 単発 ────────────────────────────────────────────────────────────

    @staticmethod
    def _expand_single(event: CalendarEvent, from_date: date, to_date: date) -> list[EventOccurrence]:
        schedule = event.single_schedule
        assert schedule is not None
        zone = event.time_zone.zone
        start_date = local_date_of(schedule.start_utc, zone)
        if start_date < from_date or start_date > to_date:
            return []
        return [
            EventOccurrence(
                event_id=event.id,
                date=start_date,
                start_time=local_time_of(schedule.start_utc, zone),
                duration_minutes=schedule.duration_minutes,
                title=event.title,
                location=event.location,
                color_key=event.color_key,
                task_id=event.task_id,
            )
        ]

    # ── 繰り返し ────────────────────────────────────────────────────────

    def _expand_recurring(
        self,
        event: CalendarEvent,
        from_date: date,
        to_date: date,
        business_calendar: BusinessCalendar | None,
    ) -> list[EventOccurrence]:
        schedule = event.recurring_schedule
        assert schedule is not None
        rule = schedule.recurrence_rule
        zone = event.time_zone.zone

        # アンカーのローカル日と時刻。時刻は回の鍵に使う「系列の名目の開始時刻」。
        anchor_local_date = local_date_of(schedule.anchor_utc, zone)
        anchor_local_time = local_time_of(schedule.anchor_utc, zone)

        def series_time_at(day: date) -> time:
            # その日の回の、UTC に留めた瞬間をローカルへ戻した時刻（time-model §4-2）。
            days = day.toordinal() - anchor_local_date.toordinal()
            try:
                instant: datetime = schedule.anchor_utc + timedelta(days=days)
            except OverflowError:
                return anchor_local_time
            try:
                return local_time_of(instant, zone)
            except OverflowError:
                return anchor_local_time

        exceptions: dict[OccurrenceKey, EventException] = {}
        for exception in event.exceptions:
            exceptions.setdefault(exception.occurrence_key, exception)
        moves: dict[OccurrenceKey, EventMove] = {}
        for move in event.moves:
            moves.setdefault(move.occurrence_key, move)

        # 営業日シフトは候補日を数日動かしうるので、窓の少し後ろの候補も作り、
        # シフトした後の日付で窓に入るかを決める（「月末の 3 営業日前」が窓の外の月末から
        # 窓の中へ来る場合を落とさない）。幅は粗い絞り込みの余白と同じ。
        candidate_bound = (
            _add_days_clamped(to_date, PERIOD_OVERLAP_MARGIN_DAYS) if rule.adjustment else to_date
        )

        results: list[EventOccurrence] = []
        for candidate in _candidate_dates(anchor_local_date, rule, candidate_bound):
            key = OccurrenceKey(candidate, anchor_local_time)
            exception = exceptions.get(key)
            if exception is not None and exception.type == ExceptionType.SKIP:
                continue

            # 移動は窓の判定より先に見る（窓の外の回が窓の中へ移されていれば出す）。
            move = moves.get(key)
            if move is not None:
                if from_date <= move.new_date <= to_date:
                    # 上書きと移動が同じ回に重なっていたら、上書きの内容を移動先にも残す。
                    content = (
                        exception.override
                        if exception is not None and exception.type == ExceptionType.OVERRIDE
                        else None
                    )
                    results.append(
                        EventOccurrence(
                            event_id=event.id,
                            date=move.new_date,
                            start_time=_first(
                                move.new_start_time,
                                content.start_time if content else None,
                            ) or series_time_at(candidate),
                            duration_minutes=_first(
                                move.new_duration_minutes,
                                content.duration_minutes if content else None,
                            ) or schedule.duration_minutes,
                            title=_first(move.title, content.title if content else None) or event.title,
                            location=_first(
                                move.location, content.location if content else None, event.location
                            ),
                            is_moved=True,
                            series_key=key,
                            color_key=event.color_key,
                            task_id=event.task_id,
                        )
                    )
                continue

            adjusted = candidate
            if rule.adjustment is not None and business_calendar is not None:
                if self._shift.cancels(candidate, rule.adjustment, business_calendar):
                    continue
                adjusted = self._shift.shift(candidate, rule.adjustment, business_calendar)

            if adjusted < from_date or adjusted > to_date:
                continue

            if (
                exception is not None
                and exception.type == ExceptionType.OVERRIDE
                and exception.override is not None
            ):
                content = exception.override
                results.append(
                    EventOccurrence(
                        event_id=event.id,
                        date=adjusted,
                        start_time=content.start_time or series_time_at(adjusted),
                        duration_minutes=content.duration_minutes or schedule.duration_minutes,
                        title=content.title or event.title,
                        location=_first(content.location, event.location),
                        is_overridden=True,
                        series_key=key,
                        color_key=event.color_key,
                        task_id=event.task_id,
                    )
                )
                continue

            results.append(
                EventOccurrence(
                    event_id=event.id,
                    date=adjusted,
                    start_time=series_time_at(adjusted),
                    duration_minutes=schedule.duration_minutes,
                    title=event.title,
                    location=event.location,
                    series_key=key,
                    color_key=event.color_key,
                    task_id=event.task_id,
                )
            )

        results.sort(key=lambda o: (o.date, o.start_time))
        return results


def _first[T](*values: T | None) -> T | None:
    for value in values:
        if value is not None:
            return value
    return None


# ── 候補日 ──────────────────────────────────────────────────────────────


def _candidate_dates(start: date, rule: RecurrenceRule, end_bound: date) -> Iterator[date]:
    end = min(rule.end_date, end_bound)
    if rule.rule_type == RecurrenceType.WEEKLY:
        assert rule.weekly is not None
        return _weekly(start, rule.interval, rule.weekly, end)
    if rule.rule_type == RecurrenceType.MONTHLY:
        assert rule.monthly is not None
        return _monthly(start, rule.interval, rule.monthly, end)
    assert rule.yearly is not None
    return _yearly(start, rule.interval, rule.yearly, end)


def _weekly(start: date, interval: int, weekly: WeeklyRule, end: date) -> Iterator[date]:
    # 開始日を含む週の月曜から、interval 週ごとに進む。
    week_start = start.toordinal() - start.weekday()
    offsets = [w.iso_index for w in weekly.weekdays]
    while week_start <= end.toordinal():
        for offset in offsets:
            candidate = week_start + offset
            if candidate > _MAX_ORDINAL:
                return
            if candidate < start.toordinal() or candidate > end.toordinal():
                continue
            yield date.fromordinal(candidate)
        week_start += 7 * interval
        if week_start > _MAX_ORDINAL:
            return


def _monthly(start: date, interval: int, monthly: MonthlyRule, end: date) -> Iterator[date]:
    month_index = start.year * 12 + (start.month - 1)
    last_index = date.max.year * 12 + (date.max.month - 1)
    while month_index <= last_index:
        year, month = divmod(month_index, 12)
        month += 1
        if date(year, month, 1) > end:
            return
        candidate = _resolve_monthly(year, month, monthly)
        if candidate is not None:
            if candidate > end:
                return
            if candidate >= start:
                yield candidate
        month_index += interval


def _resolve_monthly(year: int, month: int, rule: MonthlyRule) -> date | None:
    days_in_month = gregorian.monthrange(year, month)[1]
    if isinstance(rule, DayOfMonthMonthlyRule):
        return date(year, month, rule.day) if rule.day <= days_in_month else None
    if isinstance(rule, NthWeekdayMonthlyRule):
        return _nth_weekday(year, month, rule.week_index, rule.weekday)
    if isinstance(rule, LastDayOfMonthMonthlyRule):
        return date(year, month, days_in_month)
    return None


def _yearly(start: date, interval: int, yearly: YearlyRule, end: date) -> Iterator[date]:
    year = start.year
    while year <= date.max.year:
        if date(year, 1, 1) > end:
            return
        candidate = _resolve_yearly(year, yearly)
        if candidate is not None:
            if candidate > end:
                return
            if candidate >= start:
                yield candidate
        year += interval


def _resolve_yearly(year: int, rule: YearlyRule) -> date | None:
    if isinstance(rule, DayOfMonthYearlyRule):
        days_in_month = gregorian.monthrange(year, rule.month)[1]
        return date(year, rule.month, rule.day) if rule.day <= days_in_month else None
    if isinstance(rule, NthWeekdayYearlyRule):
        return _nth_weekday(year, rule.month, rule.week_index, rule.weekday)
    return None


def _nth_weekday(year: int, month: int, week_index: int, weekday: Weekday) -> date | None:
    """その月の第 n ○曜日（``-1`` は最終）。第 5 が無い月は ``None``。"""
    if week_index == -1:
        last = date(year, month, gregorian.monthrange(year, month)[1])
        return last - timedelta(days=(last.weekday() - weekday.iso_index) % 7)
    first = date(year, month, 1)
    offset = (weekday.iso_index - first.weekday()) % 7
    day = 1 + offset + (week_index - 1) * 7
    if day > gregorian.monthrange(year, month)[1]:
        return None
    return date(year, month, day)


__all__ = ["OccurrenceExpander"]
