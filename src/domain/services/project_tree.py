"""One person's project tree (task #187 / ADR-0024).

Projects number in the tens, so display paths, roll-up group targets and cycle checks
fetch everything once and walk it here. ⚠ **Filtering (including descendants) uses a recursive CTE in the DB**
(``ProjectRepository.subtree_ids``) — so the task side, which has many rows, is filtered in one query.
"""

from __future__ import annotations

from collections.abc import Iterable

from src.domain.entities.project import Project

PATH_SEPARATOR = " / "


class ProjectTree:
    def __init__(self, projects: Iterable[Project]) -> None:
        self._projects: dict[int, Project] = {p.id: p for p in projects if p.id is not None}

    def __contains__(self, project_id: object) -> bool:
        return project_id in self._projects

    def get(self, project_id: int | None) -> Project | None:
        return self._projects.get(project_id) if project_id is not None else None

    def ancestors_or_self(self, project_id: int | None) -> list[int]:
        """Ids from self up to the root (self first). ⚠ Stops even with a broken cycle."""
        chain: list[int] = []
        seen: set[int] = set()
        current = project_id
        while current is not None and current in self._projects and current not in seen:
            chain.append(current)
            seen.add(current)
            current = self._projects[current].parent_project_id
        return chain

    def root_of(self, project_id: int) -> int:
        """Id of the top-level project (members attach here. ADR-0055). Itself if not in the tree."""
        chain = self.ancestors_or_self(project_id)
        return chain[-1] if chain else project_id

    def subtree_ids(self, project_id: int) -> set[int]:
        """Ids of itself and its descendants."""
        children: dict[int, list[int]] = {}
        for pid, p in self._projects.items():
            if p.parent_project_id is not None:
                children.setdefault(p.parent_project_id, []).append(pid)
        found: set[int] = set()
        stack = [project_id] if project_id in self._projects else []
        while stack:
            current = stack.pop()
            if current in found:
                continue
            found.add(current)
            stack.extend(children.get(current, []))
        return found

    def would_cycle(self, project_id: int, new_parent_id: int | None) -> bool:
        """Whether moving ``project_id`` under ``new_parent_id`` makes a cycle (under itself or its descendants is a cycle)."""
        if new_parent_id is None:
            return False
        return project_id in self.ancestors_or_self(new_parent_id)

    def path_names(self, project_id: int | None) -> list[str]:
        """Names from the root down to itself ("parent", "child")."""
        return [self._projects[i].name for i in reversed(self.ancestors_or_self(project_id))]

    def path(self, project_id: int | None) -> str | None:
        """Display path ("parent / child"). None for unclassified or unknown ids."""
        names = self.path_names(project_id)
        return PATH_SEPARATOR.join(names) if names else None

    def is_effectively_archived(self, project_id: int) -> bool:
        """Whether it or any ancestor is archived (everything under an archived branch is removed from choices)."""
        return any(self._projects[i].is_archived for i in self.ancestors_or_self(project_id))

    def group_under(self, project_id: int | None, top: int | None) -> int | None:
        """Roll-up group target: id of the branch, among the direct children of ``top``, that contains ``project_id``.

        If ``top`` is None, the root (top-level project). If ``project_id`` is ``top`` itself,
        ``top`` (for tasks attached directly under it). Outside ``top``'s branch or unclassified: None.
        """
        chain = self.ancestors_or_self(project_id)
        if not chain:
            return None
        if top is None:
            return chain[-1]
        if chain[0] == top:
            return top
        for child, parent in zip(chain, chain[1:], strict=False):
            if parent == top:
                return child
        return None

    def children_of(self, parent_id: int | None) -> list[Project]:
        """Direct children (in sort order)."""
        return sorted(
            (p for p in self._projects.values() if p.parent_project_id == parent_id),
            key=lambda p: (p.sort_order, p.id or 0),
        )

    def milestone_reachable(self, milestone_project_id: int | None, task_project_id: int | None) -> bool:
        """Whether this milestone can be attached to the task (ADR-0024).

        An unclassified milestone attaches to any task. A project's milestone attaches only
        to tasks of that project or **its descendants** (a parent's milestone also closes the children's work).
        """
        if milestone_project_id is None:
            return True
        return milestone_project_id in self.ancestors_or_self(task_project_id)


__all__ = ["PATH_SEPARATOR", "ProjectTree"]
