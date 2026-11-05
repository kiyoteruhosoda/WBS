"""ログインの控えと Cookie を HTTP の入口から確かめる（ADR-0069・ADR-0071）。"""

from __future__ import annotations

from datetime import timedelta
from unittest.mock import patch

import sqlalchemy as sa
from fastapi.testclient import TestClient

from src.infrastructure.auth.auth_settings import LOGOUT_COOKIE_NAME, REFRESH_COOKIE_NAME
from src.infrastructure.database.session import get_engine
from src.shared.clock import utcnow
from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    COOKIE,
    sign_in,
    sign_in_alive,
    sso_client,
    sso_provider,
)

LOGOUT = "/api/auth/logout"
ME = "/api/auth/me"
THIRTY_DAYS = 30 * 24 * 3600


def _rows() -> list:
    with get_engine().connect() as connection:
        return list(connection.execute(sa.text("SELECT * FROM refresh_sessions")).mappings())


def _another_device(client: TestClient) -> TestClient:
    other = TestClient(client.app)
    sign_in(other)
    return other


def _callback_cookies(client: TestClient) -> dict[str, str]:
    started = client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)
    return {c.split("=")[0]: c for c in response.headers.get_list("set-cookie")}


def test_signing_in_sets_only_the_access_token_and_keeps_it_for_thirty_days(sso_client) -> None:  # noqa: F811
    """⚠ リフレッシュトークンもログアウトの札も出さない（ADR-0071）。以前のものが残っていれば落とす。"""
    cookies = _callback_cookies(sso_client)
    assert "HttpOnly" in cookies[COOKIE]
    assert "SameSite=lax" in cookies[COOKIE]
    assert f"Max-Age={THIRTY_DAYS}" in cookies[COOKIE]
    for old in (REFRESH_COOKIE_NAME, LOGOUT_COOKIE_NAME):
        assert "Max-Age=0" in cookies[old] or 'expires=Thu, 01 Jan 1970' in cookies[old]


def test_the_refresh_endpoint_is_gone(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sso_client.post("/api/auth/refresh").status_code in (404, 405)


def test_signing_in_keeps_one_row_per_sign_in(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["idp_session_id"] == "taro-session"
    assert set(rows[0]) == {"id", "user_id", "expires_at", "created_at", "idp_session_id"}


def test_the_access_token_is_read_without_the_database(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    statements: list[str] = []

    def remember(_conn, _cursor, statement, *_rest) -> None:
        statements.append(statement)

    sa.event.listen(get_engine(), "before_cursor_execute", remember)
    try:
        assert sso_client.get(ME).status_code == 200
    finally:
        sa.event.remove(get_engine(), "before_cursor_execute", remember)
    assert statements == []


def test_the_access_token_ends_at_its_lifetime(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    later = utcnow() + timedelta(minutes=6)
    with patch("src.presentation.api.dependencies.utcnow", return_value=later):
        assert sso_client.get(ME).status_code == 401


def test_logging_out_ends_this_sign_in_and_clears_the_cookies(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sso_client.post(LOGOUT).status_code == 200
    assert _rows() == []
    assert not sso_client.cookies.get(COOKIE)


def test_logging_out_after_the_access_token_expired_still_ends_the_sign_in(sso_client) -> None:  # noqa: F811
    """ログアウトの札はもう無い。切れたアクセストークンからでも、どのログインかは読める（ADR-0071）。"""
    sign_in(sso_client)
    later = utcnow() + timedelta(hours=3)
    with patch("src.presentation.api.routers.auth.utcnow", return_value=later):
        assert sso_client.post(LOGOUT).status_code == 200
    assert _rows() == []


def test_logging_out_leaves_other_devices_signed_in(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    other = _another_device(sso_client)
    sso_client.post(LOGOUT)
    assert len(_rows()) == 1
    assert sign_in_alive(other)


def test_logging_out_without_a_session_is_fine(sso_client) -> None:  # noqa: F811
    assert sso_client.post(LOGOUT).status_code == 200


def test_a_forged_access_token_does_not_end_someone_elses_sign_in(sso_client) -> None:  # noqa: F811
    other = _another_device(sso_client)
    sso_client.cookies.set(COOKIE, "made-up-token")
    sso_client.post(LOGOUT)
    assert sign_in_alive(other)


def test_a_cookie_from_before_the_tokens_means_one_more_sign_in(sso_client) -> None:  # noqa: F811
    """配った直後に残っている古い Cookie。500 にせず、ログインし直せば入れる。"""
    sso_client.cookies.set(COOKIE, "old-opaque-session-token")
    assert sso_client.get(ME).status_code == 401
    sign_in(sso_client)
    assert sso_client.get(ME).status_code == 200


def test_saving_settings_reissues_the_access_token_with_the_new_values(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    assert sso_client.put("/api/settings", json={"timezone": "America/New_York"}).status_code == 200
    assert sso_client.get(ME).json()["timezone"] == "America/New_York"


def test_saving_settings_after_the_sign_in_ended_does_not_mint_a_token(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    with get_engine().begin() as connection:
        connection.execute(sa.text("DELETE FROM refresh_sessions"))
    response = sso_client.put("/api/settings", json={"language": "en"})
    assert response.status_code == 200
    assert not any(c.startswith(f"{COOKIE}=") for c in response.headers.get_list("set-cookie"))
