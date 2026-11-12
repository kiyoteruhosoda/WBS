from __future__ import annotations

from sqlalchemy.orm import Session

from src.application.dto.task_dto import CreateTaskDTO, UpdateTaskDTO
from src.application.use_cases.completion_forecast_use_cases import CompletionForecastUseCases
from src.application.use_cases.ownership import owned_by
from src.application.use_cases.project_membership import ProjectMembership
from src.application.user_clock import UserClock
from src.domain.entities.project import Project
from src.domain.entities.task import Task
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


def _forecast_fields(forecast: CompletionForecast, task: Task) -> dict:
    """Forecast completion (ADR-0058). When no forecast is given, ``forecast_gap`` holds the reason."""
    f = forecast.task(task.id or 0)
    return {
        "forecast_start": f.start,
        "forecast_finish": f.finish,
        "forecast_gap": f.gap.value if f.gap is not None else None,
        "forecast_overdue_days": f.overdue_days,
    }


class TaskUseCases:
    def __init__(
        self,
        session: Session,
        clock: UserClock | None = None,
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
        # Only used to look up assignee names (candidate filtering is not used)
        self._people = SqlAlchemyPersonDirectory(session, require_identity=False)
        self._clock = clock or UserClock(session)
        self._forecasts = CompletionForecastUseCases(session, self._clock)

    def list_tasks(self, user_id: int, filters: dict) -> list[dict]:
        """``project_id`` in ``filters`` filters **including descendant projects** (ADR-0024).

        Archived tasks (ADR-0046) are not returned.
        """
        filters = self.resolve_project_filter(user_id, filters)
        tasks = [t for t in self._repo.find_all(user_id, filters) if not t.is_archived]
        board = self.progress_board(user_id)
        tree = self._membership.tree(user_id)
        names = self._assignee_names(tasks)
        forecast = self._forecasts.forecast(user_id)
        return [self._enrich(t, board, tree, names, forecast) for t in tasks]

    def assigned_open_tasks(self, user_id: int) -> list[tuple[Task, str | None]]:
        """Tasks assigned to the caller, visible to them and still workable, with their paths (ADR-0056; passed to Tracker's picker).

        ⚠ Assignments of people removed from members remain (ADR-0055 decision 4), but they are not visible so they do not appear here.
        """
        tree = self._membership.tree(user_id)
        tasks = self._repo.find_all(user_id, {"assignee_user_id": user_id})
        return [(t, tree.path(t.project_id)) for t in tasks if t.is_open]

    def open_projects(self, user_id: int) -> list[tuple[Project, str]]:
        """Projects visible to the caller and not archived, with their paths (ADR-0056 decision 4; passed to Tracker's and Scheduler's pickers).

        In tree order (children right after their parent, siblings by position). Everything under an archived branch is omitted.
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
        """Replace ``project_id`` with the list of ids of that project and its descendants (``project_ids``)."""
        if filters.get("project_id") is None:
            return filters
        resolved = {k: v for k, v in filters.items() if k != "project_id"}
        resolved["project_ids"] = self._membership.scope_ids(user_id, filters["project_id"])
        return resolved

    def progress_board(self, user_id: int) -> TaskProgressBoard:
        # A parent's progress is rolled up from its descendants, so build from all the user's tasks regardless of filters
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
            # A child task goes into its parent's project (ADR-0024). If sent empty, align it with the parent
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
            # Check only when re-selected. A team task may still carry the category of whoever set it
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
                # Making itself or its own descendant the parent would make that branch unreachable
                raise ConflictError("a task cannot be placed under itself or its own subtask")
            task.parent_task_id = dto.parent_task_id

        previous_project = task.project_id
        task.project_id = self._project_for_update(task, user_id, dto)
        if task.project_id != previous_project:
            # Only admins of both the source and target trees may take it to another tree (ADR-0066). Same when moving by changing the parent
            self._membership.require_manager_to_cross(user_id, previous_project, task.project_id)
        previous_milestone = task.milestone_id
        if dto.milestone_id_given or dto.milestone_id is not None:
            task.milestone_id = dto.milestone_id
        # Reject a milestone the caller re-selected if it cannot be reached. Previously attached ones are detached below
        if task.milestone_id is not None and task.milestone_id != previous_milestone:
            self._check_milestone(user_id, task.milestone_id, task.project_id)
        # Check the assignee only when re-selected. An existing assignee is kept even if removed from members (ADR-0055 decision 4)
        if dto.assignee_user_id_given and dto.assignee_user_id != task.assignee_user_id:
            task.assignee_user_id = dto.assignee_user_id
            self._check_assignee(user_id, task)

        saved = self._repo.save(task)
        if task.project_id != previous_project:
            # Moving a parent moves its descendants too (a child alone never goes to a different project, ADR-0024)
            self._repo.set_project(self._repo.subtree_ids(user_id, task_id), task.project_id)
            self._membership.detach_unreachable_milestones(user_id)
            self._session.expire_all()
        self._session.commit()
        refreshed = self._repo.find_by_id_for_user(task_id, user_id)
        return self._enrich(
            refreshed if refreshed is not None else saved, forecast=self._forecasts.forecast(user_id)
        )

    def move_to_project(self, user_id: int, task_ids: list[int], project_id: int | None) -> dict:
        """Move the selected tasks to another project at once (to unclassified with ``None``). ADR-0030.

        Child tasks follow their parent (ADR-0024 point 4), so only branch roots are written and descendants move along with them.
        If it includes a child task whose ancestor is not selected along with it, 422 without changing anything (a child alone never goes to a different project).
        Ids that are not the caller's tasks and other people's projects are 404. Milestones that can no longer be reached are detached.
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
            # Only admins of both the source and target trees may take them to another tree (ADR-0066). If any one is refused, nothing changes
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
        """The project it belongs to after the update. If it has a parent, the parent's (422 if a different value is sent)."""
        # ⚠ A child whose parent was deleted (soft delete) is treated as a root (don't make it uneditable just because the parent is missing)
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
        """Categories belong to their creator (task #762). Someone else's category is rejected as if it did not exist."""
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
        """Only members of the root project (the creator, if unclassified) can be assignees (ADR-0055 decision 4)."""
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
        """Whether the milestone is visible and belongs to that project (or an ancestor, or is unclassified) (ADR-0024, ADR-0055)."""
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
        tree: ProjectTree | None = None,
        names: dict[int, str] | None = None,
        forecast: CompletionForecast | None = None,
    ) -> dict:
        if forecast is None:
            # Even for a single task, the forecast is computed by stacking all tasks in the same capacity (ADR-0058)
            forecast = self._forecasts.forecast(task.user_id)
        if names is None:
            names = self._assignee_names([task])
        if board is None:
            board = self.progress_board(task.user_id)
        if tree is None:
            tree = self._membership.tree(task.user_id)
        actual = board.actual_hours(task.id)
        remaining = task.remaining_hours_from(actual)
        # Actual and remaining fed into the progress formula (rolled up from descendants if it has children, ADR-0010)
        figures = board.figures(task)
        # How close the due date is depends on the user's date. Using the server's (UTC) today
        # shifts "today" to the previous day between 0:00 and 9:00 for a JST user.
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
            # Display path ("parent / child"). null if unclassified
            "project_path": tree.path(task.project_id),
            "completed_at": task.completed_at,
            "archived_at": task.archived_at,
            "deleted_at": task.deleted_at,
            "created_at": task.created_at,
            "updated_at": task.updated_at,
        }
