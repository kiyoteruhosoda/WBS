from __future__ import annotations

from pydantic import BaseModel


class AuthConfigResponse(BaseModel):
    """ログイン画面を出すべきかをフロントが判断するための情報。"""

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


class LogoutResponse(BaseModel):
    # IdP 側のセッションも切るための遷移先。IdP が対応していなければ null。
    end_session_url: str | None = None
