"""いま送る通知を決める（task #193 / ADR-0031 の 4）。

送る係（``DispatchPushNotices``）が周回ごとに、利用者 1 人ぶんの事実（予定の回・走っている打刻・
未確定の締めの期間）と「今」を渡し、**いま送るべき通知**を受け取る。DB にも時計にも触らない
純粋な判定だけをここに置く（送る時刻の判定の試験はここを叩く）。

- **予定の通知**: 回の開始の 15 / 5 / 1 / 0 分前（予定のアラームの設定どおり。ADR-0021）。
  遅れても ``DUE_GRACE`` の間なら送る。同じ回で同時に送れるものが 2 つ以上あれば、いちばん
  遅い（開始に近い）1 つだけ。終日の回は送らない（ADR-0021 と同じ）
- **定常業務の回の開始**: 分類がタスクの予定（ADR-0025）の回の開始。終日の回は利用者の
  その日の ``MORNING_HOUR`` 時。⚠ 開始時刻ちょうどの予定の通知とは同じ時刻なので 1 通にまとめ、
  定常業務の通知として出す（定常業務を切っていれば、予定の通知の「開始時刻」として出す）
- **打刻の止め忘れ**: 走っている打刻が設定の時間（既定 4 時間）を超えたら 1 本につき 1 回。
  7 日より前に始まった打刻は送らない（打刻アプリの上限と同じ。古い止め忘れは締めの画面で直す）
- **締めの時期**: 期間が終わった翌朝（新しい期間の初日の ``MORNING_HOUR`` 時以降、その日のうち）に、
  未確定の期間があれば 1 回

送ったかどうかはここでは見ない（同じ通知を毎周回返す。2 度送らないのは送った記録の仕事）。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta, tzinfo

from src.application.dto.calendar_event_dto import OccurrenceView
from src.application.dto.closing_dto import PendingClosings
from src.domain.entities.calendar_event import EventType
from src.domain.entities.time_entry import TimeEntry
from src.domain.value_objects.push_kind import PushKind
from src.domain.value_objects.push_notice import PushNotice
from src.domain.value_objects.push_preferences import PushPreferences
from src.shared.clock import isoformat_utc

#: 時刻の来た通知を、遅れても送ってよい長さ。送る係の間隔（60 秒）より十分長く取る
#: （1 周回落ちても拾える）。それより遅れた通知は送らない（遅れた予定の通知は意味が無い）。
DUE_GRACE = timedelta(minutes=5)
#: 終日の定常業務・締めの時期を知らせる、利用者のタイムゾーンの時刻。
MORNING_HOUR = 8
#: これより前に始まった打刻は、止め忘れを知らせない。
TIMER_LOOKBACK = timedelta(days=7)

_TEXTS: dict[str, dict[str, str]] = {
    "ja": {
        "alarm.soon": "{minutes} 分後に始まります（{start}〜）",
        "alarm.now": "始まります（{start}〜）",
        "routine.title": "定常業務: {title}",
        "routine.at": "始める時刻です（{start}〜）",
        "routine.allDay": "今日の定常業務です",
        "timer.title": "打刻が {hours} 時間を超えて動いています",
        "timer.body": "{task} — 止め忘れていませんか",
        "timer.unassigned": "タスク未割当",
        "closing.title": "締めの時期です",
        "closing.body": "未確定の期間が {count} 件あります（いちばん古いのは {from}〜{to}）",
    },
    "en": {
        "alarm.soon": "Starts in {minutes} min ({start})",
        "alarm.now": "Starting now ({start})",
        "routine.title": "Routine: {title}",
        "routine.at": "Time to start ({start})",
        "routine.allDay": "Today's routine",
        "timer.title": "The timer has been running for over {hours} h",
        "timer.body": "{task} — did you forget to stop it?",
        "timer.unassigned": "No task",
        "closing.title": "Time to close",
        "closing.body": "{count} periods are not closed yet (the oldest is {from}–{to})",
    },
}


def is_due(at: datetime, now: datetime) -> bool:
    """``at`` に送る通知を、``now`` に送るか（``at ≤ now < at + DUE_GRACE``）。"""
    return at <= now < at + DUE_GRACE


def local_moment(day: date, hour: int, zone: tzinfo) -> datetime:
    """``zone`` での ``day`` の ``hour`` 時の瞬間（naive な UTC）。"""
    return datetime.combine(day, time(hour), tzinfo=zone).astimezone(UTC).replace(tzinfo=None)


def _local_now(now: datetime, zone: tzinfo) -> datetime:
    return now.replace(tzinfo=UTC).astimezone(zone)


@dataclass(frozen=True)
class RunningTimer:
    entry: TimeEntry
    #: 結んだタスクの題名（未割当・消えた・他人のものなら ``None``）
    task_title: str | None


class PushNoticePlanner:
    def __init__(self, user_id: int, zone: tzinfo, language: str) -> None:
        self._user_id = user_id
        self._zone = zone
        self._texts = _TEXTS.get(language, _TEXTS["ja"])

    def _text(self, key: str, **params: object) -> str:
        return self._texts[key].format(**params)

    # ── 予定 ───────────────────────────────────────────────────────────

    def calendar_notices(
        self, occurrences: list[OccurrenceView], now: datetime, preferences: PushPreferences
    ) -> list[PushNotice]:
        notices: list[PushNotice] = []
        for occurrence in occurrences:
            is_routine = occurrence.event_type == EventType.TASK and preferences.routine_start
            if is_routine and (notice := self._routine_start(occurrence, now)) is not None:
                notices.append(notice)
            if preferences.event_alarm and (
                notice := self._event_alarm(occurrence, now, skip_at_start=is_routine)
            ) is not None:
                notices.append(notice)
        return notices

    def _routine_start(self, occurrence: OccurrenceView, now: datetime) -> PushNotice | None:
        if occurrence.is_all_day:
            at = local_moment(occurrence.date, MORNING_HOUR, self._zone)
            body = self._text("routine.allDay")
        else:
            at = occurrence.start_utc
            body = self._text("routine.at", start=occurrence.start_time.strftime("%H:%M"))
        if not is_due(at, now):
            return None
        return PushNotice(
            user_id=self._user_id,
            kind=PushKind.ROUTINE_START,
            key=f"{occurrence.event_id}:{isoformat_utc(occurrence.start_utc)}",
            title=self._text("routine.title", title=occurrence.title),
            body=body,
            url="/",
        )

    def _event_alarm(
        self, occurrence: OccurrenceView, now: datetime, *, skip_at_start: bool
    ) -> PushNotice | None:
        if occurrence.is_all_day or occurrence.alarm is None:
            return None
        due = [
            minutes
            for minutes in occurrence.alarm.minutes_before()
            if is_due(occurrence.start_utc - timedelta(minutes=minutes), now)
        ]
        if not due:
            return None
        # 同じ回で時刻の来たものが重なったら、開始に近い 1 つだけ（遅れて起きたときに 2 通出さない）。
        # 開始時刻ちょうどが定常業務の通知にまとまるなら、ここからは出さない
        minutes = min(due)
        if minutes == 0 and skip_at_start:
            return None
        start = occurrence.start_time.strftime("%H:%M")
        body = (
            self._text("alarm.soon", minutes=minutes, start=start)
            if minutes > 0
            else self._text("alarm.now", start=start)
        )
        if occurrence.location:
            body = f"{body} @ {occurrence.location}"
        return PushNotice(
            user_id=self._user_id,
            kind=PushKind.EVENT_ALARM,
            # 打刻アプリの「この先の通知」の id と同じ形（ADR-0021）
            key=f"{occurrence.event_id}:{isoformat_utc(occurrence.start_utc)}:{minutes}",
            title=occurrence.title,
            body=body,
            url="/calendar",
        )

    # ── 打刻 ───────────────────────────────────────────────────────────

    def timer_notice(
        self, running: RunningTimer | None, now: datetime, preferences: PushPreferences
    ) -> PushNotice | None:
        if running is None or not preferences.timer_left_running:
            return None
        entry = running.entry
        if entry.id is None or not entry.is_running:
            return None
        hours = preferences.timer_left_running_hours
        if not now - TIMER_LOOKBACK <= entry.started_at <= now - timedelta(hours=hours):
            return None
        return PushNotice(
            user_id=self._user_id,
            kind=PushKind.TIMER_LEFT_RUNNING,
            key=str(entry.id),
            title=self._text("timer.title", hours=hours),
            body=self._text("timer.body", task=running.task_title or self._text("timer.unassigned")),
            url="/",
        )

    # ── 締め ───────────────────────────────────────────────────────────

    def closing_notice(
        self, pending: PendingClosings, now: datetime, preferences: PushPreferences
    ) -> PushNotice | None:
        if not preferences.closing_due or not pending.pending:
            return None
        local_now = _local_now(now, self._zone)
        if local_now.date() != pending.current.first_day or local_now.hour < MORNING_HOUR:
            return None
        oldest = pending.pending[0]
        return PushNotice(
            user_id=self._user_id,
            kind=PushKind.CLOSING_DUE,
            key=pending.current.first_day.isoformat(),
            title=self._text("closing.title"),
            body=self._text(
                "closing.body",
                count=len(pending.pending),
                **{"from": oldest.first_day.isoformat(), "to": oldest.last_day.isoformat()},
            ),
            url=f"/closing?period={oldest.first_day.isoformat()}",
        )


__all__ = [
    "DUE_GRACE",
    "MORNING_HOUR",
    "TIMER_LOOKBACK",
    "PushNoticePlanner",
    "RunningTimer",
    "is_due",
    "local_moment",
]
