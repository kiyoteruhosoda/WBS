"""締め（月 2 回の補正と確定。task #161 / #163 / ADR-0012）。

- 期間: 1〜15 日 / 16 日〜末日。利用者のタイムゾーンの 0:00 で区切る（``HalfMonthPeriod``）
- 画面 1 枚分（``board``）: 期間の打刻・予定の回・日ごとタスクごとの合計・気付かせる物
- 確定（``close``）: 期間の打刻を利用者の日付ごと・タスクごとに足して ``work_logs``
  （``source=closing``）を作る。日をまたぐ打刻は 0:00 で割る。丸めない。
  走っている打刻・未割当の打刻が期間に掛かっていれば断る（409）
- 開け直し（``reopen``）: 本人ができる。その期間から作った ``work_logs`` を消し、期間を未確定へ
- 未確定の期間（``pending``）: いちばん古い打刻の期間から、今の期間の前までで確定していないもの

確定済みの期間に掛かる打刻を書き換えさせない検査は ``TimeEntryUseCases`` が行う。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal

from src.application.dto.closing_dto import (
    ClosingBoard,
    ClosingFindings,
    ClosingPeriodState,
    ClosingResult,
    DailyTaskTotal,
    OverlapFinding,
    PendingClosings,
)
from src.application.ports.occurrence_source import NoOccurrences, OccurrenceSource
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.time_entry_use_cases import build_time_entry_view
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import ConflictError, ValidationError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.repositories.work_log_repository import WorkLogRepository
from src.domain.services.closing_review import find_overlaps, is_uncovered
from src.domain.services.daily_time_allocation import allocate_by_local_day, whole_seconds
from src.domain.value_objects.half_month_period import HalfMonthPeriod, local_date_of
from src.domain.value_objects.time_zone import TimeZoneId
from src.domain.value_objects.work_log_source import WorkLogSource
from src.shared.clock import utcnow

HOURS_QUANTUM = Decimal("0.01")
"""``work_logs.hours`` の桁（``NUMERIC(5, 2)``）。正確な長さは ``duration_seconds`` に持つ。"""

MAX_PENDING_PERIODS = 48
"""未確定の期間を数える上限（2 年分）。それより古い打刻があっても、ここで打ち切る。"""


class ClosingUseCases:
    def __init__(
        self,
        periods: ClosingPeriodRepository,
        entries: TimeEntryRepository,
        work_logs: WorkLogRepository,
        tasks: OwnedTaskLookup,
        unit_of_work: UnitOfWork,
        *,
        occurrences: OccurrenceSource | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._periods = periods
        self._entries = entries
        self._work_logs = work_logs
        self._tasks = tasks
        self._uow = unit_of_work
        self._occurrences = occurrences or NoOccurrences()
        self._now = now

    # ── 引く ────────────────────────────────────────────────────────────

    def board(self, user_id: int, first_day: date, time_zone: str) -> ClosingBoard:
        """締めの画面 1 枚分。確定済みの期間は確定したときの区切り・タイムゾーンで出す。"""
        now = self._now()
        state = self._state(user_id, HalfMonthPeriod.starting_on(first_day), TimeZoneId(time_zone))
        zone = TimeZoneId(state.time_zone)
        entries = self._entries.find_overlapping(user_id, state.starts_at, state.ends_at)
        occurrences = self._occurrences.list_occurrence_views(
            user_id, state.period.first_day, state.period.last_day, zone.name
        )
        titles: dict[int, str | None] = {}
        projects: dict[int, int | None] = {}
        views = [build_time_entry_view(e, now, self._tasks, titles) for e in entries]
        totals = allocate_by_local_day(entries, state.starts_at, state.ends_at, zone.zone, now)
        daily = [
            DailyTaskTotal(
                work_date=day,
                task_id=task_id,
                task_title=self._title(task_id, user_id, titles),
                project_id=self._project_id(task_id, user_id, projects),
                seconds=whole_seconds(length),
            )
            for (task_id, day), length in sorted(
                totals.items(), key=lambda kv: (kv[0][1], kv[0][0] is None, kv[0][0] or 0)
            )
        ]
        missed = [
            o
            for o in occurrences
            if not o.is_all_day
            and (end := o.start_utc + timedelta(minutes=o.duration_minutes)) <= now
            and is_uncovered(o.start_utc, end, entries, now)
        ]
        findings = ClosingFindings(
            long_running_entry_ids=[
                e.id for e in entries if e.id is not None and e.is_long_running(now)
            ],
            overlaps=[
                OverlapFinding(o.first_entry_id, o.second_entry_id, whole_seconds(o.overlap))
                for o in find_overlaps(entries, now)
            ],
            unassigned_entry_ids=self._unassigned_ids(entries, user_id),
            missed_occurrences=missed,
        )
        return ClosingBoard(
            state=state,
            entries=views,
            occurrences=occurrences,
            daily_totals=daily,
            findings=findings,
        )

    def pending(self, user_id: int, time_zone: str) -> PendingClosings:
        zone = TimeZoneId(time_zone)
        current = HalfMonthPeriod.containing(local_date_of(self._now(), zone.zone))
        earliest = self._entries.find_earliest_started_at(user_id)
        if earliest is None:
            return PendingClosings(current=current, pending=[])
        closed = self._periods.list_first_days(user_id)
        start = HalfMonthPeriod.containing(local_date_of(earliest, zone.zone))
        oldest_counted = current
        for _ in range(MAX_PENDING_PERIODS):
            if oldest_counted <= start:
                break
            oldest_counted = oldest_counted.previous()
        period = max(start, oldest_counted)
        pending: list[HalfMonthPeriod] = []
        while period < current:
            if period.first_day not in closed:
                pending.append(period)
            period = period.next()
        return PendingClosings(current=current, pending=pending)

    # ── 確定・開け直し ───────────────────────────────────────────────────

    def close(self, user_id: int, first_day: date, time_zone: str) -> ClosingResult:
        """期間を確定し、打刻から ``work_logs``（``source=closing``）を作る。"""
        now = self._now()
        period = HalfMonthPeriod.starting_on(first_day)
        zone = TimeZoneId(time_zone)
        if self._periods.find_by_first_day(user_id, period.first_day) is not None:
            raise ConflictError("This closing period is already closed")
        closing = ClosingPeriod.close(user_id=user_id, period=period, time_zone=zone, now=now)
        if closing.starts_at > now:
            raise ValidationError("a closing period that has not started cannot be closed")

        entries = self._entries.find_overlapping(user_id, closing.starts_at, closing.ends_at)
        running = [e.id for e in entries if e.is_running]
        if running:
            raise ConflictError(
                f"A running time entry overlaps this period (id={running[0]}); stop it first"
            )
        unassigned = self._unassigned_ids(entries, user_id)
        if unassigned:
            raise ConflictError(
                "Time entries without a task overlap this period"
                f" (ids={','.join(str(i) for i in unassigned)}); assign a task or delete them"
            )

        saved_period = self._periods.save(closing)
        assert saved_period.id is not None
        totals = allocate_by_local_day(entries, closing.starts_at, closing.ends_at, zone.zone, now)
        created: list[WorkLog] = []
        for (task_id, day), length in sorted(
            totals.items(), key=lambda kv: (kv[0][1], kv[0][0] or 0)
        ):
            assert task_id is not None
            seconds = whole_seconds(length)
            if seconds <= 0:
                continue
            created.append(
                self._work_logs.save(
                    WorkLog(
                        id=None,
                        user_id=user_id,
                        task_id=task_id,
                        work_date=day,
                        hours=hours_of(seconds),
                        source=WorkLogSource.CLOSING,
                        closing_period_id=saved_period.id,
                        duration_seconds=seconds,
                    )
                )
            )
        self._uow.commit()
        return ClosingResult(state=self._state_of(saved_period), work_logs=created)

    def reopen(self, user_id: int, first_day: date) -> int:
        """開け直す（本人ができる）。その期間から作った ``work_logs`` を消し、消した数を返す。"""
        period = HalfMonthPeriod.starting_on(first_day)
        closed = self._periods.find_by_first_day(user_id, period.first_day)
        if closed is None or closed.id is None:
            raise ConflictError("This closing period is not closed")
        removed = self._work_logs.delete_by_closing_period(closed.id)
        self._periods.delete(closed.id)
        self._uow.commit()
        return removed

    def work_logs_of(self, user_id: int, first_day: date) -> list[WorkLog]:
        """確定で作った ``work_logs``（未確定なら空）。"""
        closed = self._periods.find_by_first_day(
            user_id, HalfMonthPeriod.starting_on(first_day).first_day
        )
        if closed is None or closed.id is None:
            return []
        return self._work_logs.find_by_closing_period(closed.id)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _state(self, user_id: int, period: HalfMonthPeriod, zone: TimeZoneId) -> ClosingPeriodState:
        closed = self._periods.find_by_first_day(user_id, period.first_day)
        if closed is not None:
            return self._state_of(closed)
        starts_at, ends_at = period.utc_window(zone.zone)
        return ClosingPeriodState(
            period=period, time_zone=zone.name, starts_at=starts_at, ends_at=ends_at, closed=None
        )

    @staticmethod
    def _state_of(closed: ClosingPeriod) -> ClosingPeriodState:
        return ClosingPeriodState(
            period=closed.period,
            time_zone=closed.time_zone,
            starts_at=closed.starts_at,
            ends_at=closed.ends_at,
            closed=closed,
        )

    def _unassigned_ids(self, entries: list[TimeEntry], user_id: int) -> list[int]:
        owned: dict[int, bool] = {}
        found: list[int] = []
        for e in entries:
            if e.id is None:
                continue
            if e.task_id is None:
                found.append(e.id)
                continue
            if e.task_id not in owned:
                owned[e.task_id] = self._tasks.find_by_id_for_user(e.task_id, user_id) is not None
            if not owned[e.task_id]:
                found.append(e.id)
        return found

    def _title(
        self, task_id: int | None, user_id: int, titles: dict[int, str | None]
    ) -> str | None:
        if task_id is None:
            return None
        if task_id not in titles:
            task = self._tasks.find_by_id_for_user(task_id, user_id)
            titles[task_id] = task.title if task is not None else None
        return titles[task_id]

    def _project_id(
        self, task_id: int | None, user_id: int, projects: dict[int, int | None]
    ) -> int | None:
        """合計の行のプロジェクト（いまのタスクの所属。未割当・消えたタスク・未分類は None）。"""
        if task_id is None:
            return None
        if task_id not in projects:
            task = self._tasks.find_by_id_for_user(task_id, user_id)
            projects[task_id] = task.project_id if task is not None else None
        return projects[task_id]


def hours_of(seconds: int) -> Decimal:
    """``work_logs.hours`` へ入れる値（小数 2 桁。正確な長さは ``duration_seconds``）。"""
    return (Decimal(seconds) / Decimal(3600)).quantize(HOURS_QUANTUM, rounding=ROUND_HALF_UP)


__all__ = ["ClosingUseCases", "hours_of"]
