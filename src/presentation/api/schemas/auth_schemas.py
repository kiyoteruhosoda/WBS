from __future__ import annotations

from pydantic import BaseModel


class AuthConfigResponse(BaseModel):
    """Information the frontend uses to decide whether to show the login screen."""

    mode: str
    sso_enabled: bool
    provider_name: str | None = None
    login_path: str | None = None


class CurrentUserResponse(BaseModel):
    user_id: int
    email: str
    display_name: str
    timezone: str
    language: str
    #: Whether the user can create top-level projects (ADR-0065)
    can_create_projects: bool = False


class LogoutResponse(BaseModel):
    # Where to go to also end the IdP session. null if the IdP does not support it.
    end_session_url: str | None = None

