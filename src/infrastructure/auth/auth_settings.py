"""認証まわりの設定を環境変数から 1 つのオブジェクトにまとめる。

``build_info.py`` と同じ流儀で、環境変数を読む場所をここ 1 つに閉じ込める
（アプリの各所から ``os.getenv`` を呼ばない）。
"""

from __future__ import annotations

import enum
import os
from dataclasses import dataclass
from datetime import timedelta

from src.domain.value_objects.provisioning_policy import ProvisioningPolicy

DEFAULT_COOKIE_NAME = "wbs_session"
DEFAULT_SCOPES = "openid email profile"
SINGLE_USER_ID = 1


class AuthMode(enum.StrEnum):
    SINGLE_USER = "single_user"
    OIDC = "oidc"


class AuthConfigurationError(RuntimeError):
    """設定が足りない・矛盾している。起動時に落として気づけるようにする。"""


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: str
    provider_name: str
    post_logout_redirect_uri: str | None
    http_timeout_seconds: float
    session_ttl: timedelta
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    policy: ProvisioningPolicy

    @property
    def sso_enabled(self) -> bool:
        return self.mode is AuthMode.OIDC

    @property
    def scope_list(self) -> list[str]:
        return self.scopes.split()


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise AuthConfigurationError(f"{key} must be a number, got {raw!r}") from exc


def _env_domains(key: str) -> tuple[str, ...]:
    raw = os.getenv(key, "")
    return tuple(d.strip().lower() for d in raw.split(",") if d.strip())


def load_auth_settings() -> AuthSettings:
    raw_mode = os.getenv("AUTH_MODE", AuthMode.SINGLE_USER.value).strip().lower()
    try:
        mode = AuthMode(raw_mode)
    except ValueError as exc:
        allowed = ", ".join(m.value for m in AuthMode)
        raise AuthConfigurationError(f"AUTH_MODE must be one of: {allowed} (got {raw_mode!r})") from exc

    issuer = os.getenv("OIDC_ISSUER", "").strip().rstrip("/")
    client_id = os.getenv("OIDC_CLIENT_ID", "").strip()
    client_secret = os.getenv("OIDC_CLIENT_SECRET") or None
    redirect_uri = os.getenv("OIDC_REDIRECT_URI", "").strip()

    if mode is AuthMode.OIDC:
        missing = [
            name
            for name, value in (
                ("OIDC_ISSUER", issuer),
                ("OIDC_CLIENT_ID", client_id),
                ("OIDC_REDIRECT_URI", redirect_uri),
            )
            if not value
        ]
        if missing:
            raise AuthConfigurationError(
                "AUTH_MODE=oidc requires " + ", ".join(missing)
            )
        if not issuer.startswith("https://") and not issuer.startswith("http://localhost"):
            # ID トークンの取得経路が TLS でないと、途中で差し替えられても気づけない
            raise AuthConfigurationError(
                f"OIDC_ISSUER must use https (got {issuer!r}); http is only allowed for localhost"
            )

    return AuthSettings(
        mode=mode,
        issuer=issuer,
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        scopes=os.getenv("OIDC_SCOPES", DEFAULT_SCOPES).strip() or DEFAULT_SCOPES,
        provider_name=os.getenv("OIDC_PROVIDER_NAME", "SSO").strip() or "SSO",
        post_logout_redirect_uri=os.getenv("AUTH_POST_LOGOUT_REDIRECT_URI") or None,
        http_timeout_seconds=_env_float("OIDC_HTTP_TIMEOUT_SECONDS", 10.0),
        session_ttl=timedelta(hours=_env_float("AUTH_SESSION_TTL_HOURS", 12.0)),
        cookie_name=os.getenv("AUTH_COOKIE_NAME", DEFAULT_COOKIE_NAME).strip() or DEFAULT_COOKIE_NAME,
        cookie_secure=_env_bool("AUTH_COOKIE_SECURE", True),
        cookie_samesite=os.getenv("AUTH_COOKIE_SAMESITE", "lax").strip().lower() or "lax",
        policy=ProvisioningPolicy(
            auto_provision=_env_bool("OIDC_AUTO_PROVISION", True),
            allowed_email_domains=_env_domains("OIDC_ALLOWED_EMAIL_DOMAINS"),
            require_verified_email=_env_bool("OIDC_REQUIRE_VERIFIED_EMAIL", True),
        ),
    )
