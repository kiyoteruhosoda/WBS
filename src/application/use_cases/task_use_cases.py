from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy.orm import Session

from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.application.ports.scheduled_time_lookup import ScheduledTimeLookup
from src.application.use_cases.completion_forecast_use_cases import CompletionForecastUseCases
from src.application.use_cases.project_membership import ProjectMembership
from src.application.user_clock import UserClock
from src.domain.entities.project import Project
from src.domain.entities.task import Task
from src.application.use_cases.ownership import owned_by
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.repositories.milestone_repository import MilestoneRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.completion_forecast import CompletionForecast
from src.domain.services.project_tree import ProjectTree
from src.domain.services.task_branch_selection import TaskBranchSelection
from src.domain.services.task_progress_board import TaskProgressBoard
from src.domain.value_objects.task_status import TaskStatus
from src.infrastructure.repositories.category_repository import SqlAlchemyCategoryRepository
from src.infrastructure.repositories.milestone_repository import SqlAlchemyMilestoneRepository
from src.infrastructure.repositories.person_directory import SqlAlchemyPersonDirectory
from src.infrastructure.repositories.project_member_repository import (
    SqlAlchemyProjectMemberRepository,
)
from src.infrastructure.repositories.project_repository import SqlAlchemyProjectRepository
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository

SCHEDULED_TIME_HORIZON_DAYS = 365
"""「予定済みの時間」に数える先の長さ（今日から何日先まで）。終わりのある予定はここまで数える。

終わりの無い繰り返しは、ここまで数えると 1 年分が積まれて残を大きく超える（15 分 × 毎平日で 65h）。
そちらは画面の期間の終わり（無ければ今月末）までにする（ADR-0051）。
"""


def _forecast_fields(forecast: CompletionForecast, task: Task) -> dict:
    """終わる見込み（ADR-0058）。見込みを出さないときは ``forecast_gap`` に理由。"""
    f = forecast.task(task.id or 0)
    return {
        "forecast_start": f.start,
        "forecast_finish": f.finish,
        "forecast_gap": f.gap.value if f.gap is not None else None,
        "forecast_overdue_days": f.overdue_days,
    }


