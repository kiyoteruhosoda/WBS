"""The port for talking to the external IdP. Implemented in the infrastructure layer."""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from src.domain.value_objects.identity_claims import IdentityClaims


@dataclass(frozen=True)
class AuthorizationRequest:
    """Material for redirecting the user's browser to the authorization endpoint."""

    authorization_url: str
    state: str
    nonce: str
    code_verifier: str


class IdentityProvider(ABC):
    """The IdP as seen from the OIDC Relying Party side.

    Use cases only know this interface. Steps such as discovery, fetching JWKS
    and verifying ID token signatures are all hidden in the implementation.
    """

    @property
    @abstractmethod
    def display_name(self) -> str:
        """IdP name shown on the login screen button."""

    @abstractmethod
    def build_authorization_request(
        self, *, state: str, nonce: str, code_verifier: str, silent: bool = False
    ) -> AuthorizationRequest:
        """Build the authorization request URL.

        If ``silent``, add ``prompt=none`` so the IdP shows no screen (ADR-0062).
        """

    @abstractmethod
    def exchange_code(self, *, code: str, code_verifier: str, nonce: str) -> IdentityClaims:
        """Exchange the authorization code for an ID token, verify it, and return the user's claims.

        Verifying signature, ``iss``, ``aud``, ``exp`` and ``nonce`` is the implementation's job.
        Raises ``AuthenticationError`` if verification fails.
        """

    @abstractmethod
    def build_end_session_url(self, *, post_logout_redirect_uri: str | None) -> str | None:
        """URL that also logs out on the IdP side. None if the IdP does not support it."""

    @abstractmethod
    def verify_logout_token(self, token: str) -> Mapping[str, Any]:
        """Verify a stop notification (``logout_token``) as a JWT and return its claims.

        Only **signature, issuer, audience and expiry** are checked. Whether it is valid
        as a logout notification (``events`` / ``nonce`` / ``sub`` or ``sid`` / ``jti``)
        is decided by the domain (``LogoutNotice``).

        Raises ``InvalidLogoutTokenError`` if it does not pass.
        """

    @abstractmethod
    def verify_machine_token(self, token: str, *, audience: str) -> Mapping[str, Any]:
        """Verify an access token another app's server brought **as a machine** (ADR-0056).

        Only **signature, ``typ`` (``at+jwt``), issuer, audience (``audience``) and expiry** are checked.
        Whether it is a machine token (``sub_type``) and which app (``client_id``) are decided by the use case.

        Raises ``AuthenticationError`` if it does not pass.
        """

    @abstractmethod
    def verify_access_token(self, token: str) -> Mapping[str, Any]:
        """Verify a **user's** access token an app brought with ``Authorization: Bearer``
        (ADR-0018).

        Only **signature, ``typ`` (``at+jwt``), issuer, audience and expiry** are checked. Which apps'
        tokens to accept (``client_id``) and whether to reject machine tokens (``sub_type``)
        are decided by the use case.

        Raises ``AuthenticationError`` if it does not pass.
        """

    @property
    @abstractmethod
    def federated_issuer(self) -> str:
        """Issuer spelling **used to look up the stored identity links**.

        ⚠ Different from the spelling the discovery document claims (the value matched exactly
        against the ID token's ``iss``). A difference of just a trailing ``/`` makes the lookup
        find no rows at all.
        """
