"""The port that looks up people who can be chosen as members or assignees (task #544 / ADR-0055 decision 5).

Only people who have signed in to WBS at least once (rows in ``users``) can be chosen. There is no invitation mechanism.
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
        """People who are not deactivated. With SSO, only those linked to assay (people unlinked by reconciliation and the initial user are excluded)."""
        ...

    def by_ids(self, user_ids: set[int]) -> dict[int, Person]:
        """Look up names (deactivated and unlinked people too; names are shown if they remain as assignees or members)."""
        ...


__all__ = ["Person", "PersonDirectory"]
