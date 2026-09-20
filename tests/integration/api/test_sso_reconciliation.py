"""定期照合を、DB を通して確かめる。

IdP の名簿だけを差し替える。⚠ **確かめたいのは「本当にセッションが終わるか」**で、
判断そのものの網羅は ``tests/unit/application/test_reconcile_federated_users.py``。
"""

import pytest

from src.domain.exceptions import MachineNotBoundToApplicationError
from src.domain.value_objects.roster import Roster, RosterEntry, RosterState
from src.infrastructure.auth.auth_settings import load_auth_settings
from src.presentation.api.reconciliation import reconcile_once
from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    ISSUER,
    sign_in,
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
    """機械としての名乗りがある配備の設定。⚠ 名乗りが無ければ照合は走らない。"""
    monkeypatch.setenv("MACHINE_CLIENT_ID", "wbs-machine")
    return load_auth_settings()


def test_a_blocked_person_is_signed_out_at_the_next_round(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200

    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "blocked"}))

    assert outcome is not None
    assert (outcome.checked, outcome.revoked, outcome.unlinked) == (1, 1, 0)
    assert sso_client.get("/api/auth/me").status_code == 401
    # ⚠ **入り直せる。** 止めたのはセッションだけで、利用者は止めていない
    #   （IdP で戻れば、こちらでは何もしなくてよい）。
    sign_in(sso_client)
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_person_who_is_gone_loses_the_link_too(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "unknown"}))

    assert outcome is not None
    assert outcome.unlinked == 1
    assert sso_client.get("/api/auth/me").status_code == 401


def test_an_allowed_person_keeps_working(sso_client, machine_settings) -> None:  # noqa: F811
    sign_in(sso_client)
    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "allowed"}))

    assert outcome is not None
    assert outcome.revoked == 0
    assert sso_client.get("/api/auth/me").status_code == 200


def test_a_machine_that_is_not_bound_yet_changes_nothing(sso_client, machine_settings) -> None:  # noqa: F811
    """⚠ **結び付けるまで毎時ここへ来る。** 準備待ちであって障害ではない。"""
    sign_in(sso_client)
    outcome = reconcile_once(
        machine_settings,
        roster=FakeRoster({}, error=MachineNotBoundToApplicationError("not bound")),
    )

    assert outcome is None
    assert sso_client.get("/api/auth/me").status_code == 200


def test_without_a_machine_name_the_round_does_not_run(sso_client, monkeypatch) -> None:  # noqa: F811
    """``MACHINE_CLIENT_ID`` が空なら、聞きに行く相手が決まらない。"""
    monkeypatch.delenv("MACHINE_CLIENT_ID", raising=False)
    sign_in(sso_client)

    assert reconcile_once(load_auth_settings(), roster=FakeRoster({"taro": "blocked"})) is None
    assert sso_client.get("/api/auth/me").status_code == 200


def test_the_issuer_is_the_spelling_the_login_stored(sso_client, machine_settings) -> None:  # noqa: F811
    """⚠ **綴りが 1 文字ずれると 0 件になり、「異常なし」で終わる。**

    設定は末尾の ``/`` を落とし、結び付きも同じ綴りで保存する。照合はその綴りで引く。
    """
    sign_in(sso_client)
    assert machine_settings.issuer == ISSUER

    outcome = reconcile_once(machine_settings, roster=FakeRoster({"taro": "blocked"}))
    assert outcome is not None
    assert outcome.checked == 1
