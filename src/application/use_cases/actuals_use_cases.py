"""Actuals view: plan vs actuals (task #162 / ADR-0017).

Feeds confirmed actuals (``work_logs``: received from Tracker or entered by hand) back into the plan (task estimates and remaining).
Calendar events and time punches moved to Scheduler and Tracker, so they are not counted (task #543 / ADR-0070).

- Per task (``task_board``): estimate, actual and remaining in one row. After closing, list tasks whose **remaining should be
  revisited**, with reasons (remaining is never reduced automatically, ADR-0010)
- Gantt actuals bars (``gantt``): first and last day of actuals per task, and actuals per day
- Per period (``periods``): confirmed actuals
- Roll-up (``breakdown``): by category, milestone and project (child branches rolled up)
- Export (``export``): period x day x task x hours

All dates are in the user's time zone. Only the user's own actuals are counted.
Each can be narrowed with ``project_id`` to the tasks of that project and its descendants (ADR-0024).
"""

from __future__ import annotations

from datetime import date

from src.application.dto.actuals_dto import (
    UNGROUPED_GROUP,
    Breakdown,
    BreakdownGroup,
    BreakdownGroupBy,
    BreakdownPeriod,
    ClosedPeriod,
    ExportRow,
    GanttActualDay,
    GanttActualSpan,
    PeriodComparison,
    PeriodReport,
    TaskActualsBoard,
    TaskActualsRow,
)
from src.application.use_cases.task_use_cases import TaskUseCases
from src.application.user_clock import UserClock
from src.domain.entities.task import Task
from src.domain.entities.work_log import WorkLog
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.repositories.category_repository import CategoryRepository
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.work_log_repository import WorkLogRepository
from src.domain.services.daily_ledger import DailyLedger
from src.domain.services.project_tree import ProjectTree
from src.domain.services.remaining_review import remaining_review_reasons
from src.domain.value_objects.half_month_period import HalfMonthPeriod
from src.domain.value_objects.report_period import (
    ReportPeriod,
    ReportPeriodUnit,
    recent_report_periods,
    report_periods_between,
)

DEFAULT_PERIOD_COUNT = 6
"""When no range is given, how many periods ending with the current one to list."""

MAX_EXPORT_DAYS = 366
"""Upper limit of the export range (days)."""


