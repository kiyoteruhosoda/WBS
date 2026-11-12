"""Fetching the IdP discovery document (``/.well-known/openid-configuration``)."""

from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from src.domain.exceptions import AuthenticationError
from src.infrastructure.auth.idp_http import IDP_HEADERS

# Allow list of signature algorithms. `none` and symmetric keys (HS*) are excluded.
# Verification uses public keys from JWKS, so allowing symmetric keys opens the classic
# confusion of "verifying HS256 using the public key as the secret".
SUPPORTED_SIGNING_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "ES512", "PS256", "PS384", "PS512")

DISCOVERY_CACHE_SECONDS = 3600.0


@dataclass(frozen=True)
class OidcDiscovery:
    issuer: str
    authorization_endpoint: str
    token_endpoint: str
    jwks_uri: str
    userinfo_endpoint: str | None
    end_session_endpoint: str | None
    id_token_signing_alg_values_supported: tuple[str, ...]
    token_endpoint_auth_methods_supported: tuple[str, ...]

    @property
    def allowed_algorithms(self) -> list[str]:
        advertised = [
            alg for alg in self.id_token_signing_alg_values_supported
            if alg in SUPPORTED_SIGNING_ALGORITHMS
        ]
        # Even if the IdP announces nothing (or only unsupported ones), RS256 is mandatory per spec
        return advertised or ["RS256"]


class OidcDiscoveryClient:
    """Fetch the discovery document and reuse it for a while.

    Fetching it on every login would make login availability equal to IdP availability, so
    it is kept locally for 1 hour by default.
    """

    def __init__(self, issuer: str, *, timeout_seconds: float = 10.0,
                 cache_seconds: float = DISCOVERY_CACHE_SECONDS) -> None:
        self._issuer = issuer.rstrip("/")
        self._timeout = timeout_seconds
        self._cache_seconds = cache_seconds
        self._cached: OidcDiscovery | None = None
        self._fetched_at: float | None = None

    @property
    def well_known_url(self) -> str:
        return f"{self._issuer}/.well-known/openid-configuration"

    def get(self) -> OidcDiscovery:
        # Measures elapsed time, so use a monotonic clock rather than wall time
        # (so NTP adjustments or DST do not drop or prolong the cache).
        now = time.monotonic()
        cache_is_fresh = (
            self._cached is not None
            and self._fetched_at is not None
            and now - self._fetched_at < self._cache_seconds
        )
        if cache_is_fresh:
            return self._cached
        document = self._fetch()
        self._cached = document
        self._fetched_at = now
        return document

    def _fetch(self) -> OidcDiscovery:
        try:
            response = httpx.get(self.well_known_url, timeout=self._timeout, headers=IDP_HEADERS)
            response.raise_for_status()
            payload = response.json()
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Could not reach the identity provider: {exc}") from exc
        except ValueError as exc:
            raise AuthenticationError("Identity provider returned a malformed discovery document") from exc

        # The comparison ignores a trailing `/`, but what we keep is the exact string the IdP
        # announced. The ID token's `iss` arrives unnormalized, so trimming it here would
        # always fail verification for issuers with a trailing `/` (Auth0 etc.).
        advertised_issuer = str(payload.get("issuer", ""))
        if advertised_issuer.rstrip("/") != self._issuer:
            # If these disagree, it becomes unclear which iss the later ID token verification should use
            raise AuthenticationError(
                f"Issuer mismatch: configured {self._issuer!r}, discovery says {advertised_issuer!r}"
            )
        try:
            return OidcDiscovery(
                issuer=advertised_issuer,
                authorization_endpoint=payload["authorization_endpoint"],
                token_endpoint=payload["token_endpoint"],
                jwks_uri=payload["jwks_uri"],
                userinfo_endpoint=payload.get("userinfo_endpoint"),
                end_session_endpoint=payload.get("end_session_endpoint"),
                id_token_signing_alg_values_supported=tuple(
                    payload.get("id_token_signing_alg_values_supported", ())
                ),
                token_endpoint_auth_methods_supported=tuple(
                    payload.get("token_endpoint_auth_methods_supported", ())
                ),
            )
        except KeyError as exc:
            raise AuthenticationError(
                f"Discovery document is missing a required field: {exc.args[0]}"
            ) from exc
