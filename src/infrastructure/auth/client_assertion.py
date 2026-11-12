"""``private_key_jwt`` client authentication assertion (RFC 7523 / OIDC Core §9).

Unlike ``client_secret``, **the private key never leaves the host**. The reason for choosing it is that
the credential itself need not be put in the deployment settings (env vars); the machine identity
(``client_credentials``) uses this method only.

Verification on the IdP side:

- ``client_assertion_type`` must be ``urn:ietf:params:oauth:client-assertion-type:jwt-bearer``
- ``iss`` and ``sub`` are both **the client_id itself** (RFC 7523 §3)
- ``aud`` is the token endpoint (some IdPs also accept the issuer itself)
- **``jti`` is required**. The IdP records it to prevent replay
- ``exp`` must be short. A longer one gains nothing and only widens the replay window
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta

import jwt

ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"

#: Assertion lifetime. ⚠ **Do not make it longer** (it also extends how long the IdP remembers the ``jti``).
LIFETIME_SECONDS = 60


@dataclass(frozen=True)
class ClientAssertionRequest:
    """Input for building one assertion.

    ``client_id`` / ``audience`` / ``kid`` are all ``str``, so passing them positionally lets
    a mix-up slip past type checking. A mix-up gives ``invalid_client`` at the IdP, but
    **it does not say which one was wrong**, so they are carried together from the entry point.
    """

    client_id: str
    audience: str
    private_key_pem: str
    kid: str | None
    now: datetime


def build_client_assertion(request: ClientAssertionRequest) -> str:
    """Build the signed assertion presented to the token endpoint."""
    headers = {"typ": "JWT"}
    if request.kid:
        # With several keys registered, the IdP cannot tell which one to verify with if there is no kid.
        headers["kid"] = request.kid
    return jwt.encode(
        {
            "iss": request.client_id,
            "sub": request.client_id,
            "aud": request.audience,
            # A different value every time. The IdP records it to prevent replay.
            "jti": secrets.token_urlsafe(32),
            "iat": request.now,
            "exp": request.now + timedelta(seconds=LIFETIME_SECONDS),
        },
        request.private_key_pem,
        algorithm="RS256",
        headers=headers,
    )


__all__ = ["ASSERTION_TYPE", "LIFETIME_SECONDS", "ClientAssertionRequest", "build_client_assertion"]
