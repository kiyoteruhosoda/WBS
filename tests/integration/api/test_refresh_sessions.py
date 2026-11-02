"""ログインの控えとリフレッシュトークンの振り替えを HTTP の入口から確かめる（ADR-0069）。"""

from __future__ import annotations

import logging
from datetime import timedelta
from unittest.mock import patch

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src.domain.entities.refresh_session import REUSE_GRACE
from src.infrastructure.auth.auth_settings import LOGOUT_COOKIE_NAME, REFRESH_COOKIE_NAME
from src.infrastructure.database.session import get_engine
from src.shared.clock import utcnow
from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    COOKIE,
    sign_in,
    sso_client,
    sso_provider,
)

REFRESH = "/api/auth/refresh"
LOGOUT = "/api/auth/logout"
ME = "/api/auth/me"
USE_CASE_LOGGER = "src.application.use_cases.authentication_use_cases"


@pytest.fixture
def reused_events():
    """使い回しの記録。⚠ アプリを作るとログの持ち手が消えるので、試験の引数では ``sso_client`` の後に書く。"""
    events: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            if getattr(record, "event", None) == "refresh_token.reused":
                events.append(record)

    handler = Collect()
    logger = logging.getLogger(USE_CASE_LOGGER)
    logger.disabled = False
    logger.addHandler(handler)
    yield events
    logger.removeHandler(handler)


def _refresh_cookie(client: TestClient) -> str:
    return client.cookies.get(REFRESH_COOKIE_NAME, path=REFRESH) or ""


def _present(client: TestClient, token: str) -> int:
    """手元に控えたトークンを更新の口へ出す。"""
    client.cookies.delete(REFRESH_COOKIE_NAME, path=REFRESH)
    client.cookies.set(REFRESH_COOKIE_NAME, token, path=REFRESH)
    return client.post(REFRESH).status_code


def _after_the_grace():
    moment = utcnow() + REUSE_GRACE + timedelta(seconds=1)
    return patch("src.presentation.api.routers.auth.utcnow", return_value=moment)


def _rows() -> list:
    with get_engine().connect() as connection:
        return list(connection.execute(sa.text("SELECT * FROM refresh_sessions")).mappings())


def _another_device(client: TestClient) -> TestClient:
    other = TestClient(client.app)
    sign_in(other)
    return other


def test_signing_in_sets_three_http_only_cookies_on_their_own_paths(sso_client) -> None:  # noqa: F811
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)

    cookies = {c.split("=")[0]: c for c in response.headers.get_list("set-cookie")}
    assert "Path=/;" in cookies[COOKIE] or cookies[COOKIE].endswith("Path=/")
    assert f"Path={REFRESH}" in cookies[REFRESH_COOKIE_NAME]
    assert f"Path={LOGOUT}" in cookies[LOGOUT_COOKIE_NAME]
    for name in (COOKIE, REFRESH_COOKIE_NAME, LOGOUT_COOKIE_NAME):
        assert "HttpOnly" in cookies[name]
        assert "SameSite=lax" in cookies[name]


