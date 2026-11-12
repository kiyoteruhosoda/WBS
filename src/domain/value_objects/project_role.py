"""Role of a project member (task #544 / ADR-0055)."""

from __future__ import annotations

import enum


class ProjectRole(enum.StrEnum):
    MANAGER = "manager"
    """Admin. Adds/removes members, changes roles, deletes the top-level project or moves it under another."""
    MEMBER = "member"
    """Member. Reads and writes the projects, tasks and milestones of that tree."""
