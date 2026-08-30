from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StartedLoginDTO:
    authorization_url: str


@dataclass(frozen=True)
class CompletedLoginDTO:
    session_token: str
    expires_at: datetime
    redirect_path: str


@dataclass(frozen=True)
class AuthenticatedUserDTO:
    user_id: int
    email: str
    display_name: str
    timezone: str
    language: str
