from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.application.ports.scheduled_time_lookup import ScheduledTimeLookup
from src.application.use_cases.ownership import owned_by
from src.application.use_cases.project_membership import ProjectMembership
from src.application.user_clock import UserClock
from src.domain.entities.task import Task
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.project_tree import ProjectTree
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository

SCHEDULED_TIME_HORIZON_DAYS = 365
"""「予定済みの時間」に数える先の長さ（今日から何日先まで）。終わりの無い繰り返しを数え切るため。"""


class TaskUseCases:
    def __init__(
        self,
        session: Session,
        clock: UserClock | None = None,
        *,
        scheduled_time: ScheduledTimeLookup | None = None,
    ) -> None:
        self._repo: TaskRepository = SqlAlchemyTaskRepository(session)
        self._milestones: MilestoneRepository = SqlAlchemyMilestoneRepository(session)
        self._membership = ProjectMembership(
            projects=SqlAlchemyProjectRepository(session),
            tasks=self._repo,
            milestones=self._milestones,
        )
        self._session = session
        self._clock = clock or UserClock(session)
        # 予定の口が無ければ「予定済みの時間」は出さない（null）。
        self._scheduled_time = scheduled_time

    def list_tasks(self, user_id: int, filters: dict) -> list[dict]:
        """``filters`` の ``project_id`` は**子孫のプロジェクトも含めて**絞る（ADR-0024）。"""
        filters = self.resolve_project_filter(user_id, filters)
        tasks = self._repo.find_all(user_id, filters)
        board = self.progress_board(user_id)
        scheduled = self.scheduled_minutes(user_id)
        tree = self._membership.tree(user_id)
        return [self._enrich(t, board, scheduled, tree) for t in tasks]

    def resolve_project_filter(self, user_id: int, filters: dict) -> dict:
        """``project_id`` を、そのプロジェクトと子孫の id の一覧（``project_ids``）に置き換える。"""
        if filters.get("project_id") is None:
            return filters
        resolved = {k: v for k, v in filters.items() if k != "project_id"}
        resolved["project_ids"] = self._membership.scope_ids(user_id, filters["project_id"])
        return resolved

    def scheduled_minutes(self, user_id: int) -> dict[int, int] | None:
        """タスクごとの「予定済みの時間」（分）。予定の口が無ければ None。

        今日（利用者の日付）以降に始まる、そのタスクに結ばれた回の長さの合計（ADR-0014）。
        今日の回は、もう過ぎたものも数える。先は ``SCHEDULED_TIME_HORIZON_DAYS`` 日まで。
        """
        if self._scheduled_time is None:
            return None
        today = self._clock.today(user_id)
        try:
            horizon = today + timedelta(days=SCHEDULED_TIME_HORIZON_DAYS)
        except OverflowError:
            horizon = date.max
        return self._scheduled_time.scheduled_minutes_by_task(
            user_id, today, horizon, self._clock.zone_name(user_id)
        )

    def progress_board(self, user_id: int) -> TaskProgressBoard:
        # 親の進捗は子孫の積み上げなので、絞り込みに関わらず利用者のタスク全部から作る
        return TaskProgressBoard(
            self._repo.find_all(user_id, {}),
            self._repo.get_actual_hours_by_task(user_id),
        )

    def get_task(self, task_id: int, user_id: int) -> dict:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return self._enrich(task)

    def create_task(self, dto: CreateTaskDTO) -> dict:
        project_id = dto.project_id
        if dto.parent_task_id is not None:
            parent = self._owned_task(dto.parent_task_id, dto.user_id)
            # 子タスクは親のプロジェクトに入る（ADR-0024）。空で送られたら親に揃える
            if project_id is not None and project_id != parent.project_id:
                raise ValidationError("a subtask belongs to the project of its parent task")
            project_id = parent.project_id
        elif project_id is not None:
            self._membership.owned_project(dto.user_id, project_id)
        if dto.milestone_id is not None:
            self._check_milestone(dto.user_id, dto.milestone_id, project_id)
        task = Task(
            id=None,
            user_id=dto.user_id,
            title=dto.title,
            category_id=dto.category_id,
            priority=dto.priority,
            urgency=dto.urgency,
            status=dto.status,
            start_date=dto.start_date,
            due_date=dto.due_date,
            estimated_hours=dto.estimated_hours,
            remaining_hours=dto.remaining_hours,
            memo=dto.memo,
            parent_task_id=dto.parent_task_id,
            milestone_id=dto.milestone_id,
            project_id=project_id,
        )
        saved = self._repo.save(task)
        self._session.commit()
        return self._enrich(saved)

    def update_task(self, task_id: int, user_id: int, dto: UpdateTaskDTO) -> dict:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        if dto.title is not None:
            task.title = dto.title
        if dto.category_id is not None:
            task.category_id = dto.category_id
        if dto.priority is not None:
            task.priority = dto.priority
        if dto.urgency is not None:
            task.urgency = dto.urgency
        if dto.status is not None:
            task.change_status(dto.status)
        if dto.start_date is not None:
            task.start_date = dto.start_date
        if dto.due_date is not None:
            task.due_date = dto.due_date
        if dto.estimated_hours is not None:
            task.estimated_hours = dto.estimated_hours
        if dto.remaining_hours_given:
            task.remaining_hours = dto.remaining_hours
        if dto.memo is not None:
            task.memo = dto.memo
        if dto.parent_task_id is not None and dto.parent_task_id != task.parent_task_id:
            self._owned_task(dto.parent_task_id, user_id)
            if dto.parent_task_id in self._repo.subtree_ids(user_id, task_id):
                # 自分か自分の子孫を親にすると、その枝がどこからも辿れなくなる
                raise ConflictError("a task cannot be placed under itself or its own subtask")
            task.parent_task_id = dto.parent_task_id

        previous_project = task.project_id
        task.project_id = self._project_for_update(task, user_id, dto)
        previous_milestone = task.milestone_id
        if dto.milestone_id_given or dto.milestone_id is not None:
            task.milestone_id = dto.milestone_id
        # 自分で選び直したマイルストーンが届かないなら断る。前から付いていたものは下で外す
        if task.milestone_id is not None and task.milestone_id != previous_milestone:
            self._check_milestone(user_id, task.milestone_id, task.project_id)

        saved = self._repo.save(task)
        if task.project_id != previous_project:
            # 親を移すと子孫も移る（子だけ別のプロジェクトにはしない。ADR-0024）
            self._repo.set_project(self._repo.subtree_ids(user_id, task_id), task.project_id)
            self._membership.detach_unreachable_milestones(user_id)
            self._session.expire_all()
        self._session.commit()
        refreshed = self._repo.find_by_id_for_user(task_id, user_id)
        return self._enrich(refreshed if refreshed is not None else saved)

    def _project_for_update(self, task: Task, user_id: int, dto: UpdateTaskDTO) -> int | None:
        """更新の後に属するプロジェクト。親があれば親のもの（違う値を送られたら 422）。"""
        if task.parent_task_id is not None:
            parent = self._owned_task(task.parent_task_id, user_id)
            if dto.project_id_given and dto.project_id != parent.project_id:
                raise ValidationError("a subtask belongs to the project of its parent task")
            return parent.project_id
        if not dto.project_id_given:
            return task.project_id
        if dto.project_id is not None:
            self._membership.owned_project(user_id, dto.project_id)
        return dto.project_id

    def _owned_task(self, task_id: int, user_id: int) -> Task:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    def _check_milestone(self, user_id: int, milestone_id: int, project_id: int | None) -> None:
        """自分のマイルストーンで、そのプロジェクト（か祖先・未分類）のものか（ADR-0024）。"""
        milestone = owned_by(
            self._milestones.find_by_id(milestone_id), user_id,
            resource="Milestone", resource_id=milestone_id,
        )
        tree = self._membership.tree(user_id)
        if not tree.milestone_reachable(milestone.project_id, project_id):
            raise ValidationError(
                "the milestone belongs to a project this task is not in (or under)"
            )

    def delete_task(self, task_id: int, user_id: int) -> None:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        self._repo.soft_delete(task_id, user_id)
        self._session.commit()

    def _enrich(
        self,
        task: Task,
        board: TaskProgressBoard | None = None,
        scheduled: dict[int, int] | None = None,
        tree: ProjectTree | None = None,
    ) -> dict:
        if board is None:
            board = self.progress_board(task.user_id)
        if scheduled is None:
            scheduled = self.scheduled_minutes(task.user_id)
        if tree is None:
            tree = self._membership.tree(task.user_id)
        actual = board.actual_hours(task.id)
        remaining = task.remaining_hours_from(actual)
        scheduled_hours = (
            round(scheduled.get(task.id or 0, 0) / 60, 2) if scheduled is not None else None
        )
        # 進捗率の式に入れる実績と残（子を持つなら子孫の積み上げ。ADR-0010）
        figures = board.figures(task)
        # 期限の近さは利用者の日付で決まる。サーバ（UTC）の today を使うと
        # JST の利用者にとって 0:00〜9:00 のあいだ「今日」が前日にずれる。
        today = self._clock.today(task.user_id)
        priority_score = task.priority_score(today)
        return {
            "id": task.id,
            "user_id": task.user_id,
            "title": task.title,
            "category_id": task.category_id,
            "priority": task.priority,
            "urgency": task.urgency,
            "status": task.status.value,
            "start_date": task.start_date,
            "due_date": task.due_date,
            "estimated_hours": float(task.estimated_hours) if task.estimated_hours is not None else None,
            "remaining_hours": remaining,
            "remaining_hours_entered": (
                float(task.remaining_hours) if task.remaining_hours is not None else None
            ),
            "actual_hours": actual,
            "has_subtasks": board.has_subtasks(task.id),
            "rollup_actual_hours": figures.actual_hours,
            "rollup_remaining_hours": figures.remaining_hours,
            "progress_percent": figures.progress_percent(done=task.status == TaskStatus.DONE),
            "scheduled_hours": scheduled_hours,
            # 残のうち、まだ予定に取っていない分（残 − 予定済み、0 未満は 0）
            "unscheduled_hours": (
                round(max(remaining - scheduled_hours, 0.0), 2)
                if remaining is not None and scheduled_hours is not None
                else None
            ),
            "priority_score": priority_score,
            "memo": task.memo,
            "parent_task_id": task.parent_task_id,
            "milestone_id": task.milestone_id,
            "project_id": task.project_id,
            # 表示用の道筋（「親 / 子」）。未分類は null
            "project_path": tree.path(task.project_id),
            "completed_at": task.completed_at,
            "deleted_at": task.deleted_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
