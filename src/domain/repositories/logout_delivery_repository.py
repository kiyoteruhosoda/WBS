"""Remembers whether a logout notice "arrived for the first time".

⚠ **Exists only to reject replays.** Senders reuse the same ``jti`` on resend, so
without rejecting them, **a resend of an old notice could drop a currently live session**
(a resend right after the stopped person signed in again would kill that new session).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime


class LogoutDeliveryRepository(ABC):
    @abstractmethod
    def record(self, *, jti: str, now: datetime) -> bool:
        """If this is the first notice, record it and return ``True``. ``False`` if already received."""

    @abstractmethod
    def delete_expired(self, now: datetime) -> int:
        """Clean up records that no longer matter (keeping them rejects nothing anymore)."""


__all__ = ["LogoutDeliveryRepository"]
