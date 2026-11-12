from __future__ import annotations

import hashlib
from dataclasses import dataclass


@dataclass(frozen=True)
class StartedLoginDTO:
    authorization_url: str
    # A shared secret to confirm that the callback came back from "the browser that started this round trip".
    # The Presentation layer puts it in a short-lived cookie and matches it on the callback.
    browser_binding: str


@dataclass(frozen=True)
class IssuedSessionDTO:
    """Tokens put in cookies. Access token only (refresh tokens are no longer issued, ADR-0071)."""

    access_token: str


@dataclass(frozen=True)
class CompletedLoginDTO:
    session: IssuedSessionDTO
    redirect_path: str


@dataclass(frozen=True)
class AuthenticatedUserDTO:
    user_id: int
    email: str
    display_name: str
    timezone: str
    language: str
    #: Whether they can create a top-level project (decides whether the screen shows the button; the server checks it in the DB, ADR-0065)
    can_create_projects: bool = False
    #: The calling app's ``client_id`` when coming through the machine endpoint (ADR-0068). ``None`` for a human login
    machine_client_id: str | None = None

    @property
    def id_hash(self) -> str:
        """User identifier for logs. Neither the ID nor the email address goes into logs as is (task #812)."""
        return hashlib.sha256(str(self.user_id).encode()).hexdigest()[:16]
