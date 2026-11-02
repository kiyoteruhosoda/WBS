"""同時に走る更新を、本物のサーバーと本物の DB で確かめる（ADR-0069・fastapitemplate ADR-0092）。

⚠ ``TestClient`` で順番に叩く試験（``test_refresh_sessions``）では、ここで見るものは出ない。

- **SQLite**（stg・本番が使っている）は常に流す
- **MariaDB** は ``REFRESH_TEST_MARIADB_URL`` があるときだけ流す（CI の別ジョブが使い捨ての DB を渡す）。
  ``UPDATE`` の ``SET`` を左から評価するのは MariaDB だけで、順番を間違えると ``previous_jti`` に新しい値が入る
"""

from __future__ import annotations

import logging
import os
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx
import jwt
import pytest
import sqlalchemy as sa
import uvicorn
from alembic import command

from src.domain.entities.refresh_session import REUSE_GRACE
from src.infrastructure.auth.auth_settings import REFRESH_COOKIE_NAME
from src.infrastructure.database.models import Base
from src.infrastructure.database.schema_migration import alembic_config
from src.presentation.api.dependencies import get_identity_provider
from tests.integration.api.test_auth import OIDC_ENV, FakeIdentityProvider

MARIADB_URL = os.getenv("REFRESH_TEST_MARIADB_URL", "")
USE_CASE_LOGGER = "src.application.use_cases.authentication_use_cases"
TABS = 4
ROUNDS = 5


def _prepare_mariadb(url: str) -> None:
    """形だけ作る（ここで見たいのは更新で、古い移行を MariaDB で通すことではない）。"""
    engine = sa.create_engine(url)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(sa.text("DROP TABLE IF EXISTS alembic_version"))
        command.stamp(alembic_config(connection), "head")
    engine.dispose()


@pytest.fixture(params=["sqlite", "mariadb"])
def database_url(request, database_path):
    if request.param == "sqlite":
        return f"sqlite:///{database_path}"
    if not MARIADB_URL:
        pytest.skip("REFRESH_TEST_MARIADB_URL が無い")
    _prepare_mariadb(MARIADB_URL)
    return MARIADB_URL


@pytest.fixture
def server(database_url, monkeypatch):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    from main import create_app

    app = create_app(database_url=database_url)
    provider = FakeIdentityProvider()
    app.dependency_overrides[get_identity_provider] = lambda: provider
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    running = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_config=None))
    thread = threading.Thread(target=running.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 30
    while not running.started:
        assert time.monotonic() < deadline, "server did not start"
        time.sleep(0.05)
    yield f"http://127.0.0.1:{port}"
    running.should_exit = True
    thread.join(timeout=10)


@pytest.fixture
def reused_events(server):
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


def _cookie(response: httpx.Response, name: str) -> str | None:
    for header in response.headers.get_list("set-cookie"):
        if header.startswith(f"{name}="):
            return header.split(";")[0].split("=", 1)[1]
    return None


def _sign_in(base: str) -> str:
    started = httpx.get(f"{base}/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    binding = _cookie(started, "sso_login_state")
    done = httpx.get(
        f"{base}/api/auth/callback?code=taro-code&state={state}",
        headers={"Cookie": f"sso_login_state={binding}"},
        follow_redirects=False,
    )
    token = _cookie(done, REFRESH_COOKIE_NAME)
    assert token, done.headers
    return token


def _tabs_at_once(base: str, tokens: list[str]) -> list[httpx.Response]:
    """全部のタブを同じ瞬間に出す。"""
    gate = threading.Barrier(len(tokens))

    def send(token: str) -> httpx.Response:
        gate.wait()
        return httpx.post(
            f"{base}/api/auth/refresh",
            headers={"Cookie": f"{REFRESH_COOKIE_NAME}={token}"},
            timeout=30,
        )

    with ThreadPoolExecutor(max_workers=len(tokens)) as pool:
        return list(pool.map(send, tokens))


def _jti(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["jti"]


def _session_id(token: str) -> str:
    return jwt.decode(token, options={"verify_signature": False})["rsid"]


def _row(url: str, session_id: str):
    engine = sa.create_engine(url)
    try:
        with engine.connect() as connection:
            return connection.execute(
                sa.text("SELECT * FROM refresh_sessions WHERE id = :id"), {"id": session_id}
            ).mappings().first()
    finally:
        engine.dispose()


def test_tabs_refreshing_at_once_keep_the_sign_in(server, database_url, reused_events) -> None:
    for _ in range(ROUNDS):
        first = _sign_in(server)

        # 4 つのタブが同じ 1 本で同時に更新する。勝つのは 1 つで、負けた側にも 200 を返す
        answers = _tabs_at_once(server, [first] * TABS)
        assert [a.status_code for a in answers] == [200] * TABS
        winners = [token for a in answers if (token := _cookie(a, REFRESH_COOKIE_NAME))]
        assert len(winners) == 1
        second = winners[0]

        # ⚠ **SET の順番。** 直前の 1 本に新しい値が入っていないこと（MariaDB でしか出ない）
        row = _row(database_url, _session_id(first))
        assert row["previous_jti"] == _jti(first)
        assert row["current_jti"] == _jti(second)

        # 新しい Cookie を受け取ったタブとまだのタブが混ざって更新する（振り替えの連鎖。ADR-0092）
        answers = _tabs_at_once(server, [second, first, second, first])
        assert [a.status_code for a in answers] == [200] * TABS
        assert all(_cookie(a, REFRESH_COOKIE_NAME) is None for a in answers)
        row = _row(database_url, _session_id(first))
        assert row["current_jti"] == _jti(second)

    assert reused_events == []


def test_a_token_used_after_the_grace_ends_that_sign_in(server, database_url, reused_events) -> None:
    first = _sign_in(server)
    other_device = _sign_in(server)
    assert _tabs_at_once(server, [first])[0].status_code == 200

    engine = sa.create_engine(database_url)
    with engine.begin() as connection:
        long_ago = _row(database_url, _session_id(first))["rotated_at"] - REUSE_GRACE * 2
        connection.execute(
            sa.text("UPDATE refresh_sessions SET rotated_at = :at WHERE id = :id"),
            {"at": long_ago, "id": _session_id(first)},
        )
    engine.dispose()

    assert _tabs_at_once(server, [first])[0].status_code == 401
    assert _row(database_url, _session_id(first)) is None
    assert len(reused_events) == 1
    assert _tabs_at_once(server, [other_device])[0].status_code == 200
