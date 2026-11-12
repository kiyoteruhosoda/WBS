"""Path of the screen to return to after sign-in."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REDIRECT_PATH = "/"


@dataclass(frozen=True)
class RedirectTarget:
    """A return target guaranteed to be a relative path within this site.

    Users can set ``?next=`` freely, so putting it into ``Location`` as is would
    let someone redirect to an external site right after IdP sign-in (open redirect).
    Every received value must pass through here; any form that could point outside falls back to the default path.
    """

    path: str

    @classmethod
    def parse(cls, raw: str | None) -> RedirectTarget:
        if not raw:
            return cls(DEFAULT_REDIRECT_PATH)
        candidate = raw.strip()
        if not candidate.startswith("/"):
            # Absolute URLs, scheme-relative URLs and bare relative paths can all point outside
            return cls(DEFAULT_REDIRECT_PATH)
        if candidate.startswith("//") or candidate.startswith("/\\"):
            # `//evil.example` resolves to an external host as a scheme-relative URL
            return cls(DEFAULT_REDIRECT_PATH)
        if "\\" in candidate or "\n" in candidate or "\r" in candidate:
            # Some browsers read a backslash as `/`. Newlines enable header splitting.
            return cls(DEFAULT_REDIRECT_PATH)
        return cls(candidate)

    def __str__(self) -> str:
        return self.path
