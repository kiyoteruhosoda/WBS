"""Tokens this app issues itself (ADR-0069, ADR-0071). Separate from assay's tokens; only this app knows their contents.

Only access tokens are issued (ADR-0071; refresh tokens and logout tickets are no longer issued).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.domain.value_objects.continued_sign_in import ContinuedSignIn


@dataclass(frozen=True)
class AccessTokenContents:
    user: AuthenticatedUserDTO
    session_id: str


class SessionTokens(ABC):
    @abstractmethod
    def access_token(self, user: AuthenticatedUserDTO, *, session_id: str, now: datetime) -> str:
        """⚠ **Verification does not hit the DB, so include everything needed about the user.**"""

    @abstractmethod
    def read_access(self, token: str, *, now: datetime) -> AccessTokenContents | None:
        """Verify signature and expiry and read it. ``None`` if unreadable."""

    @abstractmethod
    def continuation_of(self, token: str, *, now: datetime) -> ContinuedSignIn | None:
        """Read the login to continue from an expired access token (ADR-0071).

        ⚠ **This is not authentication.** Signature, issuer, audience and type are checked; expiry is tolerated up to the login record retention.
        The value read is used only when the same person comes back from the IdP (continuation round trip) and for logout.
        """
