from __future__ import annotations

from src.domain.entities.task_dependency import TaskDependency
from src.domain.exceptions import CyclicDependencyError, NotFoundError
from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.value_objects.dependency_type import DependencyType


def _has_cycle(all_deps: list[TaskDependency], new_pred: int, new_succ: int) -> bool:
    """``new_pred → new_succ`` を足すと循環するか。

    循環するのは、``new_succ`` が既に ``new_pred`` の祖先（``new_pred`` から先行を
    辿って届く）であるとき。自分自身への依存も循環として扱う。
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
        # 両端とも自分のタスクであること。片方でも他人のものだと、
        # 存在しないはずのタスクの ID を依存として書き込めてしまう。
        self._owned_task(successor_task_id, user_id)
        self._owned_task(predecessor_task_id, user_id)
        # 循環は自分の依存の中でしか起きない（両端とも自分のタスクであることを上で見ている）。
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
        # 後続（URL の task_id）が自分のものであることを見る。先行は他人のタスクを
        # 指していても、足す口で両端を見ているのでその組の行は存在せず、何も消えない。
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
