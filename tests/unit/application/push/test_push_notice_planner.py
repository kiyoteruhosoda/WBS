"""いま送る通知の判定（task #193 / ADR-0031）。送る時刻・まとめ方・種類の入り / 切り。

時刻はどれも naive な UTC。利用者は Asia/Tokyo（UTC+9）。
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from src.application.dto.calendar_event_dto import OccurrenceView
from src.application.dto.closing_dto import PendingClosings
from src.application.push_notice_planner import (
    DUE_GRACE,
    PushNoticePlanner,
    RunningTimer,
    is_due,
)
from src.domain.entities.calendar_event import EventType
from src.domain.entities.time_entry import TimeEntry
from src.domain.value_objects.event_alarm import EventAlarm
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.half_month_period import HalfMonthPeriod
from src.domain.value_objects.push_kind import PushKind
from src.domain.value_objects.push_preferences import PushPreferences

TOKYO = ZoneInfo("Asia/Tokyo")
START = datetime(2026, 10, 5, 1, 0)  # 10:00 JST
ALL_ON = PushPreferences()


def _planner(language: str = "ja") -> PushNoticePlanner:
    return PushNoticePlanner(7, TOKYO, language)


def _occurrence(
    *,
    start: datetime = START,
    alarm: EventAlarm | None = None,
    event_type: EventType = EventType.EVENT,
    all_day: bool = False,
    location: str | None = None,
) -> OccurrenceView:
    local = start + timedelta(hours=9)
    return OccurrenceView(
        event_id=12,
        event_version=1,
        is_recurring=False,
        title="設計レビュー",
        start_utc=start,
        duration_minutes=1440 if all_day else 60,
        date=local.date(),
        start_time=time(0, 0) if all_day else local.time(),
        is_all_day=all_day,
        color_key=EventColorKey.DEFAULT,
        location=location,
        task_id=None,
        is_moved=False,
        is_overridden=False,
        series_key=None,
        alarm=alarm,
        event_type=event_type,
    )


def _at(minutes_from_start: float) -> datetime:
    return START + timedelta(minutes=minutes_from_start)


# ── 送る時刻 ────────────────────────────────────────────────────────────


def test_a_notice_is_due_from_its_time_until_the_grace_runs_out() -> None:
    at = datetime(2026, 10, 5, 0, 45)
    assert not is_due(at, at - timedelta(seconds=1))
    assert is_due(at, at)
    assert is_due(at, at + DUE_GRACE - timedelta(seconds=1))
    assert not is_due(at, at + DUE_GRACE)


def test_event_alarms_follow_the_alarm_setting() -> None:
    occurrence = _occurrence(alarm=EventAlarm.default(), location="会議室A")
    planner = _planner()

    [fifteen] = planner.calendar_notices([occurrence], _at(-15), ALL_ON)
    assert fifteen.kind is PushKind.EVENT_ALARM
    assert fifteen.key == "12:2026-10-05T01:00:00Z:15"
    assert fifteen.title == "設計レビュー"
    assert fifteen.body == "15 分後に始まります（10:00〜） @ 会議室A"
    assert fifteen.url == "/calendar"

    assert planner.calendar_notices([occurrence], _at(-15.1), ALL_ON) == []
    # 15 分前から 5 分たったら、もう 15 分前の通知は送らない（5 分前はまだ）
    assert planner.calendar_notices([occurrence], _at(-10), ALL_ON) == []

    [start] = planner.calendar_notices([occurrence], _at(0), ALL_ON)
    assert start.key == "12:2026-10-05T01:00:00Z:0"
    assert start.body.startswith("始まります（10:00〜）")


def test_when_several_alarms_of_one_occurrence_are_due_only_the_latest_is_sent() -> None:
    occurrence = _occurrence(alarm=EventAlarm.default())
    # 5 分前（-5）も 1 分前（-1）も送れる時刻（遅れて起きた）。開始に近い 1 分前だけ
    [notice] = _planner().calendar_notices([occurrence], _at(-0.5), ALL_ON)
    assert notice.key.endswith(":1")


def test_no_event_alarm_without_an_enabled_alarm_or_for_all_day_or_when_turned_off() -> None:
    planner = _planner()
    now = _at(-15)
    assert planner.calendar_notices([_occurrence(alarm=None)], now, ALL_ON) == []
    disabled = EventAlarm(False, True, True, True, True)
    assert planner.calendar_notices([_occurrence(alarm=disabled)], now, ALL_ON) == []
    off = PushPreferences(event_alarm=False)
    assert planner.calendar_notices([_occurrence(alarm=EventAlarm.default())], now, off) == []
    all_day = _occurrence(alarm=EventAlarm.default(), all_day=True, start=datetime(2026, 10, 4, 15, 0))
    assert planner.calendar_notices([all_day], datetime(2026, 10, 4, 14, 45), ALL_ON) == []


# ── 定常業務 ────────────────────────────────────────────────────────────


def test_a_routine_occurrence_start_is_one_routine_notice_not_two() -> None:
    occurrence = _occurrence(alarm=EventAlarm.default(), event_type=EventType.TASK)
    [notice] = _planner().calendar_notices([occurrence], _at(0), ALL_ON)
    assert notice.kind is PushKind.ROUTINE_START
    assert notice.key == "12:2026-10-05T01:00:00Z"
    assert notice.title == "定常業務: 設計レビュー"
    assert notice.url == "/"

    # 開始より前の通知は予定の通知のまま
    [before] = _planner().calendar_notices([occurrence], _at(-5), ALL_ON)
    assert before.kind is PushKind.EVENT_ALARM


def test_a_routine_start_falls_back_to_the_event_alarm_when_routines_are_off() -> None:
    occurrence = _occurrence(alarm=EventAlarm.default(), event_type=EventType.TASK)
    [notice] = _planner().calendar_notices([occurrence], _at(0), PushPreferences(routine_start=False))
    assert notice.kind is PushKind.EVENT_ALARM
    assert notice.key.endswith(":0")


def test_a_routine_without_an_alarm_still_notifies_its_start() -> None:
    occurrence = _occurrence(alarm=None, event_type=EventType.TASK)
    [notice] = _planner().calendar_notices([occurrence], _at(1), ALL_ON)
    assert notice.kind is PushKind.ROUTINE_START
    assert _planner().calendar_notices([occurrence], _at(1), PushPreferences(routine_start=False)) == []


def test_an_all_day_routine_is_notified_in_the_users_morning() -> None:
    # 10/5 の終日（JST）。朝 8:00 JST = 10/4 23:00Z
    occurrence = _occurrence(event_type=EventType.TASK, all_day=True, start=datetime(2026, 10, 4, 15, 0))
    morning = datetime(2026, 10, 4, 23, 0)
    assert _planner().calendar_notices([occurrence], morning - timedelta(seconds=1), ALL_ON) == []
    [notice] = _planner().calendar_notices([occurrence], morning, ALL_ON)
    assert notice.kind is PushKind.ROUTINE_START
    assert notice.body == "今日の定常業務です"


# ── 打刻の止め忘れ ──────────────────────────────────────────────────────


def _running(started_at: datetime, entry_id: int = 5) -> RunningTimer:
    return RunningTimer(TimeEntry(id=entry_id, user_id=7, started_at=started_at), "設計書")


def test_a_timer_running_past_the_set_hours_is_notified_once_per_entry() -> None:
    now = datetime(2026, 10, 5, 9, 0)
    planner = _planner()
    assert planner.timer_notice(_running(now - timedelta(hours=3, minutes=59)), now, ALL_ON) is None
    notice = planner.timer_notice(_running(now - timedelta(hours=4)), now, ALL_ON)
    assert notice is not None
    assert notice.kind is PushKind.TIMER_LEFT_RUNNING
    assert notice.key == "5"
    assert notice.title == "打刻が 4 時間を超えて動いています"
    assert notice.body == "設計書 — 止め忘れていませんか"
    # 鍵は打刻ごと（何時間たっても同じ鍵 = 1 回だけ）
    later = planner.timer_notice(_running(now - timedelta(hours=10)), now, ALL_ON)
    assert later is not None and later.key == notice.key


def test_timer_notice_respects_the_setting_and_ignores_old_or_stopped_entries() -> None:
    now = datetime(2026, 10, 5, 9, 0)
    planner = _planner()
    assert planner.timer_notice(None, now, ALL_ON) is None
    assert planner.timer_notice(_running(now - timedelta(hours=5)), now, PushPreferences(timer_left_running=False)) is None
    assert planner.timer_notice(_running(now - timedelta(hours=5)), now, PushPreferences(timer_left_running_hours=6)) is None
    assert planner.timer_notice(_running(now - timedelta(days=8)), now, ALL_ON) is None
    stopped = RunningTimer(
        TimeEntry(id=5, user_id=7, started_at=now - timedelta(hours=5), ended_at=now), None
    )
    assert planner.timer_notice(stopped, now, ALL_ON) is None


# ── 締めの時期 ──────────────────────────────────────────────────────────

PENDING = PendingClosings(
    current=HalfMonthPeriod(date(2026, 10, 16), date(2026, 10, 31)),
    pending=[HalfMonthPeriod(date(2026, 10, 1), date(2026, 10, 15))],
)


def test_closing_is_notified_the_morning_after_a_period_ends() -> None:
    planner = _planner()
    # 10/16 7:59 JST はまだ。8:00 JST から、その日のうち
    assert planner.closing_notice(PENDING, datetime(2026, 10, 15, 22, 59), ALL_ON) is None
    notice = planner.closing_notice(PENDING, datetime(2026, 10, 15, 23, 0), ALL_ON)
    assert notice is not None
    assert notice.kind is PushKind.CLOSING_DUE
    assert notice.key == "2026-10-16"
    assert notice.url == "/closing?period=2026-10-01"
    assert notice.body == "未確定の期間が 1 件あります（いちばん古いのは 2026-10-01〜2026-10-15）"
    assert planner.closing_notice(PENDING, datetime(2026, 10, 16, 14, 59), ALL_ON) is not None
    # 翌日（10/17 0:00 JST）からは送らない
    assert planner.closing_notice(PENDING, datetime(2026, 10, 16, 15, 0), ALL_ON) is None


def test_closing_is_not_notified_when_all_periods_are_closed_or_turned_off() -> None:
    planner = _planner()
    morning = datetime(2026, 10, 15, 23, 30)
    assert planner.closing_notice(PendingClosings(PENDING.current, []), morning, ALL_ON) is None
    assert planner.closing_notice(PENDING, morning, PushPreferences(closing_due=False)) is None


def test_texts_follow_the_users_language() -> None:
    notice = _planner("en").closing_notice(PENDING, datetime(2026, 10, 15, 23, 30), ALL_ON)
    assert notice is not None
    assert notice.title == "Time to close"
