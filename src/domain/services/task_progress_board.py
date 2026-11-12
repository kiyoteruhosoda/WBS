"""Compute task progress, including roll-ups from children (design doc §5.1, ADR-0010).

- Task without children: ``actual ÷ (actual + remaining)`` from its own actual and remaining
- Task with children: the sum of actuals of itself and all descendants, and the sum of remaining of the descendants without children (leaves),
  go through the same formula. The parent's own remaining (estimate / manual value) is not counted (to avoid double counting with the children).
  CANCELLED leaves count only their actuals, with remaining 0 (work no longer to be done does not hold back the parent's completion).
  If no leaf's remaining is determined (both remaining and estimate empty), the rolled-up remaining is undetermined too (None).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus
from src.domain.value_objects.work_figures import WorkFigures


class TaskProgressBoard:
    """Build from one person's tasks (excluding deleted ones) and the actual totals per task."""

    def __init__(self, tasks: Iterable[Task], actual_hours_by_task: Mapping[int, float]) -> None:
        self._tasks: dict[int, Task] = {t.id: t for t in tasks if t.id is not None}
        self._actual = actual_hours_by_task
        self._children: dict[int, list[int]] = defaultdict(list)
        for task in self._tasks.values():
            parent_id = task.parent_task_id
            if parent_id is not None and parent_id != task.id and parent_id in self._tasks:
                self._children[parent_id].append(task.id)

    def actual_hours(self, task_id: int | None) -> float:
        if task_id is None:
            return 0.0
        return float(self._actual.get(task_id, 0.0))

    def has_subtasks(self, task_id: int | None) -> bool:
        return task_id is not None and bool(self._children.get(task_id))

    def figures(self, task: Task) -> WorkFigures:
        """Actual and remaining to feed into the progress formula (rolled up if it has children)."""
        own_actual = self.actual_hours(task.id)
        if not self.has_subtasks(task.id):
            return task.work_figures(own_actual)

        actual = own_actual
        remainders: list[float | None] = []
        for node in self.descendants(task.id):
            node_actual = self.actual_hours(node.id)
            actual += node_actual
            if self.has_subtasks(node.id):
                continue
            if node.status == TaskStatus.CANCELLED:
                remainders.append(0.0)
            else:
                remainders.append(node.remaining_hours_from(node_actual))
        known = [r for r in remainders if r is not None]
        remaining = round(sum(known), 2) if known else None
        return WorkFigures(actual_hours=round(actual, 2), remaining_hours=remaining)

    def progress_percent(self, task: Task) -> float | None:
        return self.figures(task).progress_percent(done=task.status == TaskStatus.DONE)

    def descendants(self, root_id: int) -> Iterator[Task]:
        """Descendants (excluding itself)."""
        # Never revisit a visited node, so this stops even if parent/child links form a cycle
        seen = {root_id}
        stack = list(self._children.get(root_id, ()))
        while stack:
            task_id = stack.pop()
            if task_id in seen:
                continue
            seen.add(task_id)
            yield self._tasks[task_id]
            stack.extend(self._children.get(task_id, ()))
