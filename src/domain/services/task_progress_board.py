"""タスクの進捗率を、親子の積み上げまで含めて出す（設計書 §5.1・ADR-0010）。

- 子を持たないタスク: 自分の実績と残で ``実績 ÷（実績 ＋ 残）``
- 子を持つタスク: 自分と全子孫の実績の合計と、子孫のうち子を持たないもの（葉）の残の合計を、
  同じ式に通す。親自身の残（見積・手の値）は数えない（子と二重に数えないため）。
  CANCELLED の葉は実績だけ数え、残は 0 とする（もうやらない仕事は親の完了を止めない）。
  葉の残がどれも決まらない（残も見積も空）なら、積み上げの残も決まらない（None）。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping

from src.domain.entities.task import Task
from src.domain.value_objects.task_status import TaskStatus
from src.domain.value_objects.work_figures import WorkFigures


class TaskProgressBoard:
    """1 人ぶんのタスク（削除済みを除く）と、タスクごとの実績の合計から作る。"""

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
        """進捗率の式に入れる実績と残（子を持つなら積み上げ）。"""
        own_actual = self.actual_hours(task.id)
        if not self.has_subtasks(task.id):
            return task.work_figures(own_actual)

        actual = own_actual
        remainders: list[float | None] = []
        for node in self._descendants(task.id):
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

    def _descendants(self, root_id: int) -> Iterator[Task]:
        # 親子が輪になっていても止まるよう、通ったものは二度辿らない
        seen = {root_id}
        stack = list(self._children.get(root_id, ()))
        while stack:
            task_id = stack.pop()
            if task_id in seen:
                continue
            seen.add(task_id)
            yield self._tasks[task_id]
            stack.extend(self._children.get(task_id, ()))
