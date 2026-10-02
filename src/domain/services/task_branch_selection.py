"""まとめて選んだタスクを、枝ごとに移す単位へ分ける（task #187 / ADR-0030）。

子タスクは親タスクと同じプロジェクトに属する（ADR-0024 の 4）。なので、まとめて移すときに書くのは
**枝の根**（親の無いタスク）だけで、その子孫は根に付いてくる。選んだタスクは次の 3 つに分かれる:

- ``roots``: 親の無いタスク。これを移す（子孫も一緒に移る）
- ``followers``: 祖先のどれかも選ばれている子タスク。祖先と一緒に移るので、別に書かない
- ``stranded``: 祖先のどれも選ばれていない子タスク。子だけ別のプロジェクトにはできないので移せない

⚠ 親が見つからない（消した）子は根として扱う（タスクの更新と同じ。親が消えただけで動かせなくしない）。
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass


@dataclass(frozen=True)
class TaskBranchSelection:
    roots: tuple[int, ...]
    followers: tuple[int, ...]
    stranded: tuple[int, ...]

    @classmethod
    def of(cls, selected: Iterable[int], parent_of: Mapping[int, int | None]) -> TaskBranchSelection:
        """``parent_of`` は消していないタスクの「id → 親の id」。選んだ順を保ち、重ねない。"""
        chosen: list[int] = list(dict.fromkeys(selected))
        chosen_set = set(chosen)
        roots: list[int] = []
        followers: list[int] = []
        stranded: list[int] = []
        for task_id in chosen:
            parent = parent_of.get(task_id)
            if parent is None or parent not in parent_of:
                roots.append(task_id)
            elif cls._has_selected_ancestor(task_id, chosen_set, parent_of):
                followers.append(task_id)
            else:
                stranded.append(task_id)
        return cls(tuple(roots), tuple(followers), tuple(stranded))

    @staticmethod
    def _has_selected_ancestor(
        task_id: int, chosen: set[int], parent_of: Mapping[int, int | None]
    ) -> bool:
        """⚠ 壊れた環があっても止まる。"""
        seen = {task_id}
        current = parent_of.get(task_id)
        while current is not None and current in parent_of and current not in seen:
            if current in chosen:
                return True
            seen.add(current)
            current = parent_of.get(current)
        return False


__all__ = ["TaskBranchSelection"]
