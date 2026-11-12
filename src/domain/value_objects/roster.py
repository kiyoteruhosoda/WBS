"""The IdP's answer to "who may use this app right now" (input for periodic reconciliation).

A value mirroring exactly what assay's ``GET {issuer}/admin/applications/self/users`` returns.
It carries only ``sub`` and state, no profile (attribute copies are passed on every
sign-in).

⚠ **Unknown states fall back to "leave alone".** If the IdP adds a 4th state one day and we
read "unknown = stop", **everyone stops**. Never stop people on a value we cannot read.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RosterState(Enum):
    """How one person on the roster is treated. Split into 3 by **the action the RP takes**."""

    #: May use it now.
    ALLOWED = "allowed"
    #: Exists on the IdP but cannot use it now. ⚠ **Keep the link** (if restored there, they get in as is).
    BLOCKED = "blocked"
    #: Not in this IdP tenant (= gone). The link may be dropped too.
    UNKNOWN = "unknown"
    #: ⚠ The IdP returned **a value we do not know**, or the person is not on the roster. Do nothing.
    UNRECOGNISED = ""

    @classmethod
    def of(cls, value: str) -> RosterState:
        for state in cls:
            if state is not cls.UNRECOGNISED and state.value == value:
                return state
        return cls.UNRECOGNISED

    @property
    def ends_sessions(self) -> bool:
        """Whether this state means "no longer allow sessions in this app"."""
        return self in {RosterState.BLOCKED, RosterState.UNKNOWN}

    @property
    def drops_the_link(self) -> bool:
        """Whether the link (the ``federated_identities`` row) may also be dropped.

        ⚠ **Do not drop the link of someone who is merely blocked.** Dropping it would mean
        recreating the ``(iss, sub)`` mapping when they are restored there.
        """
        return self is RosterState.UNKNOWN


@dataclass(frozen=True)
class RosterEntry:
    """One roster row."""

    subject: str
    state: RosterState

    @classmethod
    def of(cls, payload: dict[str, object]) -> RosterEntry | None:
        """Build from one element of the response. ``None`` if ``sub`` cannot be read."""
        subject = payload.get("sub")
        state = payload.get("state")
        if not isinstance(subject, str) or not subject:
            return None
        return cls(subject=subject, state=RosterState.of(state if isinstance(state, str) else ""))


@dataclass(frozen=True)
class Roster:
    """The roster received in one query.

    ⚠ **Do not express "could not fetch" with this type.** When fetching fails, stop with an exception and skip
    the reconciliation itself — if it became indistinguishable from an empty roster, an IdP hiccup would stop everyone.
    """

    entries: tuple[RosterEntry, ...]

    def state_of(self, subject: str) -> RosterState:
        """State of that ``sub``. ⚠ **A ``sub`` not on the roster is ``UNRECOGNISED``** (= leave alone)."""
        for entry in self.entries:
            if entry.subject == subject:
                return entry.state
        return RosterState.UNRECOGNISED


__all__ = ["Roster", "RosterEntry", "RosterState"]
