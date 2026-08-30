from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class StartedLoginDTO:
    authorization_url: str
    # コールバックが「この往復を始めたブラウザ」から戻ってきたことを確かめるための
    # 合言葉。Presentation 層が短命な Cookie に載せ、コールバックで突き合わせる。
    browser_binding: str


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
