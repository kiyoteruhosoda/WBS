"""Gather the authentication settings from env vars into one object.

Same style as ``build_info.py``: env vars are read in this one place only
(nothing else in the app calls ``os.getenv``).
"""

from __future__ import annotations

import enum
import json
import os
from dataclasses import dataclass
from datetime import timedelta

from src.domain.value_objects.provisioning_policy import ProvisioningPolicy

DEFAULT_COOKIE_NAME = "wbs_access_token"
#: Cookies of the refresh token and logout ticket issued in the past (ADR-0069). No longer issued; cleared if still present (ADR-0071)
REFRESH_COOKIE_NAME = "wbs_refresh_token"
LOGOUT_COOKIE_NAME = "wbs_logout_token"
#: Access token lifetime. ⚠ **This value is exactly the upper bound of "time until a deactivation takes effect"** (ADR-0069)
DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS = 300.0
#: How long the login record and the access token cookie are kept (ADR-0071). The token itself expires in 5 minutes.
#: The cookie is kept after expiry so the silent continuation round trip can tell "whose login, which login".
#: Matches the longest IdP login state (30 days). Each continuation also extends the record's expiry
SIGN_IN_CARRY = timedelta(days=30)
#: Minimum signing key length (an HS256 key is at least 32 bytes, the size of a SHA-256 output)
MIN_SIGNING_KEY_LENGTH = 32
DEFAULT_SCOPES = "openid email profile"
SINGLE_USER_ID = 1
# Values allowed for SameSite in Set-Cookie. Without rejecting here, a typo is only noticed
# "when the cookie is set at the end of login", showing nothing but a 500.
ALLOWED_SAMESITE = ("lax", "strict", "none")


class AuthMode(enum.StrEnum):
    SINGLE_USER = "single_user"
    OIDC = "oidc"


class AuthConfigurationError(RuntimeError):
    """Settings are missing or inconsistent. Fail at startup so it gets noticed."""


@dataclass(frozen=True)
class AuthSettings:
    mode: AuthMode
    #: ⚠ **Spelling with the trailing ``/`` dropped.** Different from the exact spelling the discovery document
    #: announces (the value matched exactly against the ID token's ``iss``; ``OidcDiscovery.issuer``).
    issuer: str
    client_id: str
    client_secret: str | None
    redirect_uri: str
    scopes: str
    provider_name: str
    post_logout_redirect_uri: str | None
    http_timeout_seconds: float
    cookie_name: str
    cookie_secure: bool
    cookie_samesite: str
    policy: ProvisioningPolicy
    #: Access token lifetime (ADR-0069). After expiry the SPA silently asks the IdP (ADR-0071)
    access_token_ttl: timedelta = timedelta(seconds=DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS)
    #: How long the login record and the access token cookie are kept (ADR-0071)
    sign_in_carry: timedelta = SIGN_IN_CARRY
    #: Signing key for this app's tokens. ⚠ **Must be the same across processes** (ADR-0069).
    session_signing_key: str = ""
    #: Identity used when **we** call the IdP (the service account's ``client_id``).
    #: ⚠ A registration separate from the login ``client_id``. **If empty, reconciliation does not run.**
    machine_client_id: str = ""
    machine_private_key_file: str = ""
    machine_private_key_kid: str | None = None
    #: This app's audience when other apps' servers come to read/write as machines (an assay resource. ADR-0056).
    #: ⚠ **If empty, no machine endpoint lets anything through.**
    machine_audience: str = ""
    #: **Machine** ``client_id``s of apps allowed to read/write on a user's behalf (Tracker's server. ADR-0056).
    machine_reader_client_ids: frozenset[str] = frozenset()

    @property
    def sso_enabled(self) -> bool:
        return self.mode is AuthMode.OIDC

    @property
    def reconciliation_enabled(self) -> bool:
        """Whether to run reconciliation. **Not without an identity** (nothing can be asked)."""
        return self.sso_enabled and bool(self.machine_client_id)

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


