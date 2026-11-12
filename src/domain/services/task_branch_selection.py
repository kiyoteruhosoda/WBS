"""Split tasks selected in bulk into per-branch units to move (task #187 / ADR-0030).

A child task belongs to the same project as its parent task (ADR-0024 item 4). So a bulk move writes only
**branch roots** (tasks without a parent), and their descendants follow the root. Selected tasks fall into 3 groups:

- ``roots``: tasks without a parent. These are moved (descendants move with them)
- ``followers``: child tasks with some ancestor also selected. They move with the ancestor, so are not written separately
- ``stranded``: child tasks with no ancestor selected. A child alone cannot be in a different project, so they cannot be moved

⚠ A child whose parent is not found (deleted) is treated as a root (same as task updates; a deleted parent alone must not make it immovable).
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
        """``parent_of`` is "id → parent id" for non-deleted tasks. Keeps the selection order and does not duplicate."""
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
        """⚠ Stops even with a broken cycle."""
        seen = {task_id}
        current = parent_of.get(task_id)
        while current is not None and current in parent_of and current not in seen:
            if current in chosen:
                return True
            seen.add(current)
            current = parent_of.get(current)
        return False


__all__ = ["TaskBranchSelection"]
