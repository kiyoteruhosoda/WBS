from __future__ import annotations
from sqlalchemy.orm import Session
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository
from src.infrastructure.repositories.task_dependency_repository import SqlAlchemyTaskDependencyRepository
from src.application.use_cases.task_use_cases import TaskUseCases


class GanttUseCases:
    def __init__(self, session: Session) -> None:
        self._session = session
        self._task_repo = SqlAlchemyTaskRepository(session)
        self._dep_repo = SqlAlchemyTaskDependencyRepository(session)
        self._task_uc = TaskUseCases(session)

    def get_gantt_data(self, user_id: int) -> list[dict]:
        tasks = self._task_repo.find_all(user_id, {})
        all_deps = self._dep_repo.get_all_dependencies()
        task_ids = {t.id for t in tasks}
        result = []
        for task in tasks:
            enriched = self._task_uc._enrich(task)
            deps = [
                {
                    "predecessor_task_id": d.predecessor_task_id,
                    "dependency_type": d.dependency_type.value,
                    "lag_days": d.lag_days,
                }
                for d in all_deps
                if d.successor_task_id == task.id and d.predecessor_task_id in task_ids
            ]
            result.append({
                "id": task.id,
                "title": task.title,
                "start_date": str(task.start_date) if task.start_date else None,
                "due_date": str(task.due_date) if task.due_date else None,
                "status": task.status.value,
                "parent_task_id": task.parent_task_id,
                "progress_percent": enriched["progress_percent"],
                "dependencies": deps,
            })
        return result
