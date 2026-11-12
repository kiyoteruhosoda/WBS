"""Check, from the HTTP entry point, the round trip that continues an expired sign-in without showing a screen (ADR-0071)."""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src.infrastructure.database.session import get_engine
from src.shared.clock import utcnow
from tests.integration.api.test_auth import (  # noqa: F401 - borrow fixtures
    COOKIE,
    STATE_COOKIE,
    sign_in,
    sign_in_alive,
    sso_client,
    sso_provider,
)

RENEW = "/api/auth/renew"
RESULT = "/api/auth/renewed"
ME = "/api/auth/me"


def _rows() -> list:
    with get_engine().connect() as connection:
        return list(connection.execute(sa.text("SELECT * FROM refresh_sessions")).mappings())


def _start(client: TestClient) -> tuple[str, str]:
    response = client.get(RENEW, follow_redirects=False)
    assert response.status_code == 302
    location = response.headers["location"]
    return location, location.split("state=")[1].split("&")[0]


def _renew(client: TestClient, code: str = "taro-code") -> str:
    """Walk the continue round trip once and return the URL of the result page."""
    _, state = _start(client)
    response = client.get(f"/api/auth/callback?code={code}&state={state}", follow_redirects=False)
    return response.headers["location"]


def _expired(client: TestClient) -> None:
    """The access token's lifetime has passed."""
    later = utcnow() + timedelta(minutes=6)
    patcher = patch("src.presentation.api.dependencies.utcnow", return_value=later)
    patcher.start()
    assert client.get(ME).status_code == 401
    patcher.stop()


def test_the_renewal_asks_the_idp_without_a_screen(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    location, _ = _start(sso_client)
    assert "prompt=none" in location


def test_a_renewal_continues_the_same_sign_in(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    _expired(sso_client)
    before = _rows()
    assert _renew(sso_client) == f"{RESULT}?result=renewed"
    after = _rows()
    assert [r["id"] for r in after] == [before[0]["id"]]
    assert str(after[0]["expires_at"]) >= str(before[0]["expires_at"])
    assert sso_client.get(ME).status_code == 200


def test_a_renewal_sets_no_refresh_token(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    _, state = _start(sso_client)
    response = sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)
    issued = [c.split("=")[0] for c in response.headers.get_list("set-cookie") if "Max-Age=0" not in c]
    assert COOKIE in issued
    assert "wbs_refresh_token" not in issued
    assert "wbs_logout_token" not in issued


def test_not_being_signed_in_to_the_idp_is_declined(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    _, state = _start(sso_client)
    response = sso_client.get(f"/api/auth/callback?error=login_required&state={state}", follow_redirects=False)
    assert response.headers["location"] == f"{RESULT}?result=declined"


def test_someone_else_coming_back_is_declined(sso_client) -> None:  # noqa: F811
    """The user signed in again as someone else at the IdP. The open screen belongs to the previous person, so don't continue."""
    sign_in(sso_client)
    assert _renew(sso_client, code="hanako-code") == f"{RESULT}?result=declined"
    assert len(_rows()) == 1


def test_a_stopped_user_is_declined(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    with get_engine().begin() as connection:
        connection.execute(sa.text("UPDATE users SET is_active = 0"))
    assert _renew(sso_client) == f"{RESULT}?result=declined"


def test_a_broken_round_trip_fails(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert _renew(sso_client, code="unknown-code") == f"{RESULT}?result=failed"


def test_a_round_trip_from_another_browser_fails(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    _, state = _start(sso_client)
    sso_client.cookies.delete(STATE_COOKIE)
    response = sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)
    assert response.headers["location"] == f"{RESULT}?result=failed"


def test_a_stopped_sign_in_starts_anew_when_the_idp_still_says_yes(sso_client) -> None:  # noqa: F811
    """The record was deleted by a stop notification or the periodic reconciliation. If the IdP says still signed in, enter as a new sign-in."""
    sign_in(sso_client)
    with get_engine().begin() as connection:
        connection.execute(sa.text("DELETE FROM refresh_sessions"))
    assert not sign_in_alive(sso_client)
    assert _renew(sso_client) == f"{RESULT}?result=renewed"
    assert sign_in_alive(sso_client)


def test_without_a_token_in_hand_the_renewal_is_a_new_sign_in(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    sso_client.cookies.delete(COOKIE)
    assert _renew(sso_client) == f"{RESULT}?result=renewed"
    assert len(_rows()) == 2


def test_a_renewal_does_not_create_an_account(sso_client) -> None:  # noqa: F811
    """Users are created only when signing in via the button."""
    assert _renew(sso_client) == f"{RESULT}?result=declined"
    with get_engine().connect() as connection:
        count = connection.execute(sa.text("SELECT COUNT(*) FROM users WHERE email = 'taro@example.com'")).scalar()
    assert count == 0


@pytest.mark.parametrize("path", [RENEW, f"{RESULT}?result=renewed"])
def test_only_this_origin_may_frame_the_renewal(sso_client, path) -> None:  # noqa: F811
    response = sso_client.get(path, follow_redirects=False)
    assert response.headers["x-frame-options"] == "SAMEORIGIN"
    assert "frame-ancestors 'self'" in response.headers["content-security-policy"]


def test_the_callback_of_a_renewal_may_be_framed(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    _, state = _start(sso_client)
    response = sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)
    assert response.headers["x-frame-options"] == "SAMEORIGIN"


def test_an_ordinary_login_still_lands_on_the_screen(sso_client) -> None:  # noqa: F811
    started = sso_client.get("/api/auth/login?next=/tasks", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)
    assert response.headers["location"] == "/tasks"


def test_the_renewal_in_single_user_mode_is_not_found(client) -> None:
    """Same as ``/login``. The screen reads it as ``failed`` because the frame does not reach the result page."""
    assert client.get(RENEW, follow_redirects=False).status_code == 404
