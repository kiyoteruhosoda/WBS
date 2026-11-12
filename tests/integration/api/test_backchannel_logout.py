"""Whether stop propagation (IdP → this app) works.

Communication with the IdP is stopped by swapping the provider. What we want to check here is that **a delivered notification
actually ends the sessions**, and that it does not get the scope wrong.

Whether it stopped is judged by **the sign-in record being gone**. Access tokens don't hit the DB, so the one in hand stays valid
until it expires. Once it expires, the screen asks the IdP again, the IdP answers "not signed in", and that is the end (ADR-0071).
"""

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.test_auth import (  # noqa: F401 - borrow fixtures
    COOKIE,
    sign_in,
    sign_in_alive,
    sso_client,
    sso_provider,
)

LOGOUT = "/api/auth/backchannel-logout"


def post_logout(client: TestClient, logout_token: str) -> int:
    """The route the IdP's server calls. **It carries neither a cookie nor credentials.**"""
    return client.post(LOGOUT, data={"logout_token": logout_token}).status_code


def test_a_stop_from_the_idp_ends_the_session(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sign_in_alive(sso_client)

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200

    # ⚠ **The record row is gone** (re-issuing settings and logging out no longer work).
    assert not sign_in_alive(sso_client)


def test_a_stop_without_a_sid_ends_every_session_of_that_user(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert post_logout(sso_client, "taro||delivery-1") == 200
    assert not sign_in_alive(sso_client)


def test_a_stop_for_another_person_leaves_this_session_alone(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert post_logout(sso_client, "hanako|hanako-session|delivery-1") == 200
    assert sign_in_alive(sso_client)


def test_a_stop_for_another_login_of_the_same_person_leaves_this_one_alone(sso_client) -> None:  # noqa: F811
    """⚠ **A notification that also knows the ``sid`` ends only that device's sign-in.**

    If this doesn't work, signing out on another device logs out every device.
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|another-device|delivery-1") == 200
    assert sign_in_alive(sso_client)


def test_a_replayed_notice_does_not_end_a_session_started_afterwards(sso_client) -> None:  # noqa: F811
    """⚠ **A resend does not delete the session created after signing in again.**

    The sender uses the same ``jti`` even on resends. If we applied it every time instead of rejecting it, a resend
    right after being restored at the IdP and signing in again would drop that **new session**.
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200
    assert not sign_in_alive(sso_client)

    sign_in(sso_client)  # Restored at the IdP and signed in again
    assert sign_in_alive(sso_client)

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200  # resend with the same jti
    assert sign_in_alive(sso_client)


def test_a_new_notice_for_the_same_login_still_lands(sso_client) -> None:  # noqa: F811
    """⚠ **Resends are rejected by ``jti``, not because "it is the second time".**

    When stopped, restored and stopped again, it arrives with a new ``jti``. Rejecting that too
    would make the second stop ineffective.
    """
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200
    sign_in(sso_client)
    assert post_logout(sso_client, "taro|taro-session|delivery-2") == 200
    assert not sign_in_alive(sso_client)


@pytest.mark.parametrize(
    "body",
    [
        {},  # no logout_token
        {"logout_token": ""},  # empty
        {"logout_token": ["a|b|c", "d|e|f"]},  # two values
    ],
    ids=["missing", "empty", "two"],
)
def test_a_malformed_body_is_refused(sso_client, body) -> None:  # noqa: F811
    assert sso_client.post(LOGOUT, data=body).status_code == 400


def test_a_forged_token_is_refused_and_leaves_the_session(sso_client, sso_provider) -> None:  # noqa: F811
    """⚠ **The signature is the sender's entire proof.** Anything that fails gets a 400 without a reason."""
    sign_in(sso_client)
    # A spelling that passes as a shape (sub / sid / jti present). The only reason to refuse is the signature.
    sso_provider.rejected.add("taro|taro-session|delivery-1")

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 400
    assert sign_in_alive(sso_client)


def test_the_notice_needs_no_cookie(sso_client) -> None:  # noqa: F811
    """⚠ The sender is the IdP's server, not a browser (no cookie attached)."""
    sign_in(sso_client)
    cookie = sso_client.cookies.get(COOKIE)
    assert cookie  # Precondition: signed in
    sso_client.cookies.clear()

    assert post_logout(sso_client, "taro|taro-session|delivery-1") == 200

    sso_client.cookies.set(COOKIE, cookie)
    assert not sign_in_alive(sso_client)

