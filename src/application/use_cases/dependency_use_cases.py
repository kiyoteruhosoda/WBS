from __future__ import annotations

from src.domain.entities.task_dependency import TaskDependency
from src.domain.exceptions import CyclicDependencyError, NotFoundError
from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.value_objects.dependency_type import DependencyType


def _has_cycle(all_deps: list[TaskDependency], new_pred: int, new_succ: int) -> bool:
    """Whether adding ``new_pred -> new_succ`` makes a cycle.

    It cycles when ``new_succ`` is already an ancestor of ``new_pred`` (reachable by following
    predecessors from ``new_pred``). A dependency on itself is also treated as a cycle.
    """
    graph: dict[int, list[int]] = {}
    for dep in all_deps:
        graph.setdefault(dep.successor_task_id, []).append(dep.predecessor_task_id)
    visited = set()
    stack = [new_pred]
    while stack:
        node = stack.pop()
        if node == new_succ:
            return True
        if node in visited:
            continue
        visited.add(node)
        for pred in graph.get(node, []):
            stack.append(pred)
    return False


class DependencyUseCases:
    def __init__(self, *, dependencies: TaskDependencyRepository, tasks: TaskRepository) -> None:
        self._repo = dependencies
        self._task_repo = tasks

    def get_dependencies(self, task_id: int, user_id: int) -> dict:
        self._owned_task(task_id, user_id)
        all_for_task = self._repo.find_by_task_for_user(task_id, user_id)
        predecessors = [d for d in all_for_task if d.successor_task_id == task_id]
        successors = [d for d in all_for_task if d.predecessor_task_id == task_id]
        return {
            "task_id": task_id,
            "predecessors": [self._dep_to_dict(d) for d in predecessors],
            "successors": [self._dep_to_dict(d) for d in successors],
        }

    def add_dependency(self, successor_task_id: int, predecessor_task_id: int, user_id: int, dependency_type: str = "FS", lag_days: int = 0) -> TaskDependency:
        # Both ends must be the caller's tasks. If either belongs to someone else,
        # a task ID that should not exist for the caller could be written as a dependency.
        self._owned_task(successor_task_id, user_id)
        self._owned_task(predecessor_task_id, user_id)
        # Cycles can only occur within the caller's own dependencies (both ends were checked above to be the caller's tasks).
        all_deps = self._repo.find_all_for_user(user_id)
        if _has_cycle(all_deps, predecessor_task_id, successor_task_id):
            raise CyclicDependencyError()
        dep = TaskDependency(
            predecessor_task_id=predecessor_task_id,
            successor_task_id=successor_task_id,
            dependency_type=DependencyType(dependency_type),
            lag_days=lag_days,
        )
        return self._repo.save(dep)

    def remove_dependency(self, successor_task_id: int, predecessor_task_id: int, user_id: int) -> None:
        # Check that the successor (task_id in the URL) is the caller's. Even if the predecessor points at someone else's
        # task, the add endpoint checks both ends, so no such row exists and nothing is deleted.
        self._owned_task(successor_task_id, user_id)
        self._repo.delete(predecessor_task_id, successor_task_id)

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
