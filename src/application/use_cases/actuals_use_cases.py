"""実績の見える化: 予定 vs 実績・計画 vs 実績（task #162 / ADR-0017）。

確定した実績（``work_logs``）を計画（タスクの見積・残）と予定（カレンダーの回）へ返す。

- タスクごと（``task_board``）: 見積・予定済み・実績・残を 1 行に。締めの後に**残を見直す**
  タスクを理由つきで挙げる（残は自動で減らさない。ADR-0010）
- ガントの実績の帯（``gantt``）: タスクごとの実績の最初と最後の日・日ごとの実績
- 期間ごと（``periods``）: 予定した時間と打刻の差、タスク外の割合、確定実績
- 積み上げ（``breakdown``）: カテゴリ別・マイルストーン別・プロジェクト別（子の枝を積み上げる）
- 書き出し（``export``）: 期間 × 日 × タスク × 時間

日付はすべて利用者のタイムゾーン。数えるのは本人の予定・打刻・実績だけ。
どれも ``project_id`` で、そのプロジェクトと子孫のタスクの分だけに絞れる（タスク外の時間は
どのプロジェクトにも属さないので、絞ると数えない。ADR-0024）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime

from src.application.dto.actuals_dto import (
    UNASSIGNED_GROUP,
    UNGROUPED_GROUP,
    Breakdown,
    BreakdownGroup,
    BreakdownGroupBy,
    BreakdownPeriod,
    ExportRow,
    GanttActualDay,
    GanttActualSpan,
    PeriodComparison,
    PeriodReport,
    TaskActualsBoard,
    TaskActualsRow,
    TimeSource,
)
from src.application.ports.occurrence_source import OccurrenceSource
from src.application.use_cases.ownership import owned_by
from src.application.use_cases.task_use_cases import TaskUseCases
from src.application.user_clock import UserClock
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.task import Task
from src.domain.exceptions import ValidationError
from src.domain.repositories.category_repository import CategoryRepository
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.repositories.work_log_repository import WorkLogRepository
from src.domain.services.daily_ledger import DailyLedger
from src.domain.services.daily_time_allocation import allocate_by_local_day, whole_seconds
from src.domain.services.project_tree import ProjectTree
from src.domain.services.remaining_review import remaining_review_reasons
from src.domain.value_objects.half_month_period import HalfMonthPeriod
from src.domain.value_objects.report_period import (
    ReportPeriod,
    ReportPeriodUnit,
    recent_report_periods,
    report_periods_between,
)
from src.shared.clock import utcnow

DEFAULT_PERIOD_COUNT = 6
"""範囲を指さないとき、今の期間で終わる何期間を並べるか。"""

MAX_EXPORT_DAYS = 366
"""書き出しの範囲の上限（日）。"""


class ActualsUseCases:
    def __init__(
        self,
        *,
        clock: UserClock,
        tasks: TaskUseCases,
        task_repository: TaskRepository,
        work_logs: WorkLogRepository,
        time_entries: TimeEntryRepository,
        closing_periods: ClosingPeriodRepository,
        categories: CategoryRepository,
        milestones: MilestoneRepository,
        projects: ProjectRepository,
        occurrences: OccurrenceSource,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock
        self._tasks = tasks
        self._task_repo = task_repository
        self._work_logs = work_logs
        self._time_entries = time_entries
        self._closing_periods = closing_periods
        self._categories = categories
        self._milestones = milestones
        self._projects = projects
        self._occurrences = occurrences
        # 既定は作るときに引く（試験でモジュールの utcnow を差し替えられるように）
        self._now = now or utcnow

    # ── タスクごと ──────────────────────────────────────────────────────

    def task_board(
        self,
        user_id: int,
        *,
        review_only: bool = False,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> TaskActualsBoard:
        """タスクごとの見積・予定済み・実績・残と、残を見直してほしい理由。"""
        filters: dict = {}
        if project_id is not None:
            filters["project_id"] = project_id
        if unclassified:
            filters["unclassified"] = True
        task_rows = self._tasks.list_tasks(user_id, filters)
        entities = self._owned_tasks(user_id)
        logs = self._work_logs.find_for_user(user_id)
        ledger = DailyLedger()
        for log in logs:
            ledger.add(log.task_id, log.work_date, log.seconds)
        spans = ledger.span_by_task()

        latest = self._latest_closed(user_id)
        latest_seconds: dict[int, int] = {}
        if latest is not None:
            for log in logs:
                if log.closing_period_id == latest.id:
                    latest_seconds[log.task_id] = latest_seconds.get(log.task_id, 0) + log.seconds

        rows: list[TaskActualsRow] = []
        for row in task_rows:
            task_id: int = row["id"]
            entity = entities.get(task_id)
            closed_hours = round(latest_seconds.get(task_id, 0) / 3600, 2)
            reasons = (
                remaining_review_reasons(
                    entity,
                    actual_hours=row["actual_hours"],
                    has_subtasks=row["has_subtasks"],
                    latest_closed_hours=closed_hours,
                    latest_closed_at=latest.closed_at if latest is not None else None,
                )
                if entity is not None
                else []
            )
            if review_only and not reasons:
                continue
            first, last = spans.get(task_id, (None, None))
            rows.append(
                TaskActualsRow(
                    task=row,
                    actual_first_date=first,
                    actual_last_date=last,
                    latest_closed_hours=closed_hours,
                    review_reasons=reasons,
                )
            )
        return TaskActualsBoard(latest_closed=latest, rows=rows)

    # ── ガント ──────────────────────────────────────────────────────────

    def gantt(
        self,
        user_id: int,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> list[GanttActualSpan]:
        """タスクごとの実績の帯（確定した実績から）。日ごとの塗りは ``first_day``〜``last_day`` だけ。"""
        if first_day is not None and last_day is not None and last_day < first_day:
            raise ValidationError("the end of the range must not be before its start")
        scope = self._task_scope(user_id, project_id, unclassified, self._owned_tasks(user_id))
        ledger = DailyLedger()
        for log in self._work_logs.find_for_user(user_id):
            if scope is None or log.task_id in scope:
                ledger.add(log.task_id, log.work_date, log.seconds)
        days: dict[int, list[GanttActualDay]] = {}
        for task_id, day, seconds in ledger.entries():
            if task_id is None:
                continue
            if (first_day is None or day >= first_day) and (last_day is None or day <= last_day):
                days.setdefault(task_id, []).append(GanttActualDay(work_date=day, seconds=seconds))
        return [
            GanttActualSpan(
                task_id=task_id, first_date=first, last_date=last, days=days.get(task_id, [])
            )
            for task_id, (first, last) in sorted(ledger.span_by_task().items())
        ]

    # ── 期間ごと ────────────────────────────────────────────────────────

    def periods(
        self,
        user_id: int,
        unit: ReportPeriodUnit,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> PeriodReport:
        """期間ごとの予定と実際の時間の差・タスク外の割合。"""
        periods = self._resolve_periods(user_id, unit, first_day, last_day)
        window_first, window_last = periods[0].first_day, periods[-1].last_day
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        window = (user_id, window_first, window_last, owned, scope)
        planned = self._ledger(TimeSource.PLANNED, *window)
        tracked = self._ledger(TimeSource.TRACKED, *window)
        confirmed = self._ledger(TimeSource.CONFIRMED, *window)
        closed_days = (
            self._closing_periods.list_first_days(user_id)
            if unit is ReportPeriodUnit.CLOSING
            else None
        )
        return PeriodReport(
            unit=unit,
            time_zone=self._clock.zone_name(user_id),
            periods=[
                PeriodComparison(
                    period=p,
                    closed=(p.first_day in closed_days) if closed_days is not None else None,
                    planned_task_seconds=planned.total(p, task_only=True),
                    planned_off_task_seconds=planned.total(p, task_only=False),
                    tracked_task_seconds=tracked.total(p, task_only=True),
                    tracked_off_task_seconds=tracked.total(p, task_only=False),
                    confirmed_seconds=confirmed.total(p),
                )
                for p in periods
            ],
        )

    # ── 積み上げ ────────────────────────────────────────────────────────

    def breakdown(
        self,
        user_id: int,
        unit: ReportPeriodUnit,
        group_by: BreakdownGroupBy,
        source: TimeSource,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> Breakdown:
        """期間ごとの時間を、カテゴリ別・マイルストーン別・プロジェクト別に積み上げる。

        プロジェクト別は**枝ごと**: ``project_id`` を指さなければ最上位のプロジェクトごと、
        指せばその直下の子ごと（それぞれ孫より下の分も積む）と、そのプロジェクトに直に付いた分。
        """
        periods = self._resolve_periods(user_id, unit, first_day, last_day)
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        ledger = self._ledger(
            source, user_id, periods[0].first_day, periods[-1].last_day, owned, scope
        )
        tree = ProjectTree(self._projects.find_all(user_id))

        # 並びはリポジトリの順（カテゴリは並び順、マイルストーンは期限の近い順、プロジェクトは木の順）
        if group_by is BreakdownGroupBy.CATEGORY:
            known = [
                BreakdownGroup(key=f"category:{c.id}", name=c.name, color=c.color)
                for c in self._categories.find_all(user_id)
            ]
        elif group_by is BreakdownGroupBy.MILESTONE:
            known = [
                BreakdownGroup(key=f"milestone:{m.id}", name=m.name, color=None)
                for m in self._milestones.find_all(user_id)
            ]
        else:
            top = tree.get(project_id)
            heads = ([top] if top is not None else []) + tree.children_of(project_id)
            known = [
                BreakdownGroup(key=f"project:{p.id}", name=p.name, color=p.color) for p in heads
            ]
        known_keys = {g.key for g in known}

        def group_id_of(task: Task) -> int | None:
            if group_by is BreakdownGroupBy.CATEGORY:
                return task.category_id
            if group_by is BreakdownGroupBy.MILESTONE:
                return task.milestone_id
            return tree.group_under(task.project_id, project_id)

        def group_of(task_id: int | None) -> str:
            if task_id is None:
                return UNASSIGNED_GROUP
            task = owned.get(task_id)
            group_id = None if task is None else group_id_of(task)
            key = f"{group_by.value}:{group_id}"
            return key if group_id is not None and key in known_keys else UNGROUPED_GROUP

        rows = [
            BreakdownPeriod(period=p, seconds_by_group=ledger.grouped(p, group_of)) for p in periods
        ]
        used = {key for row in rows for key in row.seconds_by_group}
        groups = [g for g in known if g.key in used]
        for key in (UNGROUPED_GROUP, UNASSIGNED_GROUP):
            if key in used:
                groups.append(BreakdownGroup(key=key, name=None, color=None))
        return Breakdown(
            unit=unit,
            group_by=group_by,
            source=source,
            time_zone=self._clock.zone_name(user_id),
            groups=groups,
            periods=rows,
        )

    # ── 書き出し ────────────────────────────────────────────────────────

    def export(
        self,
        user_id: int,
        first_day: date,
        last_day: date,
        source: TimeSource,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> list[ExportRow]:
        """期間（締めの期間）× 日 × タスク × 時間。日の順・タスクの順（タスク外は後ろ）。"""
        if last_day < first_day:
            raise ValidationError("the end of the range must not be before its start")
        if (last_day - first_day).days + 1 > MAX_EXPORT_DAYS:
            raise ValidationError(f"the range must be at most {MAX_EXPORT_DAYS} days")
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        ledger = self._ledger(source, user_id, first_day, last_day, owned, scope)
        category_names = {c.id: c.name for c in self._categories.find_all(user_id)}
        milestone_names = {m.id: m.name for m in self._milestones.find_all(user_id)}
        rows: list[ExportRow] = []
        for task_id, day, seconds in ledger.entries():
            task = owned.get(task_id) if task_id is not None else None
            half = HalfMonthPeriod.containing(day)
            rows.append(
                ExportRow(
                    period=ReportPeriod(half.first_day, half.last_day),
                    work_date=day,
                    task_id=task_id,
                    task_title=task.title if task is not None else None,
                    category_name=(
                        category_names.get(task.category_id)
                        if task is not None and task.category_id is not None
                        else None
                    ),
                    milestone_name=(
                        milestone_names.get(task.milestone_id)
                        if task is not None and task.milestone_id is not None
                        else None
                    ),
                    seconds=seconds,
                )
            )
        return rows

    # ── 内側 ────────────────────────────────────────────────────────────

    def _resolve_periods(
        self, user_id: int, unit: ReportPeriodUnit, first_day: date | None, last_day: date | None
    ) -> list[ReportPeriod]:
        if first_day is None and last_day is None:
            return recent_report_periods(unit, self._clock.today(user_id), DEFAULT_PERIOD_COUNT)
        if first_day is None or last_day is None:
            end = last_day or self._clock.today(user_id)
            start = first_day or recent_report_periods(unit, end, DEFAULT_PERIOD_COUNT)[0].first_day
            return report_periods_between(unit, start, end)
        return report_periods_between(unit, first_day, last_day)

    def _owned_tasks(self, user_id: int) -> dict[int, Task]:
        return {t.id: t for t in self._task_repo.find_all(user_id, {}) if t.id is not None}

    def _task_scope(
        self, user_id: int, project_id: int | None, unclassified: bool, owned: dict[int, Task]
    ) -> set[int] | None:
        """``project_id`` と子孫のプロジェクト（``unclassified`` なら未分類）のタスクの id。絞らないなら None。"""
        if unclassified:
            return {task_id for task_id, task in owned.items() if task.project_id is None}
        if project_id is None:
            return None
        projects = set(self._projects.subtree_ids(user_id, project_id))
        if not projects:
            owned_by(
                self._projects.find_by_id(project_id), user_id,
                resource="Project", resource_id=project_id,
            )
        return {task_id for task_id, task in owned.items() if task.project_id in projects}

    def _latest_closed(self, user_id: int) -> ClosingPeriod | None:
        first_days = self._closing_periods.list_first_days(user_id)
        if not first_days:
            return None
        return self._closing_periods.find_by_first_day(user_id, max(first_days))

    def _ledger(
        self,
        source: TimeSource,
        user_id: int,
        first_day: date,
        last_day: date,
        owned: dict[int, Task],
        scope: set[int] | None = None,
    ) -> DailyLedger:
        """``first_day``〜``last_day``（利用者の日付）の時間を（タスク, 日）ごとに。

        ``scope`` があれば、その中のタスクの分だけ（タスク外の時間も数えない）。
        """
        ledger = ScopedLedger(scope)
        if source is TimeSource.CONFIRMED:
            for log in self._work_logs.find_for_user(user_id, first_day, last_day):
                ledger.add(log.task_id, log.work_date, log.seconds)
            return ledger
        if source is TimeSource.PLANNED:
            # 回はその始まりの日に数える（日をまたぐ回も割らない）。終日の回は作業の時間ではない（ADR-0014）
            for occurrence in self._occurrences.list_occurrence_views(
                user_id, first_day, last_day, self._clock.zone_name(user_id)
            ):
                if occurrence.is_all_day:
                    continue
                task_id = occurrence.task_id if occurrence.task_id in owned else None
                ledger.add(task_id, occurrence.date, occurrence.duration_minutes * 60)
            return ledger
        # 打刻: 日をまたぐ打刻は利用者の 0:00 で割る（締めと同じ割り方）。タスクが空・消えた・他人のものはタスク外
        start, end = self._clock.utc_window(user_id, first_day, last_day)
        entries = self._time_entries.find_overlapping(user_id, start, end)
        allocated = allocate_by_local_day(
            entries, start, end, self._clock.zone(user_id), self._now()
        )
        for (task_id, day), length in allocated.items():
            ledger.add(task_id if task_id in owned else None, day, whole_seconds(length))
        return ledger


class ScopedLedger(DailyLedger):
    """絞り込みの外のタスク（とタスク外の時間）を足さない帳簿。``scope`` が None なら全部足す。"""

    def __init__(self, scope: set[int] | None) -> None:
        super().__init__()
        self._scope = scope

    def add(self, task_id: int | None, day: date, seconds: int) -> None:
        if self._scope is not None and task_id not in self._scope:
            return
        super().add(task_id, day, seconds)


__all__ = ["DEFAULT_PERIOD_COUNT", "MAX_EXPORT_DAYS", "ActualsUseCases"]
