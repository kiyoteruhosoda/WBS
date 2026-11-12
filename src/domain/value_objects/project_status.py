"""Project status (task #187 / ADR-0024)."""

from __future__ import annotations

import enum


class ProjectStatus(enum.StrEnum):
    ACTIVE = "active"
    """Active. Offered as a choice for tasks and milestones."""
    ARCHIVED = "archived"
    """Archived. Stays faintly in the tree (its tasks and actuals can still be read) but is not offered as a choice."""