class ActualsUseCases:
    def __init__(
        self,
        *,
        clock: UserClock,
        tasks: TaskUseCases,
        task_repository: TaskRepository,
        work_logs: WorkLogRepository,
        categories: CategoryRepository,
        milestones: MilestoneRepository,
        projects: ProjectRepository,
    ) -> None:
        self._clock = clock
        self._tasks = tasks
        self._task_repo = task_repository
        self._work_logs = work_logs
        self._categories = categories
        self._milestones = milestones
        self._projects = projects

    # ── Per task ──────────────────────────────────────────────────────

    def task_board(
        self,
        user_id: int,
        *,
        review_only: bool = False,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> TaskActualsBoard:
        """Estimate, actual and remaining per task, plus reasons to revisit the remaining."""
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

        latest, latest_logs = _latest_closed(logs)
        latest_seconds: dict[int, int] = {}
        for log in latest_logs:
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

    # ── Gantt ──────────────────────────────────────────────────────────

    def gantt(
        self,
        user_id: int,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> list[GanttActualSpan]:
        """Actuals bars per task (from confirmed actuals). Per-day fill only for ``first_day``-``last_day``."""
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

    # ── Per period ────────────────────────────────────────────────────────

    def periods(
        self,
        user_id: int,
        unit: ReportPeriodUnit,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> PeriodReport:
        """Confirmed actuals per period."""
        periods = self._resolve_periods(user_id, unit, first_day, last_day)
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        confirmed = self._ledger(user_id, periods[0].first_day, periods[-1].last_day, scope)
        return PeriodReport(
            unit=unit,
            time_zone=self._clock.zone_name(user_id),
            periods=[
                PeriodComparison(period=p, confirmed_seconds=confirmed.total(p)) for p in periods
            ],
        )

    # ── Roll-up ────────────────────────────────────────────────────────

    def breakdown(
        self,
        user_id: int,
        unit: ReportPeriodUnit,
        group_by: BreakdownGroupBy,
        first_day: date | None = None,
        last_day: date | None = None,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> Breakdown:
        """Roll up hours per period by category, milestone and project.

        By project is **per branch**: without ``project_id``, per top-level project;
        with it, per direct child (each including everything below it) plus what is attached directly to that project.
        """
        periods = self._resolve_periods(user_id, unit, first_day, last_day)
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        ledger = self._ledger(user_id, periods[0].first_day, periods[-1].last_day, scope)
        tree = ProjectTree(self._projects.find_all(user_id))

        # Ordered as the repositories return them (categories by position, milestones by nearest due date, projects in tree order)
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
            task = owned.get(task_id) if task_id is not None else None
            group_id = None if task is None else group_id_of(task)
            key = f"{group_by.value}:{group_id}"
            return key if group_id is not None and key in known_keys else UNGROUPED_GROUP

        rows = [
            BreakdownPeriod(period=p, seconds_by_group=ledger.grouped(p, group_of)) for p in periods
        ]
        used = {key for row in rows for key in row.seconds_by_group}
        groups = [g for g in known if g.key in used]
        if UNGROUPED_GROUP in used:
            groups.append(BreakdownGroup(key=UNGROUPED_GROUP, name=None, color=None))
        return Breakdown(
            unit=unit,
            group_by=group_by,
            time_zone=self._clock.zone_name(user_id),
            groups=groups,
            periods=rows,
        )

    # ── Export ────────────────────────────────────────────────────────

    def export(
        self,
        user_id: int,
        first_day: date,
        last_day: date,
        project_id: int | None = None,
        unclassified: bool = False,
    ) -> list[ExportRow]:
        """Period (half month) x day x task x hours. Ordered by day, then task."""
        if last_day < first_day:
            raise ValidationError("the end of the range must not be before its start")
        if (last_day - first_day).days + 1 > MAX_EXPORT_DAYS:
            raise ValidationError(f"the range must be at most {MAX_EXPORT_DAYS} days")
        owned = self._owned_tasks(user_id)
        scope = self._task_scope(user_id, project_id, unclassified, owned)
        ledger = self._ledger(user_id, first_day, last_day, scope)
        category_names = {c.id: c.name for c in self._categories.find_all(user_id)}
        milestone_names = {m.id: m.name for m in self._milestones.find_all(user_id)}
        rows: list[ExportRow] = []
        for task_id, day, seconds in ledger.entries():
            if task_id is None:
                continue
            task = owned.get(task_id)
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

    # ── Internals ────────────────────────────────────────────────────────────

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
        """Task ids of ``project_id`` and its descendant projects (unclassified if ``unclassified``). None if not narrowed."""
        if unclassified:
            return {task_id for task_id, task in owned.items() if task.project_id is None}
        if project_id is None:
            return None
        projects = set(self._projects.subtree_ids(user_id, project_id))
        if not projects:
            raise NotFoundError("Project", project_id)
        return {task_id for task_id, task in owned.items() if task.project_id in projects}

    def _ledger(
        self, user_id: int, first_day: date, last_day: date, scope: set[int] | None = None
    ) -> DailyLedger:
        """Confirmed actuals for ``first_day``-``last_day`` (user's dates) per (task, day).

        If ``scope`` is given, only the tasks within it.
        """
        ledger = ScopedLedger(scope)
        for log in self._work_logs.find_for_user(user_id, first_day, last_day):
            ledger.add(log.task_id, log.work_date, log.seconds)
        return ledger


def _latest_closed(logs: list[WorkLog]) -> tuple[ClosedPeriod | None, list[WorkLog]]:
    """The closed period most recently received from Tracker and its actuals rows (ADR-0056; None and empty if none received)."""
    delivered = [log for log in logs if log.tracker_first_day is not None]
    if not delivered:
        return None, []
    first_day = max(log.tracker_first_day for log in delivered if log.tracker_first_day)
    latest = [log for log in delivered if log.tracker_first_day == first_day]
    stamps = [s for log in latest for s in (log.updated_at or log.created_at,) if s is not None]
    if not stamps:
        return None, []
    return (
        ClosedPeriod(
            first_day=first_day,
            last_day=max(log.work_date for log in latest),
            closed_at=max(stamps),
        ),
        latest,
    )


class ScopedLedger(DailyLedger):
    """A ledger that does not add tasks outside the filter (or time outside tasks). Adds everything if ``scope`` is None."""

    def __init__(self, scope: set[int] | None) -> None:
        super().__init__()
        self._scope = scope

    def add(self, task_id: int | None, day: date, seconds: int) -> None:
        if self._scope is not None and task_id not in self._scope:
            return
        super().add(task_id, day, seconds)


__all__ = ["DEFAULT_PERIOD_COUNT", "MAX_EXPORT_DAYS", "ActualsUseCases"]
