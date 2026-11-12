"""Implementation that talks to the IdP with the OIDC authorization code flow (with PKCE).

The only implementation of the ``IdentityProvider`` port. Any IdP that publishes a discovery document
(Keycloak / Microsoft Entra ID / Google Workspace / Okta etc.) connects with settings alone.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import urlencode

import httpx
import jwt
from jwt import PyJWKClient

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.logout_notice import InvalidLogoutTokenError
from src.infrastructure.auth.auth_settings import AuthSettings
from src.infrastructure.auth.idp_http import IDP_HEADERS
from src.infrastructure.auth.oidc_discovery import OidcDiscoveryClient
from src.infrastructure.auth.pkce import CODE_CHALLENGE_METHOD, code_challenge_from_verifier

JWKS_CACHE_SECONDS = 300

#: ``typ`` of access tokens (RFC 9068). Keeps ID tokens and deactivation notices from being used as Bearer.
ACCESS_TOKEN_TYPE = "at+jwt"

# Strings accepted as JSON true. Passing `email_verified` through a bare ``bool()`` makes
# ``bool("false")`` True, so the "verified emails only" rule would be bypassed
# only for IdPs that return booleans as strings.
_TRUE_STRINGS = {"true", "1", "yes"}


def _as_bool(value: object, *, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in _TRUE_STRINGS
    return bool(value)


class OidcIdentityProvider(IdentityProvider):
    def __init__(
        self,
        settings: AuthSettings,
        discovery: OidcDiscoveryClient | None = None,
        jwks_client: PyJWKClient | None = None,
    ) -> None:
        self._settings = settings
        self._discovery = discovery or OidcDiscoveryClient(
            settings.issuer, timeout_seconds=settings.http_timeout_seconds
        )
        self._jwks_client = jwks_client

    @property
    def display_name(self) -> str:
        return self._settings.provider_name

    @property
    def federated_issuer(self) -> str:
        """Spelling used to look up stored audiences/identities (with the trailing ``/`` dropped).

        ⚠ ``OidcDiscovery.issuer`` keeps exactly what the IdP announced -- matching against the ID token's ``iss``
        must be an **exact match**. What this returns is the **stored** spelling,
        the same as in the links (``federated_identities``).
        """
        return self._settings.issuer

    # ── Authorization request ──────────────────────────────────────────
    def build_authorization_request(
        self, *, state: str, nonce: str, code_verifier: str, silent: bool = False
    ) -> AuthorizationRequest:
        discovery = self._discovery.get()
        params = {
            "response_type": "code",
            "client_id": self._settings.client_id,
            "redirect_uri": self._settings.redirect_uri,
            "scope": self._settings.scopes,
            "state": state,
            "nonce": nonce,
            "code_challenge": code_challenge_from_verifier(code_verifier),
            "code_challenge_method": CODE_CHALLENGE_METHOD,
        }
        if silent:
            # If signed in, a code comes back as usual; otherwise it returns with ``error=login_required``
            # (OIDC Core §3.1.2.1). The IdP shows no screen (ADR-0062).
            params["prompt"] = "none"
        separator = "&" if "?" in discovery.authorization_endpoint else "?"
        url = f"{discovery.authorization_endpoint}{separator}{urlencode(params)}"
        return AuthorizationRequest(
            authorization_url=url, state=state, nonce=nonce, code_verifier=code_verifier
        )

    # ── Code exchange and ID token verification ────────────────────────
    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> IdentityClaims:
        discovery = self._discovery.get()
        tokens = self._request_tokens(code, code_verifier)
        id_token = tokens.get("id_token")
        if not id_token:
            raise AuthenticationError("Token response did not contain an id_token")

        claims = self._verify_id_token(id_token, nonce=nonce)
        email = claims.get("email")
        email_verified = _as_bool(claims.get("email_verified"))
        display_name = claims.get("name")
        preferred_username = claims.get("preferred_username")

        if email is None and discovery.userinfo_endpoint and tokens.get("access_token"):
            # Some IdPs do not put email in the ID token (depends on requested scopes or settings).
            # It is used for the membership check, so fetch it from userinfo if missing.
            userinfo = self._fetch_userinfo(discovery.userinfo_endpoint, tokens["access_token"])
            if userinfo.get("sub") != claims["sub"]:
                raise AuthenticationError("userinfo response does not match the ID token subject")
            email = userinfo.get("email")
            email_verified = _as_bool(userinfo.get("email_verified"), default=email_verified)
            display_name = display_name or userinfo.get("name")
            preferred_username = preferred_username or userinfo.get("preferred_username")

        session_id = claims.get("sid")
        return IdentityClaims(
            identity=FederatedIdentity(issuer=claims["iss"], subject=claims["sub"]),
            email=email,
            email_verified=email_verified,
            display_name=display_name,
            preferred_username=preferred_username,
            session_id=session_id.strip() if isinstance(session_id, str) and session_id.strip() else None,
        )

    def verify_logout_token(self, token: str) -> Mapping[str, Any]:
        """Verify a deactivation notice (``logout_token``) as a JWT.

        Makes ``exp`` and ``iat`` **required**. The spec does not require ``exp``, but
        without it there is no telling how long the notice is valid, and a notice intercepted once
        could be replayed forever.

        ⚠ **``algorithms`` are only those listed.** Neither ``none`` nor symmetric keys
        (``OidcDiscovery.allowed_algorithms`` narrows them).
        """
        discovery = self._discovery.get()
        try:
            signing_key = self._get_jwks_client(discovery.jwks_uri).get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=discovery.allowed_algorithms,
                audience=self._settings.client_id,
                issuer=discovery.issuer,
                options={"require": ["exp", "iat", "iss", "aud"]},
            )
        except jwt.PyJWTError as exc:
            # ⚠ **Do not return the reason to the sender.** Only log it (this endpoint can be called unauthenticated).
            raise InvalidLogoutTokenError(f"logout_token verification failed: {exc}") from exc
        return claims

    def verify_access_token(self, token: str) -> Mapping[str, Any]:
        """Verify a user's access token coming from an app (ADR-0018).

        ⚠ **The audience is ``{issuer}/userinfo``.** assay does not put an audience (RFC 8707 ``resource``)
        in tokens from human logins (assay ADR-0042 decision 6, kept as is on 2026-09-30).
        Which app it is for is told apart by ``client_id`` (on the use case side).
        """
        return self._verify_jwt_access_token(token, audience=None)

    def verify_machine_token(self, token: str, *, audience: str) -> Mapping[str, Any]:
        """Verify a token another app's server brought as a machine (ADR-0056).

        Machine tokens are obtained with an audience (``resource``), so ``aud`` is this app's audience
        (``MACHINE_AUDIENCE``). ⚠ The audience only says "for whom"; what is allowed is decided by ``client_id``.
        """
        if not audience:
            raise AuthenticationError("Machine tokens are not accepted by this deployment")
        return self._verify_jwt_access_token(token, audience=audience)

    def _verify_jwt_access_token(self, token: str, *, audience: str | None) -> Mapping[str, Any]:
        try:
            discovery = self._discovery.get()
            header = jwt.get_unverified_header(token)
            if str(header.get("typ", "")).lower() != ACCESS_TOKEN_TYPE:
                raise AuthenticationError("Bearer token is not an access token")
            # ⚠ Fetching the key is inside the try too (so broken input or JWKS failures do not turn into 500)
            signing_key = self._get_jwks_client(discovery.jwks_uri).get_signing_key_from_jwt(token)
            claims: dict[str, Any] = jwt.decode(
                token,
                signing_key.key,
                algorithms=discovery.allowed_algorithms,
                audience=audience or f"{discovery.issuer.rstrip('/')}/userinfo",
                issuer=discovery.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"Access token verification failed: {exc}") from exc
        return claims

    def build_end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        try:
            discovery = self._discovery.get()
        except AuthenticationError:
            # Even if the IdP cannot be reached, our own session is already gone.
            # There is no reason to report the logout as failed.
            return None
        if not discovery.end_session_endpoint:
            return None
        params = {"client_id": self._settings.client_id}
        if post_logout_redirect_uri:
            params["post_logout_redirect_uri"] = post_logout_redirect_uri
        separator = "&" if "?" in discovery.end_session_endpoint else "?"
        return f"{discovery.end_session_endpoint}{separator}{urlencode(params)}"

    # ── Internals ──────────────────────────────────────────────────────
    def _request_tokens(self, code: str, code_verifier: str) -> dict:
        discovery = self._discovery.get()
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._settings.redirect_uri,
            "client_id": self._settings.client_id,
            "code_verifier": code_verifier,
        }
        auth: tuple[str, str] | None = None
        if self._settings.client_secret:
            if "client_secret_post" in discovery.token_endpoint_auth_methods_supported:
                data["client_secret"] = self._settings.client_secret
            else:
                # Default is client_secret_basic (also when the IdP announces nothing)
                auth = (self._settings.client_id, self._settings.client_secret)
        try:
            response = httpx.post(
                discovery.token_endpoint,
                data=data,
                auth=auth,
                headers={"Accept": "application/json", **IDP_HEADERS},
                timeout=self._settings.http_timeout_seconds,
            )
        except httpx.HTTPError as exc:
            raise AuthenticationError(f"Could not reach the token endpoint: {exc}") from exc
        if response.status_code >= 400:
            # The IdP error body does not contain client_secret, but details go to the log, not the user
            raise AuthenticationError(
                f"Token endpoint rejected the authorization code (HTTP {response.status_code})"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise AuthenticationError("Token endpoint returned a malformed response") from exc

    def _verify_id_token(self, id_token: str, *, nonce: str) -> dict:
        discovery = self._discovery.get()
        try:
            signing_key = self._get_jwks_client(discovery.jwks_uri).get_signing_key_from_jwt(id_token)
            claims = jwt.decode(
                id_token,
                signing_key.key,
                algorithms=discovery.allowed_algorithms,
                audience=self._settings.client_id,
                issuer=discovery.issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            raise AuthenticationError(f"ID token verification failed: {exc}") from exc

        if claims.get("nonce") != nonce:
            # A token whose nonce does not match was issued for another (or an earlier)
            # login. Stop reuse here.
            raise AuthenticationError("ID token nonce does not match this login request")
        azp = claims.get("azp")
        if azp is not None and azp != self._settings.client_id:
            raise AuthenticationError("ID token was issued for another client")
        return claims

    def _get_jwks_client(self, jwks_uri: str) -> PyJWKClient:
        if self._jwks_client is None:
            self._jwks_client = PyJWKClient(
                jwks_uri,
                cache_keys=True,
                lifespan=JWKS_CACHE_SECONDS,
                timeout=self._settings.http_timeout_seconds,
                # ⚠ Only this goes through urllib. The default UA (`Python-urllib/3.x`) may be
                #   blocked by a WAF, and then **the token exchange still succeeds**
                #   while only signature verification fails. See idp_http.py.
                headers=IDP_HEADERS,
            )
        return self._jwks_client

    def _fetch_userinfo(self, userinfo_endpoint: str, access_token: str) -> dict:
        try:
            response = httpx.get(
                userinfo_endpoint,
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Accept": "application/json",
                    **IDP_HEADERS,
                },
                timeout=self._settings.http_timeout_seconds,
            )
            response.raise_for_status()
            return response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise AuthenticationError(f"Could not read the userinfo endpoint: {exc}") from exc
