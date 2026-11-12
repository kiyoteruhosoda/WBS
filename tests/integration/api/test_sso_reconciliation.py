"""Check the periodic reconciliation through the DB.

Only the IdP's roster is swapped out. ⚠ **What we want to check is "does the session really end"**;
full coverage of the decision itself is in ``tests/unit/application/test_reconcile_federated_users.py``.
"""

import pytest

from src.domain.exceptions import MachineNotBoundToApplicationError
from src.domain.value_objects.roster import Roster, RosterEntry, RosterState
from src.infrastructure.auth.auth_settings import load_auth_settings
from src.presentation.api.reconciliation import reconcile_once
from tests.integration.api.test_auth import (  # noqa: F401 - borrow fixtures
    ISSUER,
    sign_in,
    sign_in_alive,
    sso_client,
    sso_provider,
)


class FakeRoster:
    def __init__(self, states: dict[str, str], *, error: Exception | None = None) -> None:
        self._states = states
        self._error = error

    def fetch(self, *, issuer, subjects):
        if self._error is not None:
            raise self._error
        return Roster(
            entries=tuple(
                RosterEntry(subject=sub, state=RosterState.of(self._states[sub]))
                for sub in subjects
                if sub in self._states
            )
        )


@pytest.fixture
def machine_settings(monkeypatch):
    """Settings for a deployment that has a machine identity. ⚠ Without one, reconciliation does not run."""
    monkeypatch.setenv("MACHINE_CLIENT_ID", "wbs-machine")
    return load_auth_settings()


def test_a_blocked_person_is_signed_out_at_the_next_round(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sign_in_alive(sso_client)

    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "blocked"}))

    assert outcome is not None
    assert (outcome.checked, outcome.revoked, outcome.unlinked) == (1, 1, 0)
    assert not sign_in_alive(sso_client)
    # ⚠ **They can sign in again.** Only the sessions were stopped, not the user
    #   (if they come back at the IdP, nothing needs to be done here).
    sign_in(sso_client)
    assert sign_in_alive(sso_client)


def test_a_person_who_is_gone_loses_the_link_too(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "unknown"}))

    assert outcome is not None
    assert outcome.unlinked == 1
    assert not sign_in_alive(sso_client)


def test_an_allowed_person_keeps_working(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "allowed"}))

    assert outcome is not None
    assert outcome.revoked == 0
    assert sign_in_alive(sso_client)


def test_a_machine_that_is_not_bound_yet_changes_nothing(sso_client, machine_settings) -> None:  # noqa: F811
    """⚠ **Comes here every hour until bound.** This is waiting for setup, not a failure."""
    sign_in(sso_client)
    outcome = reconcile_once(
        machine_settings,
        roster=FakeRoster({}, error=MachineNotBoundToApplicationError("not bound")),
    )

    assert outcome is None
    assert sign_in_alive(sso_client)


def test_without_a_machine_name_the_round_does_not_run(sso_client, monkeypatch) -> None:  # noqa: F811
    """If ``MACHINE_CLIENT_ID`` is empty, there is no one to ask."""
    monkeypatch.delenv("MACHINE_CLIENT_ID", raising=False)
    sign_in(sso_client)

    assert reconcile_once(load_auth_settings(), roster=FakeRoster({"taro": "blocked"})) is None
    assert sign_in_alive(sso_client)


def test_the_issuer_is_the_spelling_the_login_stored(sso_client, machine_settings) -> None:  # noqa: F811
    """⚠ **If the spelling is off by one character, it finds 0 rows and ends as "no anomalies".**

    The setting drops the trailing ``/`` and the binding is stored with the same spelling. Reconciliation looks it up by that spelling.
    """
    sign_in(sso_client)
    assert machine_settings.issuer == ISSUER

    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "blocked"}))
    assert outcome is not None
    assert outcome.checked == 1