def _env_list(key: str) -> frozenset[str]:
    """Comma-separated (or a JSON array). Empty elements are dropped."""
    raw = os.getenv(key, "").strip()
    if raw.startswith("["):
        try:
            parsed = json.loads(raw)
        except ValueError as exc:
            raise AuthConfigurationError(f"{key} must be a JSON array or comma-separated") from exc
        items = [str(item) for item in parsed] if isinstance(parsed, list) else [str(parsed)]
    else:
        items = raw.split(",")
    return frozenset(item.strip() for item in items if item.strip())


def _env_samesite(key: str, *, cookie_secure: bool) -> str:
    value = os.getenv(key, "lax").strip().lower() or "lax"
    if value not in ALLOWED_SAMESITE:
        raise AuthConfigurationError(
            f"{key} must be one of: {', '.join(ALLOWED_SAMESITE)} (got {value!r})"
        )
    if value == "none" and not cookie_secure:
        # Browsers discard SameSite=None cookies without Secure.
        # The app starts but only login fails -- the most confusing way to break.
        raise AuthConfigurationError(f"{key}=none requires AUTH_COOKIE_SECURE=true")
    return value


def _load_signing_key() -> str:
    """Read the signing key. In production it is passed as a file path (``SESSION_SIGNING_KEY_FILE``). ⚠ Never log the value."""
    value = os.getenv("SESSION_SIGNING_KEY", "").strip()
    if value:
        return value
    path = os.getenv("SESSION_SIGNING_KEY_FILE", "").strip()
    if not path:
        return ""
    try:
        with open(path, encoding="utf-8") as handle:
            return handle.read().strip()
    except OSError as exc:
        raise AuthConfigurationError(f"SESSION_SIGNING_KEY_FILE could not be read: {path}") from exc


def _env_seconds(key: str, default: float) -> timedelta:
    seconds = _env_float(key, default)
    if seconds <= 0:
        raise AuthConfigurationError(f"{key} must be positive (got {seconds})")
    return timedelta(seconds=seconds)


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
            # If the ID token is fetched over a non-TLS path, tampering on the way would go unnoticed
            raise AuthConfigurationError(
                f"OIDC_ISSUER must use https (got {issuer!r}); http is only allowed for localhost"
            )

    signing_key = _load_signing_key()
    if mode is AuthMode.OIDC and len(signing_key) < MIN_SIGNING_KEY_LENGTH:
        # ⚠ Fail at startup. Filling it with random bytes would sign everyone out on every restart
        raise AuthConfigurationError(
            "AUTH_MODE=oidc requires SESSION_SIGNING_KEY_FILE "
            f"(a signing key of at least {MIN_SIGNING_KEY_LENGTH} characters)"
        )

    cookie_secure = _env_bool("AUTH_COOKIE_SECURE", True)
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
        access_token_ttl=_env_seconds(
            "ACCESS_TOKEN_EXPIRES_SECONDS", DEFAULT_ACCESS_TOKEN_EXPIRES_SECONDS
        ),
        session_signing_key=signing_key,
        cookie_name=os.getenv("AUTH_COOKIE_NAME", DEFAULT_COOKIE_NAME).strip() or DEFAULT_COOKIE_NAME,
        cookie_secure=cookie_secure,
        cookie_samesite=_env_samesite("AUTH_COOKIE_SAMESITE", cookie_secure=cookie_secure),
        policy=ProvisioningPolicy(
            auto_provision=_env_bool("OIDC_AUTO_PROVISION", True),
            allowed_email_domains=_env_domains("OIDC_ALLOWED_EMAIL_DOMAINS"),
            require_verified_email=_env_bool("OIDC_REQUIRE_VERIFIED_EMAIL", True),
            # ⚠ **Do not link by default.** An email address does not prove identity (see below).
            link_by_email=_env_bool("OIDC_LINK_BY_EMAIL", False),
        ),
        machine_client_id=os.getenv("MACHINE_CLIENT_ID", "").strip(),
        machine_private_key_file=os.getenv("MACHINE_PRIVATE_KEY_FILE", "").strip(),
        machine_private_key_kid=os.getenv("MACHINE_PRIVATE_KEY_KID", "").strip() or None,
        machine_audience=os.getenv("MACHINE_AUDIENCE", "").strip(),
        machine_reader_client_ids=_env_list("MACHINE_READER_CLIENT_IDS"),
    )