def _end_of_month(day: date) -> date:
    first_of_next = (day.replace(day=28) + timedelta(days=4)).replace(day=1)
    return first_of_next - timedelta(days=1)


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
        self._categories = SqlAlchemyCategoryRepository(session)
        self._membership = ProjectMembership(
            projects=SqlAlchemyProjectRepository(session),
            tasks=self._repo,
            milestones=self._milestones,
            members=SqlAlchemyProjectMemberRepository(session),
        )
        self._session = session
        # 担当者の名前を引くだけ（候補の絞りは使わない）
        self._people = SqlAlchemyPersonDirectory(session, require_identity=False)
        self._clock = clock or UserClock(session)
        self._forecasts = CompletionForecastUseCases(session, self._clock)
        # 予定の口が無ければ「予定済みの時間」は出さない（null）。
        self._scheduled_time = scheduled_time

    def list_tasks(
        self, user_id: int, filters: dict, *, scheduled_until: date | None = None
    ) -> list[dict]:
        """``filters`` の ``project_id`` は**子孫のプロジェクトも含めて**絞る（ADR-0024）。

        アーカイブしたタスク（ADR-0046）は出さない。``scheduled_until`` は画面で選んでいる期間の
        終わりで、終わりの無い繰り返しをそこまで数える（無ければ今月末。ADR-0051）。
        """
        filters = self.resolve_project_filter(user_id, filters)
        tasks = [t for t in self._repo.find_all(user_id, filters) if not t.is_archived]
        board = self.progress_board(user_id)
        scheduled = self.scheduled_minutes(user_id, scheduled_until)
        tree = self._membership.tree(user_id)
        names = self._assignee_names(tasks)
        forecast = self._forecasts.forecast(user_id)
        return [self._enrich(t, board, scheduled, tree, names, forecast) for t in tasks]

    def assigned_open_tasks(self, user_id: int) -> list[tuple[Task, str | None]]:
        """担当が自分で、自分に見えて、まだ作業できるタスクと、その道筋（ADR-0056。Tracker の選ぶ欄へ渡す）。

        ⚠ メンバーから外れた人の担当は残っている（ADR-0055 決定 4）が、見えないのでここには出ない。
        """
        tree = self._membership.tree(user_id)
        tasks = self._repo.find_all(user_id, {"assignee_user_id": user_id})
        return [(t, tree.path(t.project_id)) for t in tasks if t.is_open]

    def open_projects(self, user_id: int) -> list[tuple[Project, str]]:
        """自分に見えて保管していないプロジェクトと、その道筋（ADR-0056 決定 4。Tracker・Scheduler の選ぶ欄へ渡す）。

        木の順（親の直後に子、兄弟は並び順）。保管した枝の下は丸ごと出さない。
        """
        tree = self._membership.tree(user_id)
        found: list[tuple[Project, str]] = []

        def walk(parent_id: int | None) -> None:
            for project in tree.children_of(parent_id):
                if project.id is None or project.is_archived:
                    continue
                path = tree.path(project.id)
                if path is not None:
                    found.append((project, path))
                walk(project.id)

        walk(None)
        return found

    def resolve_project_filter(self, user_id: int, filters: dict) -> dict:
        """``project_id`` を、そのプロジェクトと子孫の id の一覧（``project_ids``）に置き換える。"""
        if filters.get("project_id") is None:
            return filters
        resolved = {k: v for k, v in filters.items() if k != "project_id"}
        resolved["project_ids"] = self._membership.scope_ids(user_id, filters["project_id"])
        return resolved

    def scheduled_minutes(
        self, user_id: int, until: date | None = None
    ) -> dict[int, int] | None:
        """タスクごとの「予定済みの時間」（分）。予定の口が無ければ None。

        今日（利用者の日付）以降に始まる、そのタスクに結ばれた回の長さの合計（ADR-0014）。
        今日の回は、もう過ぎたものも数える。先は ``SCHEDULED_TIME_HORIZON_DAYS`` 日まで。
        終わりの無い繰り返しだけは ``until``（無ければ今月末）までにする（ADR-0051）。
        """
        if self._scheduled_time is None:
            return None
        today = self._clock.today(user_id)
        try:
            horizon = today + timedelta(days=SCHEDULED_TIME_HORIZON_DAYS)
        except OverflowError:
            horizon = date.max
        return self._scheduled_time.scheduled_minutes_by_task(
            user_id,
            today,
            horizon,
            self._clock.zone_name(user_id),
            endless_until=until if until is not None else _end_of_month(today),
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
        return self._enrich(task, forecast=self._forecasts.forecast(user_id))

    def create_task(self, dto: CreateTaskDTO) -> dict:
        project_id = dto.project_id
        if dto.parent_task_id is not None:
            parent = self._owned_task(dto.parent_task_id, dto.user_id)
            # 子タスクは親のプロジェクトに入る（ADR-0024）。空で送られたら親に揃える
            if project_id is not None and project_id != parent.project_id:
                raise ValidationError("a subtask belongs to the project of its parent task")
            project_id = parent.project_id
        elif project_id is not None:
            self._membership.visible_project(dto.user_id, project_id)
        if dto.milestone_id is not None:
            self._check_milestone(dto.user_id, dto.milestone_id, project_id)
        if dto.category_id is not None:
            self.check_category(dto.user_id, dto.category_id)
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
            assignee_user_id=(
                dto.assignee_user_id if dto.assignee_user_id_given else dto.user_id
            ),
            allocation_percent=dto.allocation_percent,
        )
        self._check_assignee(dto.user_id, task)
        saved = self._repo.save(task)
        self._session.commit()
        return self._enrich(saved, forecast=self._forecasts.forecast(dto.user_id))

    def update_task(self, task_id: int, user_id: int, dto: UpdateTaskDTO) -> dict:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        if dto.title is not None:
            task.title = dto.title
        if dto.category_id is not None:
            # 選び直したときだけ確かめる。チームのタスクには付けた人の分類が付いたままのことがある
            if dto.category_id != task.category_id:
                self.check_category(user_id, dto.category_id)
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
        if dto.allocation_percent_given:
            task.allocation_percent = dto.allocation_percent
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
        if task.project_id != previous_project:
            # 別の木へ持ち出すのは、元と先の両方の管理者だけ（ADR-0066）。親を替えて移すときも同じ
            self._membership.require_manager_to_cross(user_id, previous_project, task.project_id)
        previous_milestone = task.milestone_id
        if dto.milestone_id_given or dto.milestone_id is not None:
            task.milestone_id = dto.milestone_id
        # 自分で選び直したマイルストーンが届かないなら断る。前から付いていたものは下で外す
        if task.milestone_id is not None and task.milestone_id != previous_milestone:
            self._check_milestone(user_id, task.milestone_id, task.project_id)
        # 担当者は選び直したときだけ確かめる。前からの担当は、外れた人でも消さずに残す（ADR-0055 決定 4）
        if dto.assignee_user_id_given and dto.assignee_user_id != task.assignee_user_id:
            task.assignee_user_id = dto.assignee_user_id
            self._check_assignee(user_id, task)

        saved = self._repo.save(task)
        if task.project_id != previous_project:
            # 親を移すと子孫も移る（子だけ別のプロジェクトにはしない。ADR-0024）
            self._repo.set_project(self._repo.subtree_ids(user_id, task_id), task.project_id)
            self._membership.detach_unreachable_milestones(user_id)
            self._session.expire_all()
        self._session.commit()
        refreshed = self._repo.find_by_id_for_user(task_id, user_id)
        return self._enrich(
            refreshed if refreshed is not None else saved, forecast=self._forecasts.forecast(user_id)
        )

    def move_to_project(self, user_id: int, task_ids: list[int], project_id: int | None) -> dict:
        """選んだタスクをまとめて別のプロジェクトへ（``None`` で未分類へ）。ADR-0030。

        子タスクは親に従う（ADR-0024 の 4）ので、書くのは枝の根だけで、子孫は根と一緒に移る。
        祖先が一緒に選ばれていない子タスクを含めば、何も変えずに 422（子だけ別のプロジェクトにはしない）。
        自分のタスクでない id・他人のプロジェクトは 404。届かなくなったマイルストーンは外す。
        """
        if project_id is not None:
            self._membership.visible_project(user_id, project_id)
        live = {t.id: t for t in self._repo.find_all(user_id, {}) if t.id is not None}
        for task_id in task_ids:
            if task_id not in live:
                raise NotFoundError("Task", task_id)
        selection = TaskBranchSelection.of(
            task_ids, {tid: t.parent_task_id for tid, t in live.items()}
        )
        if selection.stranded:
            raise ValidationError(
                "a subtask follows its parent task; move the parent instead "
                f"(task ids: {', '.join(str(i) for i in selection.stranded)})"
            )
        for root in selection.roots:
            # 別の木へ持ち出すのは、元と先の両方の管理者だけ（ADR-0066）。1 つでも断れば何も変えない
            if live[root].project_id != project_id:
                self._membership.require_manager_to_cross(user_id, live[root].project_id, project_id)
        moved: list[int] = []
        for root in selection.roots:
            if live[root].project_id == project_id:
                continue
            branch = self._repo.subtree_ids(user_id, root)
            self._repo.set_project(branch, project_id)
            moved.extend(i for i in branch if i in live)
        detached = self._membership.detach_unreachable_milestones(user_id) if moved else []
        self._session.commit()
        self._session.expire_all()
        return {
            "moved_task_ids": sorted(set(moved)),
            "detached_milestone_task_ids": sorted(set(detached)),
        }

    def _project_for_update(self, task: Task, user_id: int, dto: UpdateTaskDTO) -> int | None:
        """更新の後に属するプロジェクト。親があれば親のもの（違う値を送られたら 422）。"""
        # ⚠ 親を消した（論理削除）子は、根として扱う（親が見つからないだけで直せなくしない）
        parent = (
            self._repo.find_by_id_for_user(task.parent_task_id, user_id)
            if task.parent_task_id is not None
            else None
        )
        if parent is not None:
            if dto.project_id_given and dto.project_id != parent.project_id:
                raise ValidationError("a subtask belongs to the project of its parent task")
            return parent.project_id
        if not dto.project_id_given:
            return task.project_id
        if dto.project_id is not None:
            self._membership.visible_project(user_id, dto.project_id)
        return dto.project_id

    def check_category(self, user_id: int, category_id: int) -> None:
        """分類は作った本人のもの（task #762）。ほかの人の分類は無いものとして断る。"""
        owned_by(
            self._categories.find_by_id(category_id), user_id,
            resource="Category", resource_id=category_id,
        )

    def _owned_task(self, task_id: int, user_id: int) -> Task:
        task = self._repo.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        return task

    def _assignee_names(self, tasks: list[Task]) -> dict[int, str]:
        ids = {t.assignee_user_id for t in tasks if t.assignee_user_id is not None}
        return {pid: p.display_name for pid, p in self._people.by_ids(ids).items()}

    def _check_assignee(self, user_id: int, task: Task) -> None:
        """担当者に付けられるのは、根のプロジェクトのメンバー（未分類なら作った人）だけ（ADR-0055 決定 4）。"""
        if task.assignee_user_id is None:
            return
        if task.project_id is None:
            allowed = {task.user_id}
        else:
            root = self._membership.tree(user_id).root_of(task.project_id)
            allowed = self._membership.member_ids(root)
        if task.assignee_user_id not in allowed:
            raise ValidationError("the assignee must be a member of the top project of this task")

    def _check_milestone(self, user_id: int, milestone_id: int, project_id: int | None) -> None:
        """見えるマイルストーンで、そのプロジェクト（か祖先・未分類）のものか（ADR-0024・ADR-0055）。"""
        milestone = self._milestones.find_by_id_for_user(milestone_id, user_id)
        if milestone is None:
            raise NotFoundError("Milestone", milestone_id)
        tree = self._membership.tree(user_id)
        if not tree.milestone_reachable(milestone.project_id, project_id):
            raise ValidationError(
                "the milestone belongs to a project this task is not in (or under)"
            )

    def _enrich(
        self,
        task: Task,
        board: TaskProgressBoard | None = None,
        scheduled: dict[int, int] | None = None,
        tree: ProjectTree | None = None,
        names: dict[int, str] | None = None,
        forecast: CompletionForecast | None = None,
    ) -> dict:
        if forecast is None:
            # 1 件でも、見込みは同じ枠のタスク全部を積んで出す（ADR-0058）
            forecast = self._forecasts.forecast(task.user_id)
        if names is None:
            names = self._assignee_names([task])
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
            "assignee_user_id": task.assignee_user_id,
            "allocation_percent": task.allocation_percent,
            **_forecast_fields(forecast, task),
            "assignee_name": (
                names.get(task.assignee_user_id) if task.assignee_user_id is not None else None
            ),
            # 表示用の道筋（「親 / 子」）。未分類は null
            "project_path": tree.path(task.project_id),
            "completed_at": task.completed_at,
            "archived_at": task.archived_at,
            "deleted_at": task.deleted_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
