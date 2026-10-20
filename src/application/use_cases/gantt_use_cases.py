from __future__ import annotations

from src.domain.exceptions import NotFoundError
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.services.completion_forecast import CompletionForecast
from src.domain.services.project_tree import ProjectTree
from src.domain.services.task_progress_board import TaskProgressBoard


class GanttUseCases:
    def __init__(
        self,
        *,
        tasks: TaskRepository,
        dependencies: TaskDependencyRepository,
        projects: ProjectRepository,
    ) -> None:
        self._tasks = tasks
        self._dependencies = dependencies
        self._projects = projects

    def get_gantt_data(
        self, user_id: int, project_id: int | None = None, forecast: CompletionForecast | None = None,
    ) -> list[dict]:
        """``project_id`` を指すと、そのプロジェクトと子孫のタスクだけ（ADR-0024）。アーカイブしたタスクは出さない（ADR-0046）。"""
        all_tasks = [t for t in self._tasks.find_all(user_id, {}) if not t.is_archived]
        tasks = all_tasks
        if project_id is not None:
            scope = set(self._projects.subtree_ids(user_id, project_id))
            if not scope:
                raise NotFoundError("Project", project_id)
            tasks = [t for t in all_tasks if t.project_id in scope]
        tree = ProjectTree(self._projects.find_all(user_id))
        # 自分の依存だけを引く（task_dependencies に持ち主の列は無く、リポジトリがタスクを辿って絞る）。
        deps = self._dependencies.find_all_for_user(user_id)
        task_ids = {t.id for t in tasks}
        # 進捗率は一覧・ダッシュボードと同じ式（親は子孫の積み上げ。ADR-0010）
        board = TaskProgressBoard(all_tasks, self._tasks.get_actual_hours_by_task(user_id))
        result = []
        for task in tasks:
            task_deps = [
                {
                    "predecessor_task_id": d.predecessor_task_id,
                    "dependency_type": d.dependency_type.value,
                    "lag_days": d.lag_days,
                }
                for d in deps
                # 削除済みのタスクへの依存は出さない（find_all は削除済みを含まない）。
                if d.successor_task_id == task.id and d.predecessor_task_id in task_ids
            ]
            result.append(
                {
                    "id": task.id,
                    "title": task.title,
                    "start_date": str(task.start_date) if task.start_date else None,
                    "due_date": str(task.due_date) if task.due_date else None,
                    "status": task.status.value,
                    "parent_task_id": task.parent_task_id,
                    "project_id": task.project_id,
                    "project_path": tree.path(task.project_id),
                    "progress_percent": board.progress_percent(task),
                    "dependencies": task_deps,
                    **_forecast_fields(forecast, task.id),
                }
            )
        return result


def _forecast_fields(forecast: CompletionForecast | None, task_id: int | None) -> dict:
    """終わる見込み（ADR-0058）。見込みを渡されなければ載せない。"""
    if forecast is None or task_id is None:
        return {}
    f = forecast.task(task_id)
    return {
        "forecast_start": str(f.start) if f.start else None,
        "forecast_finish": str(f.finish) if f.finish else None,
        "forecast_gap": f.gap.value if f.gap is not None else None,
        "forecast_overdue_days": f.overdue_days,
    }
