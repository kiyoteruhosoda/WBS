"""1 人ぶんのプロジェクトの木（task #187 / ADR-0024）。

プロジェクトは数十のオーダーなので、表示の道筋・積み上げの束ね先・環の判定は、
全部を 1 回引いてからここで辿る。⚠ **絞り込み（子孫を含む）は DB の再帰 CTE**
（``ProjectRepository.subtree_ids``）で引く——行の数が多いタスクの側を、1 回のクエリで絞るため。
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
        """自分から根までの id（自分が先頭）。⚠ 壊れた環があっても止まる。"""
        chain: list[int] = []
        seen: set[int] = set()
        current = project_id
        while current is not None and current in self._projects and current not in seen:
            chain.append(current)
            seen.add(current)
            current = self._projects[current].parent_project_id
        return chain

    def subtree_ids(self, project_id: int) -> set[int]:
        """自分と子孫の id。"""
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
        """``project_id`` を ``new_parent_id`` の下へ移すと環になるか（自分・自分の子孫の下は環）。"""
        if new_parent_id is None:
            return False
        return project_id in self.ancestors_or_self(new_parent_id)

    def path_names(self, project_id: int | None) -> list[str]:
        """根から自分までの名前（「親」「子」）。"""
        return [self._projects[i].name for i in reversed(self.ancestors_or_self(project_id))]

    def path(self, project_id: int | None) -> str | None:
        """表示用の道筋（「親 / 子」）。未分類・知らない id は None。"""
        names = self.path_names(project_id)
        return PATH_SEPARATOR.join(names) if names else None

    def is_effectively_archived(self, project_id: int) -> bool:
        """自分か祖先のどれかが保管されているか（保管した枝の下は丸ごと選び先から外す）。"""
        return any(self._projects[i].is_archived for i in self.ancestors_or_self(project_id))

    def group_under(self, project_id: int | None, top: int | None) -> int | None:
        """積み上げの束ね先: ``top`` の直下の子のうち ``project_id`` を含む枝の id。

        ``top`` が None なら根（最上位のプロジェクト）。``project_id`` が ``top`` そのものなら
        ``top``（その直下に付いたタスクの分）。``top`` の枝の外・未分類は None。
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
        """直下の子（並び順）。"""
        return sorted(
            (p for p in self._projects.values() if p.parent_project_id == parent_id),
            key=lambda p: (p.sort_order, p.id or 0),
        )

    def milestone_reachable(self, milestone_project_id: int | None, task_project_id: int | None) -> bool:
        """そのタスクにこのマイルストーンを付けられるか（ADR-0024）。

        未分類のマイルストーンはどのタスクにも付く。プロジェクトのマイルストーンは、
        そのプロジェクトか**その子孫**のタスクにだけ付く（親の節目は子の作業も締める）。
        """
        if milestone_project_id is None:
            return True
        return milestone_project_id in self.ancestors_or_self(task_project_id)


__all__ = ["PATH_SEPARATOR", "ProjectTree"]
