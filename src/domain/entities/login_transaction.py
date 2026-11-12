"""Entity that remembers one round trip of the authorization code flow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum

from src.domain.exceptions import ValidationError
from src.domain.value_objects.continued_sign_in import ContinuedSignIn
from src.domain.value_objects.redirect_target import RedirectTarget

DEFAULT_LOGIN_TRANSACTION_TTL = timedelta(minutes=10)


class LoginPurpose(StrEnum):
    """What the round trip was started for. There is only one redirect URI, so ``/callback`` picks the cleanup by this."""

    #: Round trip to sign in (button, or the silent check on the sign-in screen)
    LOGIN = "login"
    #: Round trip to continue an expired sign-in without showing a screen (inside a hidden frame. ADR-0071)
    RENEW = "renew"


@dataclass
class LoginTransaction:
    """Temporary data created in ``/auth/login`` and consumed in ``/auth/callback``.

    - ``state``: confirms the callback answers a request we made (CSRF protection)
    - ``nonce``: confirms the ID token was issued for our request (replay protection)
    - ``code_verifier``: PKCE. A stolen authorization code cannot be exchanged

    It is kept on the server rather than in the browser session because the callback may return
    to another tab or process. Always delete it after use (a resend of the same code must not pass).
    """

    state: str
    nonce: str
    code_verifier: str
    redirect_target: RedirectTarget
    created_at: datetime
    expires_at: datetime
    id: int | None = None
    #: Whether this round trip silently checks "already signed in at the IdP" with ``prompt=none`` (ADR-0062).
    #: If true, the IdP returning e.g. ``login_required`` is not a failure.
    silent: bool = False
    purpose: LoginPurpose = LoginPurpose.LOGIN
    #: For a continuing round trip, the sign-in to continue (read from the expired token on the client). ``None`` if unknown
    #: (then it signs in as a new sign-in). ⚠ Exists to match against the person who comes back (ADR-0071)
    continued: ContinuedSignIn | None = None

    @classmethod
    def issue(
        cls,
        *,
        state: str,
        nonce: str,
        code_verifier: str,
        redirect_target: RedirectTarget,
        now: datetime,
        ttl: timedelta = DEFAULT_LOGIN_TRANSACTION_TTL,
        silent: bool = False,
        purpose: LoginPurpose = LoginPurpose.LOGIN,
        continued: ContinuedSignIn | None = None,
    ) -> LoginTransaction:
        if not state or not nonce or not code_verifier:
            raise ValidationError("state, nonce and code_verifier are required")
        return cls(
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
            redirect_target=redirect_target,
            created_at=now,
            expires_at=now + ttl,
            silent=silent,
            purpose=purpose,
            continued=continued,
        )

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
