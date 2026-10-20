from __future__ import annotations

from abc import ABC, abstractmethod

from src.domain.entities.project_member import ProjectMember


class ProjectMemberRepository(ABC):
    @abstractmethod
    def find_by_project(self, project_id: int) -> list[ProjectMember]:
        """そのプロジェクト（根）のメンバー（加えた順）。"""

    @abstractmethod
    def find_by_user(self, user_id: int) -> list[ProjectMember]:
        """その人がメンバーになっている根の行。"""

    @abstractmethod
    def find(self, project_id: int, user_id: int) -> ProjectMember | None: ...

    @abstractmethod
    def save(self, member: ProjectMember) -> ProjectMember:
        """足す（id が無い）か、役割・1 日の工数・従事率を書き換える。"""

    @abstractmethod
    def delete(self, project_id: int, user_id: int) -> None: ...

    @abstractmethod
    def delete_all(self, project_id: int) -> None:
        """そのプロジェクトの行を全部消す（根でなくなる・消すとき）。"""
