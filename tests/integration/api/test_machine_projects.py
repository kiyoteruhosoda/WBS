"""Tracker のサーバーが機械として、利用者に見えるプロジェクトの道筋を読む（ADR-0056 決定 4）。

トークンの通し方は担当タスクの口と同じ（``test_machine_assigned_tasks``）。ここでは返す中身と、1 本だけ通し方を見る。
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.integration.api.test_auth import (  # noqa: F401 - fixture を借りる
    ISSUER,
    sign_in,
    sso_provider,
)
from tests.integration.api.test_machine_assigned_tasks import (
    AUDIENCE,
    TRACKER_MACHINE,
    _as,
    _machine_claims,
    _make_app,
)

URL = "/api/machine/projects"


@pytest.fixture
def client(database_path, monkeypatch, sso_provider):  # noqa: F811
    sso_provider.machine_tokens.update(
        {"tracker": _machine_claims(), "wrong-audience": _machine_claims(aud="api://nolumiascheduler")}
    )
    app = _make_app(database_path, monkeypatch, sso_provider, audience=AUDIENCE, readers=TRACKER_MACHINE)
    with TestClient(app) as test_client:
        yield test_client


def test_returns_open_project_paths_in_tree_order(client) -> None:
    sign_in(client, "taro-code")
    root = client.post("/api/projects", json={"name": "案件"}).json()
    client.post("/api/projects", json={"name": "設計", "parent_project_id": root["id"]})
    shelved = client.post("/api/projects", json={"name": "古い", "parent_project_id": root["id"]}).json()
    client.post("/api/projects", json={"name": "その下", "parent_project_id": shelved["id"]})
    client.put(f"/api/projects/{shelved['id']}", json={"status": "archived"})
    client.post("/api/projects", json={"name": "別件"})
    client.cookies.clear()

    res = client.get(URL, **_as("tracker"))
    assert res.status_code == 200, res.text
    assert res.json()["paths"] == ["案件", "案件 / 設計", "別件"]


def test_other_peoples_projects_are_not_shown(client) -> None:
    sign_in(client, "taro-code")
    client.post("/api/projects", json={"name": "太郎の"})
    client.cookies.clear()
    sign_in(client, "hanako-code")
    client.cookies.clear()
    res = client.get(URL, **_as("tracker", "hanako"))
    assert res.status_code == 200, res.text
    assert res.json()["paths"] == []


def test_wrong_token_is_refused(client) -> None:
    sign_in(client, "taro-code")
    client.cookies.clear()
    assert client.get(URL, **_as("wrong-audience")).status_code == 401
    assert client.get(URL, params={"issuer": ISSUER, "subject": "taro"}).status_code == 401
