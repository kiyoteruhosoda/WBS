"""プロジェクトの木（task #187 / ADR-0024）: 道筋・環・積み上げの束ね先・マイルストーンの届く範囲。"""

from __future__ import annotations

from src.domain.entities.project import Project
from src.domain.services.project_tree import ProjectTree
from src.domain.value_objects.project_status import ProjectStatus


def _p(pid: int, name: str, parent: int | None = None, order: int = 0, **kw) -> Project:
    return Project(id=pid, user_id=1, name=name, parent_project_id=parent, sort_order=order, **kw)


# 仕事(1) ─ 案件 A(2) ─ 設計(3)
#        └ 案件 B(4)
# 私用(5)
TREE = ProjectTree(
    [
        _p(1, "仕事"),
        _p(2, "案件 A", 1, order=0),
        _p(3, "設計", 2),
        _p(4, "案件 B", 1, order=1),
        _p(5, "私用", order=1),
    ]
)


def test_path_reads_from_the_root() -> None:
    assert TREE.path(3) == "仕事 / 案件 A / 設計"
    assert TREE.path(5) == "私用"
    assert TREE.path(None) is None
    assert TREE.path(99) is None


def test_subtree_includes_every_depth() -> None:
    assert TREE.subtree_ids(1) == {1, 2, 3, 4}
    assert TREE.subtree_ids(2) == {2, 3}
    assert TREE.subtree_ids(99) == set()


def test_moving_under_itself_or_a_descendant_is_a_cycle() -> None:
    assert TREE.would_cycle(1, 1)
    assert TREE.would_cycle(1, 3)
    assert not TREE.would_cycle(2, 4)
    assert not TREE.would_cycle(3, None)


def test_group_under_rolls_a_branch_up_to_the_child_of_the_top() -> None:
    assert TREE.group_under(3, None) == 1
    assert TREE.group_under(3, 1) == 2
    assert TREE.group_under(1, 1) == 1  # 直に付いた分
    assert TREE.group_under(5, 1) is None  # 枝の外
    assert TREE.group_under(None, None) is None


def test_milestone_reaches_its_project_and_descendants_only() -> None:
    assert TREE.milestone_reachable(None, None)
    assert TREE.milestone_reachable(None, 3)
    assert TREE.milestone_reachable(1, 3)
    assert TREE.milestone_reachable(3, 3)
    assert not TREE.milestone_reachable(3, 1)
    assert not TREE.milestone_reachable(4, 2)
    assert not TREE.milestone_reachable(1, None)


def test_archived_parent_archives_its_branch() -> None:
    tree = ProjectTree([_p(1, "仕事", status=ProjectStatus.ARCHIVED), _p(2, "案件", 1)])
    assert tree.is_effectively_archived(2)
    assert not ProjectTree([_p(1, "仕事"), _p(2, "案件", 1)]).is_effectively_archived(2)


def test_a_broken_cycle_in_the_data_does_not_hang() -> None:
    tree = ProjectTree([_p(1, "a", 2), _p(2, "b", 1)])
    assert tree.ancestors_or_self(1) == [1, 2]
    assert tree.subtree_ids(1) == {1, 2}


def test_children_are_in_sort_order() -> None:
    assert [p.name for p in TREE.children_of(1)] == ["案件 A", "案件 B"]
    assert [p.name for p in TREE.children_of(None)] == ["仕事", "私用"]
