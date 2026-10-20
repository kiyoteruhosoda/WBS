"""メンバーや担当者に選べる人を引く口（task #544 / ADR-0055 決定 5）。

選べるのは WBS に 1 度でもログインした人（``users`` の行）だけ。招待の仕組みは持たない。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class Person:
    id: int
    display_name: str
    email: str


class PersonDirectory(Protocol):
    def choosable(self) -> list[Person]:
        """止めていない人。SSO では assay と結び付いている人だけ（照合で外れた人・初期ユーザーは出ない）。"""
        ...

    def by_ids(self, user_ids: set[int]) -> dict[int, Person]:
        """名前を引く（止めた人・外れた人も。担当やメンバーに残っていれば名前は出す）。"""
        ...


__all__ = ["Person", "PersonDirectory"]
