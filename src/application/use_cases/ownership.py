"""Ownership checks.

Now that several users share the same API, every operation that reads or modifies by ID
must check "is this ID mine". Without it, just changing a sequential ID
reaches other people's data.

Both not found and owned by someone else become ``NotFoundError``.
Answering 403 separately would reveal that "the ID exists", letting a brute-force attack count
whether other people's data exists.
"""

from __future__ import annotations

from typing import Protocol

from src.domain.exceptions import NotFoundError


class OwnedRecord(Protocol):
    """A record that belongs to a user."""

    user_id: int


def owned_by[T: OwnedRecord](
    record: T | None, user_id: int, *, resource: str, resource_id: int
) -> T:
    if record is None or record.user_id != user_id:
        raise NotFoundError(resource, resource_id)
    return record
