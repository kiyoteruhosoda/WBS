"""Token presented when calling the IdP's **admin API**.

Obtained with ``client_credentials`` + ``private_key_jwt``. It identifies as **this app's
service account** (``MACHINE_CLIENT_ID``), separate from the login registration
(``OIDC_CLIENT_ID``; public + PKCE, holds no key).

- **The audience is ``{issuer}/admin``.** Admin API tokens are accepted only with this ``aud``.
    ⚠ **Not a setting** -- the value follows from the issuer; it is not for operators to choose.
- **The method is always ``private_key_jwt``.** Even when login uses a public client, the machine identifies with a key.
- **The token endpoint comes from discovery** (same source as the login and deactivation endpoints).

⚠ **This service account must be bound as the app's identity on the IdP side.**
Until then the admin API keeps returning 403 (the token itself can still be obtained).
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import httpx

from src.domain.exceptions import IdentityProviderUnavailableError
from src.infrastructure.auth.auth_settings import AuthConfigurationError, AuthSettings
from src.infrastructure.auth.client_assertion import (
    ASSERTION_TYPE,
    ClientAssertionRequest,
    build_client_assertion,
)
from src.infrastructure.auth.idp_http import IDP_HEADERS
from src.infrastructure.auth.oidc_discovery import OidcDiscoveryClient
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

#: How long before expiry to fetch a new one (seconds). ⚠ **Never 0** (expiring mid-request fails with 401).
RENEW_MARGIN_SECONDS = 60.0

#: Lifetime assumed when the expiry cannot be read (seconds). ⚠ Reading it as never-expiring would never refetch.
FALLBACK_LIFETIME_SECONDS = 60.0


def admin_audience(issuer: str) -> str:
    """Audience stamped into admin API tokens.

    ⚠ **``issuer`` includes the tenant** (``https://identity.example/<tenant>``), so
    the audience is that with ``/admin`` appended.
    """
    return f"{issuer.rstrip('/')}/admin"


class AdminToken(Protocol):
    """Something that provides one token for the admin API.

    The roster side only needs these two. **Depend on this shape, not the class**, so
    tests can substitute it without running an IdP.
    """

    def token(self) -> str: ...

    def invalidate(self) -> None: ...


class AdminApiTokenSource:
    """Obtain a token for the admin API and reuse it until shortly before it expires.

    One per process. Fetching a new one every cycle would add an IdP round trip per reconciliation.
    """

    def __init__(
        self,
        settings: AuthSettings,
        discovery: OidcDiscoveryClient | None = None,
        *,
        monotonic: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._discovery = discovery or OidcDiscoveryClient(
            settings.issuer, timeout_seconds=settings.http_timeout_seconds
        )
        self._monotonic = monotonic
        self._lock = threading.Lock()
        self._token = ""
        self._expires_at = 0.0

    def token(self) -> str:
        client_id = self._settings.machine_client_id
        if not client_id:
            raise AuthConfigurationError("MACHINE_CLIENT_ID is not configured")
        with self._lock:
            if self._token and self._monotonic() < self._expires_at:
                return self._token
        discovery = self._discovery.get()
        issued, lifetime = self._request(
            client_id=client_id,
            token_endpoint=discovery.token_endpoint,
            audience=admin_audience(discovery.issuer),
        )
        with self._lock:
            self._token = issued
            self._expires_at = self._monotonic() + max(lifetime - RENEW_MARGIN_SECONDS, 1.0)
            return self._token

    def invalidate(self) -> None:
        """Discard the cached token (call this on a 401)."""
        with self._lock:
            self._token = ""
            self._expires_at = 0.0

    def _request(self, *, client_id: str, token_endpoint: str, audience: str) -> tuple[str, float]:
        assertion = build_client_assertion(
            ClientAssertionRequest(
                client_id=client_id,
                audience=token_endpoint,
                private_key_pem=self._private_key(),
                kid=self._settings.machine_private_key_kid,
                now=utcnow(),
            )
        )
        payload = self._post(
            token_endpoint, client_id=client_id, assertion=assertion, audience=audience
        )
        token = payload.get("access_token")
        if not isinstance(token, str) or not token:
            raise IdentityProviderUnavailableError("the token response has no access_token")
        lifetime = payload.get("expires_in")
        if isinstance(lifetime, bool) or not isinstance(lifetime, int | float):
            return token, FALLBACK_LIFETIME_SECONDS
        return token, float(lifetime)

    def _private_key(self) -> str:
        path = self._settings.machine_private_key_file
        if not path:
            raise AuthConfigurationError("MACHINE_CLIENT_ID requires MACHINE_PRIVATE_KEY_FILE")
        try:
            return Path(path).read_text(encoding="utf-8")
        except OSError as error:
            # As 0400 root the container's runtime user cannot read it (match the group to the runtime gid).
            raise AuthConfigurationError(
                f"cannot read the machine private key: {type(error).__name__}"
            ) from error

    def _post(
        self, endpoint: str, *, client_id: str, assertion: str, audience: str
    ) -> dict[str, object]:
        form = {
            "grant_type": "client_credentials",
            "client_id": client_id,
            "client_assertion_type": ASSERTION_TYPE,
            "client_assertion": assertion,
            # ⚠ The audience is **required** for the admin API. Without it the token carries no permissions
            #   and the admin API rejects it.
            "resource": audience,
        }
        try:
            response = httpx.post(
                endpoint,
                data=form,
                headers={"Accept": "application/json", **IDP_HEADERS},
                timeout=self._settings.http_timeout_seconds,
            )
        except httpx.HTTPError as error:
            raise IdentityProviderUnavailableError(
                f"the token endpoint is unreachable: {type(error).__name__}"
            ) from error
        if response.status_code != 200:
            # ⚠ Do not log the body as is (it may contain a token).
            logger.warning(
                "failed to obtain a token with the machine identity",
                extra={
                    "event": "auth.oidc.admin_token_failed",
                    "status_code": response.status_code,
                },
            )
            raise IdentityProviderUnavailableError(
                f"the token endpoint returned {response.status_code}"
            )
        try:
            body = response.json()
        except ValueError as error:
            raise IdentityProviderUnavailableError("the token response is not JSON") from error
        return body if isinstance(body, dict) else {}


__all__ = [
    "FALLBACK_LIFETIME_SECONDS",
    "RENEW_MARGIN_SECONDS",
    "AdminApiTokenSource",
    "AdminToken",
    "admin_audience",
]
