"""Ask the IdP again and stop sessions of people who can no longer use the app (periodic reconciliation).

The stop notification endpoint **only works when a notification arrives**. If the IdP could not send it,
we were down, or the destination was not registered — the miss simply remains.
This is the second line: every hour it asks the IdP for the roster again and fills the gap.

What it stops is the same as the endpoint — **only this app's sessions**; the user itself
(``users.is_active``) is not touched. Without matching scopes, what gets stopped would differ between
"when it arrived" and "when it was missed", which is confusing.

⚠ **Do nothing when the roster cannot be fetched.** Do not confuse failing to fetch the roster with
the roster being empty — confusing them would stop everyone just because the IdP is unwell.

⚠ **Write it so that running it any number of times gives the same result.** The same job runs once per worker,
at the same time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, replace

from src.application.ports.roster_gateway import RosterGateway
from src.domain.entities.identity_link import IdentityLink
from src.domain.repositories.identity_link_repository import IdentityLinkRepository
from src.domain.repositories.refresh_session_repository import RefreshSessionRepository
from src.domain.value_objects.roster import Roster, RosterState

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReconciliationOutcome:
    """What happened in one reconciliation run (counts for logging and tests)."""

    checked: int = 0
    #: Number of people whose sessions were ended. ⚠ **People who already had none are not counted** (back to 0 every hour).
    revoked: int = 0
    unlinked: int = 0
    #: ⚠ Whether it **held back because everyone came back ``unknown``**. When true, nothing was changed.
    held_back: bool = False


@dataclass(frozen=True)
class ReconcileFederatedUsers:
    #: ⚠ The issuer with **the same spelling** as when linked at login. Off by one character and nothing matches,
    #: so it ends as "no problems" without checking anything.
    issuer: str
    links: IdentityLinkRepository
    sessions: RefreshSessionRepository
    roster: RosterGateway

    def execute(self) -> ReconciliationOutcome:
        links = self.links.list_for_issuer(self.issuer)
        if not links:
            return ReconciliationOutcome()
        # ⚠ Ask by name. A candidate list cannot tell "not there (gone)".
        answers = self.roster.fetch(
            issuer=self.issuer, subjects=tuple(link.subject for link in links)
        )
        outcome = ReconciliationOutcome(checked=len(links))
        if _everyone_is_unknown(links, answers):
            # ⚠ A tenant mix-up or the app being reassigned can also return this shape.
            #   Stop before unlinking everyone.
            logger.warning(
                "Skipped reconciliation because the IdP roster returned unknown for everyone",
                extra={
                    "event": "auth.oidc.reconciliation.everyone_unknown",
                    "checked": len(links),
                },
            )
            return replace(outcome, held_back=True)
        for link in links:
            outcome = self._apply(link, answers.state_of(link.subject), outcome)
        return outcome

    def _apply(
        self, link: IdentityLink, state: RosterState, outcome: ReconciliationOutcome
    ) -> ReconciliationOutcome:
        """Apply the result for one person. ⚠ **Explicitly return the untouched case too.**"""
        if not state.ends_sessions:
            return outcome
        ended = self.sessions.delete_for_identity(link.identity)
        if ended:
            logger.info(
                "Ended sessions of a person deactivated at the IdP",
                extra={
                    "event": "auth.oidc.reconciliation.revoked",
                    "user_id": link.user_id,
                    "ended_sessions": ended,
                },
            )
            outcome = replace(outcome, revoked=outcome.revoked + 1)
        if not state.drops_the_link:
            return outcome
        # Not there = the other end of the link no longer exists. Keeping the row would connect to someone else
        # if the same ``sub`` were reused for another person (it is promised not to be reused, but there is no reason to keep it).
        self.links.unlink(link.id)
        logger.info(
            "Unlinked a person no longer present at the IdP",
            extra={"event": "auth.oidc.reconciliation.unlinked", "user_id": link.user_id},
        )
        return replace(outcome, unlinked=outcome.unlinked + 1)


def _everyone_is_unknown(links: list[IdentityLink], answers: Roster) -> bool:
    """Whether there are 2 or more links and everyone came back ``unknown``.

    With only one, it cannot be told apart from "that one person is gone", so it is handled normally.
    """
    if len(links) < 2:
        return False
    return all(answers.state_of(link.subject) is RosterState.UNKNOWN for link in links)


__all__ = ["ReconcileFederatedUsers", "ReconciliationOutcome"]
