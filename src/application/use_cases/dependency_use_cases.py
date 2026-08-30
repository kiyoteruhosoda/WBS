from __future__ import annotations

from sqlalchemy.orm import Session

from src.domain.entities.task_dependency import TaskDependency
from src.domain.exceptions import CyclicDependencyError, NotFoundError
from src.domain.value_objects.dependency_type import DependencyType
from src.infrastructure.repositories.task_dependency_repository import (
    SqlAlchemyTaskDependencyRepository,
)
from src.infrastructure.repositories.task_repository import SqlAlchemyTaskRepository


def _has_cycle(all_deps: list[TaskDependency], new_pred: int, new_succ: int) -> bool:
    graph: dict[int, list[int]] = {}
    for dep in all_deps:
        graph.setdefault(dep.successor_task_id, []).append(dep.predecessor_task_id)
    visited = set()
    stack = [new_succ]
    while stack:
        node = stack.pop()
        if node == new_pred:
            return True
        if node in visited:
            continue
        visited.add(node)
        for pred in graph.get(node, []):
            stack.append(pred)
    return False


class DependencyUseCases:
    def __init__(self, session: Session) -> None:
        self._repo = SqlAlchemyTaskDependencyRepository(session)
        self._task_repo = SqlAlchemyTaskRepository(session)
        self._session = session

    def get_dependencies(self, task_id: int, user_id: int) -> dict:
        self._owned_task(task_id, user_id)
        all_for_task = self._repo.find_by_task(task_id)
        predecessors = [d for d in all_for_task if d.successor_task_id == task_id]
        successors = [d for d in all_for_task if d.predecessor_task_id == task_id]
        return {
            "task_id": task_id,
            "predecessors": [self._dep_to_dict(d) for d in predecessors],
            "successors": [self._dep_to_dict(d) for d in successors],
        }

    def add_dependency(self, successor_task_id: int, predecessor_task_id: int, user_id: int, dependency_type: str = "FS", lag_days: int = 0) -> TaskDependency:
        # 両端とも自分のタスクであること。片方でも他人のものだと、
        # 存在しないはずのタスクの ID を依存として書き込めてしまう。
        self._owned_task(successor_task_id, user_id)
        self._owned_task(predecessor_task_id, user_id)
        all_deps = self._repo.get_all_dependencies()
        if _has_cycle(all_deps, predecessor_task_id, successor_task_id):
            raise CyclicDependencyError()
        dep = TaskDependency(
            predecessor_task_id=predecessor_task_id,
            successor_task_id=successor_task_id,
            dependency_type=DependencyType(dependency_type),
            lag_days=lag_days,
        )
        saved = self._repo.save(dep)
        self._session.commit()
        return saved

    def remove_dependency(self, successor_task_id: int, predecessor_task_id: int, user_id: int) -> None:
        self._owned_task(successor_task_id, user_id)
        self._repo.delete(predecessor_task_id, successor_task_id)
        self._session.commit()

    def _owned_task(self, task_id: int, user_id: int) -> None:
        if self._task_repo.find_by_id_for_user(task_id, user_id) is None:
            raise NotFoundError("Task", task_id)

    def _dep_to_dict(self, dep: TaskDependency) -> dict:
        return {
            "predecessor_task_id": dep.predecessor_task_id,
            "successor_task_id": dep.successor_task_id,
            "dependency_type": dep.dependency_type.value if isinstance(dep.dependency_type, DependencyType) else dep.dependency_type,
            "lag_days": dep.lag_days,
            "created_at": dep.created_at,
        }
