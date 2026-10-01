from __future__ import annotations

from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.repositories.task_repository import TaskRepository


class GanttUseCases:
    def __init__(self, *, tasks: TaskRepository, dependencies: TaskDependencyRepository) -> None:
        self._tasks = tasks
        self._dependencies = dependencies

    def get_gantt_data(self, user_id: int) -> list[dict]:
        tasks = self._tasks.find_all(user_id, {})
        # 自分の依存だけを引く（task_dependencies に持ち主の列は無く、リポジトリがタスクを辿って絞る）。
        deps = self._dependencies.find_all_for_user(user_id)
        task_ids = {t.id for t in tasks}
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
                    "progress_percent": task.progress_percent(
                        self._tasks.get_actual_hours(task.id)
                    ),
                    "dependencies": task_deps,
                }
            )
        return result
