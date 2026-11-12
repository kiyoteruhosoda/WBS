"""Sign-in continued without showing a screen (ADR-0071).

"Whose sign-in, and which one", read from an expired access token left on the client. ⚠ **This is not authentication.**
It is used only to carry over that record when **the same person** comes back from the IdP.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ContinuedSignIn:
    user_id: int
    #: Record of the continued sign-in (``refresh_sessions.id``)
    session_id: str
