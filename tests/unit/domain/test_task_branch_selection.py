"""Split bulk-selected tasks into branch roots, followers, and children that cannot move (task #187 / ADR-0030)."""

from __future__ import annotations

from src.domain.services.task_branch_selection import TaskBranchSelection

# 1 - 2 - 3 / 4 / 5; parent 9 was deleted (not in the list)
PARENT_OF: dict[int, int | None] = {1: None, 2: 1, 3: 2, 4: None, 5: 9}


def test_roots_move_and_their_selected_descendants_follow() -> None:
    selection = TaskBranchSelection.of([3, 1, 4], PARENT_OF)

    assert selection.roots == (1, 4)
    assert selection.followers == (3,)  # grandparent 1 is selected
    assert selection.stranded == ()


def test_a_subtask_without_its_ancestors_cannot_move_alone() -> None:
    selection = TaskBranchSelection.of([2, 3, 4], PARENT_OF)

    assert selection.roots == (4,)
    assert selection.followers == (3,)  # parent 2 is selected (even though 2 itself cannot move)
    assert selection.stranded == (2,)


def test_a_subtask_whose_parent_was_deleted_is_a_root() -> None:
    assert TaskBranchSelection.of([5], PARENT_OF).roots == (5,)


def test_duplicates_are_dropped_and_a_broken_cycle_stops() -> None:
    assert TaskBranchSelection.of([1, 1], PARENT_OF).roots == (1,)
    cyclic: dict[int, int | None] = {7: 8, 8: 7}
    assert TaskBranchSelection.of([7], cyclic).stranded == (7,)
