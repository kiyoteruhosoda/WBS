"""Project (task #187 / ADR-0024).

⚠ **Can be nested to any depth** (no depth limit). The parent is held in ``parent_project_id`` (adjacency list),
and descendants are fetched with a recursive CTE (same shape as nolumiatask ADR-0046). Cycles are not allowed (``ProjectTree``).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.exceptions import ValidationError
from src.domain.value_objects.project_status import ProjectStatus

NAME_MAX_LENGTH = 200
CODE_MAX_LENGTH = 32


def project_name(raw: str) -> str:
    """The name with surrounding whitespace stripped. Rejects empty or too-long names."""
    name = raw.strip()
    if not name:
        raise ValidationError("a project needs a name")
    if len(name) > NAME_MAX_LENGTH:
        raise ValidationError(f"a project name must be at most {NAME_MAX_LENGTH} characters")
    return name


def project_code(raw: str | None) -> str | None:
    """Project code (optional; a short tag shown next to the name). Strips surrounding whitespace; None if empty. Rejects too-long codes.

    Not unique (currently used only for display).
    """
    if raw is None:
        return None
    code = raw.strip()
    if not code:
        return None
    if len(code) > CODE_MAX_LENGTH:
        raise ValidationError(f"a project code must be at most {CODE_MAX_LENGTH} characters")
    return code


@dataclass
class Project:
    id: int | None
    user_id: int
    name: str
    #: None = top level
    parent_project_id: int | None = None
    color: str | None = None
    #: Optional short code (display only; not unique)
    code: str | None = None
    description: str | None = None
    status: ProjectStatus = ProjectStatus.ACTIVE
    #: Order among siblings (from 0; moving one renumbers all siblings)
    sort_order: int = 0
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @property
    def is_archived(self) -> bool:
        return self.status is ProjectStatus.ARCHIVED
