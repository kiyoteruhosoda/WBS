"""Tracker のサーバーが機械として、利用者の担当タスクを読む（task #539 / ADR-0056）。

IdP は差し替える（署名の検証はインフラ層の試験で見る）。ここで確かめるのは、
**どのトークンを通すか**と、**だれの・どのタスクを返すか**である。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.presentation.api.dependencies import get_identity_provider
from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    ISSUER,
    OIDC_ENV,
    sign_in,
    sso_provider,
)

AUDIENCE = "api://wbs"
TRACKER_MACHINE = "tracker-machine"
URL = "/api/machine/assigned-tasks"


def _machine_claims(**overrides) -> dict:
    claims = {
        "iss": ISSUER,
        "sub": TRACKER_MACHINE,
        "sub_type": "client",
        "aud": AUDIENCE,
        "client_id": TRACKER_MACHINE,
        "exp": 4_000_000_000,
        "iat": 1_700_000_000,
    }
    claims.update(overrides)
    return claims


def _make_app(database_path, monkeypatch, provider, *, audience: str, readers: str):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("MACHINE_AUDIENCE", audience)
    monkeypatch.setenv("MACHINE_READER_CLIENT_IDS", readers)
    from main import create_app

    app = create_app(db_path=database_path)
    app.dependency_overrides[get_identity_provider] = lambda: provider
    app.state.identity_provider = provider
    return app


@pytest.fixture
def client(database_path, monkeypatch, sso_provider):  # noqa: F811
    sso_provider.machine_tokens.update(
        {
            "tracker": _machine_claims(),
            "other-machine": _machine_claims(client_id="someone-else", sub="someone-else"),
            "wrong-audience": _machine_claims(aud="api://nolumiascheduler"),
            # 人のログインのトークン（sub_type が無い）は宛名が合っても通さない
            "person": {k: v for k, v in _machine_claims(sub="taro").items() if k != "sub_type"},
        }
    )
    app = _make_app(database_path, monkeypatch, sso_provider, audience=AUDIENCE, readers=TRACKER_MACHINE)
    with TestClient(app) as test_client:
        yield test_client


def _as(token: str, subject: str = "taro") -> dict:
    return {"headers": {"Authorization": f"Bearer {token}"}, "params": {"issuer": ISSUER, "subject": subject}}


def test_returns_open_tasks_assigned_to_the_user(client) -> None:
    sign_in(client, "taro-code")
    root = client.post("/api/projects", json={"name": "案件"}).json()
    child = client.post("/api/projects", json={"name": "設計", "parent_project_id": root["id"]}).json()
    mine = client.post("/api/tasks", json={"title": "画面", "project_id": child["id"]}).json()
    loose = client.post("/api/tasks", json={"title": "自分だけ"}).json()
    client.post("/api/tasks", json={"title": "だれか", "project_id": root["id"], "assignee_user_id": None})
    done = client.post("/api/tasks", json={"title": "終わった", "project_id": root["id"]}).json()
    for status in ("DOING", "DONE"):
        client.patch(f"/api/tasks/{done['id']}", json={"status": status})
    client.cookies.clear()

    res = client.get(URL, **_as("tracker"))
    assert res.status_code == 200, res.text
    rows = {t["id"]: t for t in res.json()["tasks"]}
    assert set(rows) == {mine["id"], loose["id"]}
    assert rows[mine["id"]]["title"] == "画面"
    assert rows[mine["id"]]["project_path"] == "案件 / 設計"
    assert rows[loose["id"]]["project_path"] is None


def test_each_user_gets_only_their_own_assignments(client) -> None:
    sign_in(client, "taro-code")
    client.post("/api/tasks", json={"title": "太郎の"})
    client.cookies.clear()
    sign_in(client, "hanako-code")
    client.cookies.clear()
    res = client.get(URL, **_as("tracker", "hanako"))
    assert res.status_code == 200, res.text
    assert res.json()["tasks"] == []


@pytest.mark.parametrize("token", ["other-machine", "wrong-audience", "person", "forged"])
def test_tokens_that_are_not_trackers_are_refused(client, token) -> None:
    sign_in(client, "taro-code")
    client.cookies.clear()
    assert client.get(URL, **_as(token)).status_code == 401


def test_a_cookie_alone_is_not_enough(client) -> None:
    sign_in(client, "taro-code")
    assert client.get(URL, params={"issuer": ISSUER, "subject": "taro"}).status_code == 401


def test_someone_who_never_signed_in_is_404(client) -> None:
    assert client.get(URL, **_as("tracker", "nobody")).status_code == 404


def test_closed_unless_configured(database_path, monkeypatch, sso_provider) -> None:  # noqa: F811
    sso_provider.machine_tokens["tracker"] = _machine_claims()
    app = _make_app(database_path, monkeypatch, sso_provider, audience=AUDIENCE, readers="")
    with TestClient(app) as test_client:
        sign_in(test_client, "taro-code")
        test_client.cookies.clear()
        assert test_client.get(URL, **_as("tracker")).status_code == 401
