"""PKCE (RFC 7636) code_challenge generation."""

from __future__ import annotations

import base64
import hashlib

CODE_CHALLENGE_METHOD = "S256"


def code_challenge_from_verifier(code_verifier: str) -> str:
    """code_challenge for the ``S256`` method.

    The authorization code comes back from the IdP via the user's browser, so it can leak from
    redirect history or logs. With the challenge registered in advance, someone without the verifier
    cannot exchange the code for tokens even if they obtain it.
    """
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
