"""Plumbing for the periodic reconciliation (asks the IdP for the roster again every hour).

Runs the use case (``ReconcileFederatedUsers``) with this deployment's pieces -- the DB session,
the IdP identity, the issuer spelling. ⚠ **The decisions live in the use case.**
This only owns "when it runs" and "what to log when the roster cannot be fetched".

⚠ **It runs in the web process.** Only web holds the key for talking to the IdP, and there is no other
scheduling infrastructure. With several workers the same cycle runs several times, but reconciliation
gives the same result no matter how often it runs.
"""

from __future__ import annotations

import logging

from sqlalchemy.orm import Session

from src.application.ports.roster_gateway import RosterGateway
from src.application.use_cases.reconcile_federated_users import (
    ReconcileFederatedUsers,
    ReconciliationOutcome,
)
from src.domain.exceptions import (
    IdentityProviderUnavailableError,
    MachineNotBoundToApplicationError,
)
from src.infrastructure.auth.admin_api_token import AdminApiTokenSource
from src.infrastructure.auth.auth_settings import AuthConfigurationError, AuthSettings
from src.infrastructure.auth.http_roster_gateway import HttpRosterGateway
from src.infrastructure.database.session import get_db_session
from src.infrastructure.repositories.identity_link_repository import (
    SqlAlchemyIdentityLinkRepository,
)
from src.infrastructure.repositories.refresh_session_repository import (
    SqlAlchemyRefreshSessionRepository,
)
from src.infrastructure.scheduling.interval_worker import IntervalWorker

logger = logging.getLogger(__name__)

WORKER_NAME = "sso-reconciliation"
#: Interval between checks. ⚠ **Shortening it does not make deactivation faster** (the fast path is the receiving endpoint).
#: This is the second line that catches misses, so balancing it against IdP load is enough.
RECONCILE_INTERVAL_SECONDS = 3600.0
#: Time from startup to the first run. Set so it does not compete with startup work.
FIRST_RUN_DELAY_SECONDS = 60.0

#: Failures that can be skipped. ⚠ **None of them means "everyone left".**
_SKIPPABLE = (IdentityProviderUnavailableError, AuthConfigurationError)


def build_roster_gateway(settings: AuthSettings) -> RosterGateway:
    return HttpRosterGateway(
        AdminApiTokenSource(settings), timeout_seconds=settings.http_timeout_seconds
    )


def reconcile_once(
    settings: AuthSettings, roster: RosterGateway | None = None
) -> ReconciliationOutcome | None:
    """Run one cycle. ``None`` if skipped."""
    if not settings.reconciliation_enabled:
        return None
    session = get_db_session()
    try:
        outcome = _reconcile(session, settings, roster or build_roster_gateway(settings))
    finally:
        session.close()
    if outcome is not None:
        logger.info(
            "SSO reconciliation finished",
            extra={
                "event": "auth.oidc.reconciliation.finished",
                "checked": outcome.checked,
                "revoked": outcome.revoked,
                "unlinked": outcome.unlinked,
                "held_back": outcome.held_back,
            },
        )
    return outcome


def _reconcile(
    session: Session, settings: AuthSettings, roster: RosterGateway
) -> ReconciliationOutcome | None:
    try:
        return ReconcileFederatedUsers(
            # ⚠ **Same spelling** as when linking at login (the receiving endpoint uses it too).
            issuer=settings.issuer,
            links=SqlAlchemyIdentityLinkRepository(session),
            sessions=SqlAlchemyRefreshSessionRepository(session),
            roster=roster,
        ).execute()
    except MachineNotBoundToApplicationError:
        # ⚠ Waiting for setup, not an outage. It comes every hour until bound, so it is not a warning.
        logger.info(
            "the machine identity is not yet bound to the app",
            extra={"event": "auth.oidc.reconciliation.not_bound"},
        )
        return None
    except _SKIPPABLE as error:
        logger.warning(
            "SSO reconciliation skipped",
            extra={
                "event": "auth.oidc.reconciliation.skipped",
                "reason": type(error).__name__,
            },
        )
        return None


def start_reconciliation_worker(settings: AuthSettings) -> IntervalWorker | None:
    """Start the periodic reconciliation (only with ``AUTH_MODE=oidc`` + ``MACHINE_CLIENT_ID``)."""
    if not settings.reconciliation_enabled:
        return None
    worker = IntervalWorker(
        WORKER_NAME,
        lambda: reconcile_once(settings),
        interval_seconds=RECONCILE_INTERVAL_SECONDS,
        first_delay_seconds=FIRST_RUN_DELAY_SECONDS,
    )
    worker.start()
    return worker


__all__ = [
    "FIRST_RUN_DELAY_SECONDS",
    "RECONCILE_INTERVAL_SECONDS",
    "WORKER_NAME",
    "build_roster_gateway",
    "reconcile_once",
    "start_reconciliation_worker",
]
