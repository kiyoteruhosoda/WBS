"""打刻アプリ（task #167）が assay のアクセストークンで打刻の API を叩く（ADR-0018）。

IdP は差し替える（署名の検証はインフラ層の試験で見る）。ここで確かめるのは、
**どのトークンを誰として通すか**と、**どの口が受け取るか**である。
"""

from datetime import timedelta

import pytest
from fastapi.testclient import TestClient

from src.infrastructure.database.models import UserModel
from src.presentation.api.dependencies import get_db, get_identity_provider
from src.shared.clock import utcnow
from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    ISSUER,
    OIDC_ENV,
    sign_in,
    sso_provider,
)

APP_CLIENT = "wbstimer-app"


def _claims(sub: str = "taro", **overrides) -> dict:
    claims = {
        "iss": ISSUER,
        "sub": sub,
        "aud": f"{ISSUER}/userinfo",
        "client_id": APP_CLIENT,
        "scope": "openid profile email offline_access",
        "exp": 4_000_000_000,
        "iat": 1_700_000_000,
    }
    claims.update(overrides)
    return claims


def _make_client(database_path, monkeypatch, provider, *, app_client_ids: str | None):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    if app_client_ids is None:
        monkeypatch.delenv("APP_CLIENT_IDS", raising=False)
    else:
        monkeypatch.setenv("APP_CLIENT_IDS", app_client_ids)
    from main import create_app

    app = create_app(db_path=database_path)
    app.dependency_overrides[get_identity_provider] = lambda: provider
    # アプリの口は app.state の IdP を使う（SSO が無い配備でも 404 にしないため）
    app.state.identity_provider = provider
    return app


@pytest.fixture
def app_client(database_path, monkeypatch, sso_provider):  # noqa: F811
    sso_provider.access_tokens.update(
        {
            "taro-app": _claims(),
            "hanako-app": _claims("hanako"),
            "stranger-app": _claims("nobody-signed-in-on-the-web"),
            "other-client": _claims(client_id="someone-elses-app"),
            "machine": _claims(sub_type="client"),
        }
    )
    app = _make_client(database_path, monkeypatch, sso_provider, app_client_ids=APP_CLIENT)
    with TestClient(app) as client:
        # Web で 1 度ログインして結び付きを作ってから、Cookie を捨ててアプリとして叩く
        sign_in(client, "taro-code")
        sign_in(client, "hanako-code")
        client.cookies.clear()
        yield client


