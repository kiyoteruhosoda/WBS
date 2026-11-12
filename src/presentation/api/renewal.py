"""Finishing the round trip that silently continues an expired login (ADR-0071; same idea as fastapitemplate ADR-0104).

The SPA opens ``/api/auth/renew`` in a hidden frame (iframe), which round-trips to the IdP with ``prompt=none``.
The return (``/api/auth/callback``) sets the cookie and sends the frame to the **result page**. The SPA reads the frame's
location (same origin) to learn the result -- no script runs inside the frame.

There are three results.

- ``renewed`` -- continued (a new access token cookie was set)
- ``declined`` -- not signed in at the IdP, no consent, a different person signed in, or the user is disabled
- ``failed`` -- the round trip broke (the round trip could not be read, or the IdP could not be reached)

For both ``declined`` and ``failed``, the SPA shows the login screen.

⚠ **Only our own origin may frame these.** The round-trip endpoint and the result page carry ``X-Frame-Options: SAMEORIGIN`` and
``frame-ancestors 'self'``.
"""

from __future__ import annotations

from enum import StrEnum
from urllib.parse import urlencode

from fastapi import Response
from fastapi.responses import HTMLResponse

#: The result page. Keep in sync with the SPA (``frontend/src/auth/silentRenewal.ts``)
RESULT_PATH = "/api/auth/renewed"
RESULT_PARAM = "result"

#: CSP for responses opened inside the frame. The result page loads nothing
_FRAMED_CSP = "default-src 'none'; frame-ancestors 'self'"


class RenewalResult(StrEnum):
    RENEWED = "renewed"
    DECLINED = "declined"
    FAILED = "failed"


def allow_same_origin_framing(response: Response) -> Response:
    """Mark the response as frameable only by our own origin."""
    response.headers["X-Frame-Options"] = "SAMEORIGIN"
    response.headers["Content-Security-Policy"] = _FRAMED_CSP
    return response


def result_location(result: RenewalResult) -> str:
    """URL of the result page."""
    return f"{RESULT_PATH}?{urlencode({RESULT_PARAM: result.value})}"


def result_page() -> HTMLResponse:
    """The result page. No content is needed (the SPA only reads the URL)."""
    response = HTMLResponse("<!doctype html><title>sso</title>", headers={"Cache-Control": "no-store"})
    allow_same_origin_framing(response)
    return response


__all__ = ["RESULT_PATH", "RenewalResult", "allow_same_origin_framing", "result_location", "result_page"]
