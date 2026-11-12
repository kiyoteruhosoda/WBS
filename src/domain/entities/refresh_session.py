"""Per-sign-in record (ADR-0069 decision 3, ADR-0071).

No row means that sign-in has ended. Logout notices, periodic reconciliation and logout delete the row,
and re-issuing an access token on settings save checks whether the row exists.

⚠ **Refresh tokens are no longer issued** (ADR-0071). An SSO sign-in holds only an access token (5 minutes);
when it expires the screen asks the IdP in a hidden frame and continues. Each continuation extends this row's expiry.
The table name (``refresh_sessions``) is kept from ADR-0069.
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import datetime


def new_identifier() -> str:
    """Record id (the column is 32 characters)."""
    return secrets.token_hex(16)


@dataclass
class RefreshSession:
    id: str
    user_id: int
    expires_at: datetime
    created_at: datetime
    #: The IdP-side sign-in that started (or last continued) this sign-in (the ID token's ``sid``).
    #: ⚠ With an IdP that does not issue ``sid`` this is ``None``, and logout notices can only
    #: act **per user** (all of that person's sign-ins end together).
    idp_session_id: str | None = None

    def is_expired(self, now: datetime) -> bool:
        return now >= self.expires_at