def bearer(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_the_app_starts_and_stops_with_its_token(app_client) -> None:
    started = app_client.post("/api/time-entries/start", headers=bearer("taro-app"))
    assert started.status_code == 201, started.text
    current = app_client.get("/api/time-entries/current", headers=bearer("taro-app")).json()
    assert current["entry"]["id"] == started.json()["started"]["id"]
    stopped = app_client.post("/api/time-entries/stop", headers=bearer("taro-app"))
    assert stopped.status_code == 200
    assert stopped.json()["stopped"]["id"] == started.json()["started"]["id"]


def test_each_token_acts_as_its_own_user(app_client) -> None:
    app_client.post("/api/time-entries/start", headers=bearer("taro-app"))
    hanako = app_client.get("/api/time-entries/current", headers=bearer("hanako-app")).json()
    assert hanako["entry"] is None


@pytest.mark.parametrize(
    "token",
    ["unknown-token", "other-client", "machine"],
    ids=["unverifiable", "issued-to-another-app", "machine-token"],
)
def test_tokens_that_are_not_ours_are_refused(app_client, token) -> None:
    assert app_client.get("/api/time-entries/current", headers=bearer(token)).status_code == 401


def test_a_person_without_a_web_account_is_refused(app_client) -> None:
    # 利用者を作るのは Web のログインだけ（アプリの口では作らない）
    res = app_client.get("/api/time-entries/current", headers=bearer("stranger-app"))
    assert res.status_code == 403


def test_a_deactivated_user_is_refused(app_client) -> None:
    session = next(app_client.app.dependency_overrides.get(get_db, get_db)())
    try:
        user = session.query(UserModel).filter(UserModel.email == "taro@example.com").one()
        user.is_active = False
        session.commit()
    finally:
        session.close()
    assert app_client.get("/api/time-entries/current", headers=bearer("taro-app")).status_code == 403


def test_a_bad_bearer_does_not_fall_back_to_the_cookie(app_client) -> None:
    sign_in(app_client, "taro-code")
    assert app_client.get("/api/time-entries/current").status_code == 200
    assert app_client.get("/api/time-entries/current", headers=bearer("unknown-token")).status_code == 401
    assert (
        app_client.get("/api/time-entries/current", headers={"Authorization": "Basic eDp5"}).status_code
        == 401
    )


def test_only_the_timer_routes_take_the_app_token(app_client) -> None:
    # 打刻の Start / Stop / 現在の 3 つ（と、ADR-0021 の通知の読み取り。test_calendar_alarms_api）だけ。
    # ほかの口はこれまでどおり Cookie だけ
    assert app_client.get("/api/tasks", headers=bearer("taro-app")).status_code == 401
    assert app_client.get("/api/auth/me", headers=bearer("taro-app")).status_code == 401
    listed = app_client.get(
        "/api/time-entries",
        params={"start": "2000-01-01T00:00:00Z", "end": "2100-01-01T00:00:00Z"},
        headers=bearer("taro-app"),
    )
    assert listed.status_code == 401


def test_the_pc_recorder_sends_auto_entries_with_its_token(app_client) -> None:
    """PC の自動記録（WinTrack、task #379 / ADR-0042）も同じ Bearer の口で区間をまとめて送る。"""
    sign_in(app_client, "taro-code")
    task = app_client.post("/api/tasks", json={"title": "見積書を作る"}).json()["id"]
    app_client.cookies.clear()
    start = (utcnow() - timedelta(hours=2)).replace(microsecond=0)
    span = {
        "client_ref": "3f2b0000-0000-4000-8000-000000000001",
        "started_at": f"{start.isoformat()}Z",
        "ended_at": f"{(start + timedelta(minutes=40)).isoformat()}Z",
        "task_id": task,
    }
    res = app_client.post("/api/time-entries/auto", json={"entries": [span]}, headers=bearer("taro-app"))
    assert res.status_code == 200, res.text
    [result] = res.json()["results"]
    assert (result["status"], result["entry"]["source"]) == ("created", "auto")
    # 他人のトークンでは、その人のタスクとして扱われない
    hanako = app_client.post(
        "/api/time-entries/auto", json={"entries": [span]}, headers=bearer("hanako-app")
    )
    assert hanako.json()["results"][0]["status"] == "invalid"
    unknown = app_client.post(
        "/api/time-entries/auto", json={"entries": [span]}, headers=bearer("unknown-token")
    )
    assert unknown.status_code == 401


def test_the_pc_recorder_reads_rules_and_tasks_with_its_token(app_client) -> None:
    """PC の自動記録（WinTrack、task #381 / ADR-0043）は規則と付け替え先のタスクを Bearer で読む。編集は Cookie だけ。"""
    sign_in(app_client, "taro-code")
    task = app_client.post("/api/tasks", json={"title": "見積書を作る"}).json()["id"]
    rule = app_client.post(
        "/api/tracking-rules", json={"app": "EXCEL.EXE", "task_id": task}
    ).json()["id"]
    app_client.cookies.clear()

    rules = app_client.get("/api/tracking-rules", headers=bearer("taro-app"))
    assert rules.status_code == 200, rules.text
    assert [r["id"] for r in rules.json()["rules"]] == [rule]
    tasks = app_client.get("/api/tracking-rules/tasks", headers=bearer("taro-app"))
    assert [t["id"] for t in tasks.json()["tasks"]] == [task]
    assert app_client.get("/api/tracking-rules", headers=bearer("hanako-app")).json()["rules"] == []

    assert app_client.get("/api/tracking-rules/editor", headers=bearer("taro-app")).status_code == 401
    created = app_client.post(
        "/api/tracking-rules", json={"app": "x.exe", "task_id": task}, headers=bearer("taro-app")
    )
    assert created.status_code == 401
    assert app_client.delete(f"/api/tracking-rules/{rule}", headers=bearer("taro-app")).status_code == 401


def test_the_pc_recorder_reads_its_updates_with_its_token(app_client) -> None:
    """WinTrack（Velopack）は更新の置き場を Bearer で読む（task #384 / ADR-0044）。"""
    from src.application.ports.release_file_store import ReleaseFileStream
    from src.application.use_cases.wintrack_release_use_cases import WinTrackReleases
    from src.presentation.api.dependencies import get_wintrack_releases

    class Store:
        configured = True

        def read(self, name: str, max_bytes: int) -> bytes:
            return b"{}"

        def open(self, name: str) -> ReleaseFileStream:
            return ReleaseFileStream(size=1, chunks=iter([b"x"]))

    app_client.app.dependency_overrides[get_wintrack_releases] = lambda: WinTrackReleases(Store())
    url = "/api/wintrack/releases/releases.win.json"
    assert app_client.get(url, headers=bearer("taro-app")).status_code == 200
    assert app_client.get(url, headers=bearer("unknown-token")).status_code == 401
    assert app_client.get(url).status_code == 401


def test_without_app_client_ids_no_token_is_taken(database_path, monkeypatch, sso_provider) -> None:  # noqa: F811
    sso_provider.access_tokens["taro-app"] = _claims()
    app = _make_client(database_path, monkeypatch, sso_provider, app_client_ids=None)
    with TestClient(app) as client:
        sign_in(client, "taro-code")
        client.cookies.clear()
        assert client.get("/api/time-entries/current", headers=bearer("taro-app")).status_code == 401