def test_the_tokens_are_not_in_the_response_body(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    body = sso_client.post(REFRESH).json()
    assert set(body) == {"expires_in"}


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


def test_after_the_access_token_is_gone_a_refresh_brings_it_back(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    sso_client.cookies.delete(COOKIE)
    assert sso_client.get(ME).status_code == 401
    assert sso_client.post(REFRESH).status_code == 200
    assert sso_client.get(ME).status_code == 200


def test_rotating_extends_the_row(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    before = _rows()[0]["expires_at"]
    with _after_the_grace():
        assert sso_client.post(REFRESH).status_code == 200
    assert str(_rows()[0]["expires_at"]) > str(before)


def test_the_row_follows_the_rotation(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    sso_client.post(REFRESH)
    rows = _rows()
    assert len(rows) == 1
    assert rows[0]["previous_jti"] is not None
    assert rows[0]["current_jti"] != rows[0]["previous_jti"]


def test_the_rotation_sets_the_previous_token_first(sso_client) -> None:  # noqa: F811
    """MariaDB は SET を左から評価する。current_jti が先だと previous_jti に新しい値が入る（SQLite では起きない）。"""
    sign_in(sso_client)
    statements: list[str] = []

    def remember(_conn, _cursor, statement, *_rest) -> None:
        statements.append(statement)

    sa.event.listen(get_engine(), "before_cursor_execute", remember)
    try:
        assert sso_client.post(REFRESH).status_code == 200
    finally:
        sa.event.remove(get_engine(), "before_cursor_execute", remember)
    rotation = next(s for s in statements if s.startswith("UPDATE refresh_sessions"))
    assert rotation.index("previous_jti=") < rotation.index("current_jti=")


def test_a_refresh_racing_from_another_tab_does_not_sign_out(sso_client) -> None:  # noqa: F811
    """負けた側はアクセストークンだけを受け取り、Cookie は勝った側のものが残る。"""
    sign_in(sso_client)
    first = _refresh_cookie(sso_client)
    assert sso_client.post(REFRESH).status_code == 200
    winner = _refresh_cookie(sso_client)
    assert winner != first

    sso_client.cookies.delete(REFRESH_COOKIE_NAME, path=REFRESH)
    sso_client.cookies.set(REFRESH_COOKIE_NAME, first, path=REFRESH)
    raced = sso_client.post(REFRESH)
    assert raced.status_code == 200
    issued = raced.headers.get_list("set-cookie")
    assert not any(cookie.startswith(f"{REFRESH_COOKIE_NAME}=") for cookie in issued)
    assert any(cookie.startswith(f"{COOKIE}=") for cookie in issued)
    assert _present(sso_client, winner) == 200


def test_a_chain_of_refreshes_from_several_tabs_does_not_sign_out(sso_client, reused_events) -> None:  # noqa: F811
    """1 つ目のタブが振り替えた直後に 2 つ目が新しい 1 本で更新しても、3 つ目の古い 1 本は使い回しにならない。"""
    sign_in(sso_client)
    first = _refresh_cookie(sso_client)
    assert sso_client.post(REFRESH).status_code == 200
    second = _refresh_cookie(sso_client)

    # 振り替えたばかりなので、今の 1 本でも振り替えない
    assert sso_client.post(REFRESH).status_code == 200
    assert _refresh_cookie(sso_client) == second

    assert _present(sso_client, first) == 200
    assert _present(sso_client, second) == 200
    assert reused_events == []


def test_the_current_token_rotates_again_after_the_grace(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    sso_client.post(REFRESH)
    second = _refresh_cookie(sso_client)
    with _after_the_grace():
        assert sso_client.post(REFRESH).status_code == 200
    assert _refresh_cookie(sso_client) != second


def test_a_used_token_is_refused_and_ends_only_that_sign_in(sso_client, reused_events) -> None:  # noqa: F811
    sign_in(sso_client)
    other = _another_device(sso_client)
    used = _refresh_cookie(sso_client)
    assert sso_client.post(REFRESH).status_code == 200
    latest = _refresh_cookie(sso_client)

    with _after_the_grace():
        assert _present(sso_client, used) == 401
    # 盗まれた 1 本で、今の 1 本も止まる（どちらが本人か分からない）
    assert _present(sso_client, latest) == 401
    assert len(_rows()) == 1
    assert other.post(REFRESH).status_code == 200
    assert len(reused_events) == 1
    # 記録に利用者の番号やメールをそのまま載せない
    assert "taro@example.com" not in str(vars(reused_events[0]))


def test_logging_out_ends_the_refresh_token_taken_before(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    taken = _refresh_cookie(sso_client)
    assert sso_client.post(LOGOUT).status_code == 200
    assert _rows() == []
    assert _present(sso_client, taken) == 401


def test_logging_out_clears_the_cookies(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    sso_client.post(LOGOUT)
    assert not sso_client.cookies.get(COOKIE)
    assert not sso_client.cookies.get(LOGOUT_COOKIE_NAME, path=LOGOUT)
    assert not _refresh_cookie(sso_client)


def test_logging_out_leaves_other_devices_signed_in(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    other = _another_device(sso_client)
    sso_client.post(LOGOUT)
    assert len(_rows()) == 1
    assert other.post(REFRESH).status_code == 200


def test_logging_out_without_a_session_is_fine(sso_client) -> None:  # noqa: F811
    assert sso_client.post(LOGOUT).status_code == 200


def test_a_logout_token_cannot_refresh(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    logout_token = sso_client.cookies.get(LOGOUT_COOKIE_NAME, path=LOGOUT) or ""
    assert logout_token
    assert _present(sso_client, logout_token) == 401


def test_an_access_token_cannot_refresh_and_a_refresh_token_cannot_open_the_api(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    access = sso_client.cookies.get(COOKIE) or ""
    refresh = _refresh_cookie(sso_client)
    assert _present(sso_client, access) == 401
    sso_client.cookies.delete(COOKIE)
    sso_client.cookies.set(COOKIE, refresh)
    assert sso_client.get(ME).status_code == 401


def test_a_stopped_user_cannot_refresh_but_keeps_the_token_in_hand_until_it_ends(sso_client) -> None:  # noqa: F811
    sign_in(sso_client)
    with get_engine().begin() as connection:
        connection.execute(sa.text("UPDATE users SET is_active = 0"))
    assert sso_client.get(ME).status_code == 200  # DB を引かない。上限はアクセストークンの寿命
    assert sso_client.post(REFRESH).status_code == 401
    assert _rows() == []


def test_a_cookie_from_before_the_tokens_means_one_more_sign_in(sso_client) -> None:  # noqa: F811
    """配った直後に残っている古いセッションの Cookie。500 にせず、ログインし直せば入れる。"""
    sso_client.cookies.set("wbs_session", "old-opaque-session-token")
    sso_client.cookies.set(COOKIE, "old-opaque-session-token")
    assert sso_client.get(ME).status_code == 401
    assert sso_client.post(REFRESH).status_code == 401
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


def test_refresh_is_refused_without_a_cookie(client) -> None:
    """``AUTH_MODE=single_user`` は更新の口を使わない。500 にも 404 にもせず 401。"""
    assert client.post(REFRESH).status_code == 401
    assert client.get(ME).status_code in (200, 401)
