"""SSO を有効にしたアプリを、HTTP の入口から通しで確かめる。

IdP だけは差し替える（``get_identity_provider`` を上書き）。それ以外——Cookie の
発行、セッションの永続化、認可の掛かり方——は本番と同じ経路を通す。
"""

import pytest
from fastapi.testclient import TestClient

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.presentation.api.dependencies import get_identity_provider

ISSUER = "https://idp.example.com/realms/wbs"
COOKIE = "wbs_session"

OIDC_ENV = {
    "AUTH_MODE": "oidc",
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "wbs",
    "OIDC_CLIENT_SECRET": "s3cret",
    "OIDC_REDIRECT_URI": "https://wbs.example.com/api/auth/callback",
    # TestClient は http で話すので、Secure 付きの Cookie は保持されない
    "AUTH_COOKIE_SECURE": "false",
}


class FakeIdentityProvider(IdentityProvider):
    """認可コードごとに、その人のクレームを返す IdP。"""

    def __init__(self) -> None:
        self.codes: dict[str, IdentityClaims] = {
            "taro-code": IdentityClaims(
                identity=FederatedIdentity(issuer=ISSUER, subject="taro"),
                email="taro@example.com",
                email_verified=True,
                display_name="Taro",
            ),
            "hanako-code": IdentityClaims(
                identity=FederatedIdentity(issuer=ISSUER, subject="hanako"),
                email="hanako@example.com",
                email_verified=True,
                display_name="Hanako",
            ),
        }

    @property
    def display_name(self) -> str:
        return "Test IdP"

    def build_authorization_request(self, *, state, nonce, code_verifier):
        return AuthorizationRequest(
            authorization_url=f"{ISSUER}/auth?state={state}&nonce={nonce}",
            state=state,
            nonce=nonce,
            code_verifier=code_verifier,
        )

    def exchange_code(self, *, code, code_verifier, nonce):
        claims = self.codes.get(code)
        if claims is None:
            raise AuthenticationError("Unknown authorization code")
        return claims

    def build_end_session_url(self, *, post_logout_redirect_uri):
        return f"{ISSUER}/logout"


@pytest.fixture
def sso_client(tmp_path, monkeypatch):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    from main import create_app

    app = create_app(db_path=str(tmp_path / "sso.db"))
    app.dependency_overrides[get_identity_provider] = lambda: FakeIdentityProvider()
    with TestClient(app) as client:
        yield client


def sign_in(client: TestClient, code: str = "taro-code") -> None:
    """ログイン開始 → IdP → コールバック、をブラウザの代わりになぞる。"""
    started = client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    client.get(f"/api/auth/callback?code={code}&state={state}", follow_redirects=False)


# ── 設定の公開 ─────────────────────────────────────────────────────────────
def test_config_advertises_sso_without_a_session(sso_client) -> None:
    # ログイン画面を描くための情報なので、未ログインでも読めなければならない
    response = sso_client.get("/api/auth/config")
    assert response.status_code == 200
    assert response.json() == {
        "mode": "oidc",
        "sso_enabled": True,
        "provider_name": "SSO",
        "login_path": "/api/auth/login",
    }


def test_config_reports_single_user_mode(client) -> None:
    body = client.get("/api/auth/config").json()
    assert body["mode"] == "single_user"
    assert body["sso_enabled"] is False


# ── 認可が掛かっていること ─────────────────────────────────────────────────
@pytest.mark.parametrize(
    "method,path",
    [
        ("get", "/api/tasks"),
        ("get", "/api/settings"),
        ("get", "/api/dashboard/kpi"),
        ("get", "/api/inbox"),
        ("get", "/api/categories"),
        ("get", "/api/milestones"),
        ("get", "/api/gantt"),
        ("get", "/api/reviews/weekly"),
        ("get", "/api/auth/me"),
        ("post", "/api/tasks"),
    ],
)
def test_without_a_session_the_api_is_closed(sso_client, method, path) -> None:
    response = sso_client.request(method, path, json={})
    assert response.status_code == 401


def test_a_forged_cookie_is_refused(sso_client) -> None:
    sso_client.cookies.set(COOKIE, "made-up-token")
    assert sso_client.get("/api/tasks").status_code == 401


def test_health_stays_open(sso_client) -> None:
    # 外形監視は認証を通せない
    assert sso_client.get("/api/health").status_code == 200


# ── ログインの往復 ─────────────────────────────────────────────────────────
def test_login_sends_the_browser_to_the_idp(sso_client) -> None:
    response = sso_client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{ISSUER}/auth?")


def test_login_in_single_user_mode_is_not_found(client) -> None:
    # SSO を切っている配備では、この入口自体が無い（401 だと画面が往復する）
    assert client.get("/api/auth/login", follow_redirects=False).status_code == 404


def test_the_callback_issues_a_session_cookie(sso_client) -> None:
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]

    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/"
    set_cookie = response.headers["set-cookie"]
    assert set_cookie.startswith(f"{COOKIE}=")
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Path=/" in set_cookie


def test_the_callback_returns_to_the_requested_page(sso_client) -> None:
    started = sso_client.get("/api/auth/login?next=/gantt", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/gantt"


def test_an_external_next_is_not_followed(sso_client) -> None:
    started = sso_client.get(
        "/api/auth/login?next=https://evil.example/steal", follow_redirects=False
    )
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/"


def test_after_signing_in_the_api_answers(sso_client) -> None:
    sign_in(sso_client)
    me = sso_client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["email"] == "taro@example.com"
    assert me.json()["display_name"] == "Taro"
    assert sso_client.get("/api/tasks").status_code == 200


def test_the_signed_in_user_is_the_owner_of_new_data(sso_client) -> None:
    sign_in(sso_client)
    created = sso_client.post("/api/tasks", json={"title": "SSO で作ったタスク"})
    assert created.status_code == 201
    assert [t["title"] for t in sso_client.get("/api/tasks").json()] == ["SSO で作ったタスク"]


def test_each_user_sees_only_their_own_tasks(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    sso_client.post("/api/tasks", json={"title": "太郎のタスク"})
    sso_client.post("/api/auth/logout")
    sso_client.cookies.clear()

    sign_in(sso_client, "hanako-code")
    sso_client.post("/api/tasks", json={"title": "花子のタスク"})
    assert [t["title"] for t in sso_client.get("/api/tasks").json()] == ["花子のタスク"]


def test_settings_belong_to_the_signed_in_user(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    sso_client.put("/api/settings", json={"language": "en"})
    sso_client.post("/api/auth/logout")
    sso_client.cookies.clear()

    sign_in(sso_client, "hanako-code")
    assert sso_client.get("/api/settings").json()["language"] == "ja"


def test_signing_in_twice_keeps_the_same_account(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    first = sso_client.get("/api/auth/me").json()["user_id"]
    sso_client.post("/api/auth/logout")
    sso_client.cookies.clear()

    sign_in(sso_client, "taro-code")
    assert sso_client.get("/api/auth/me").json()["user_id"] == first


# ── コールバックの失敗 ─────────────────────────────────────────────────────
def test_an_unknown_state_goes_back_to_the_login_page(sso_client) -> None:
    response = sso_client.get(
        "/api/auth/callback?code=taro-code&state=never-issued", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login?error=authentication_failed")
    assert COOKIE not in response.headers.get("set-cookie", "")


def test_a_state_cannot_be_used_twice(sso_client) -> None:
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)

    replay = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert replay.headers["location"].startswith("/login?error=authentication_failed")


def test_an_error_from_the_idp_goes_back_to_the_login_page(sso_client) -> None:
    response = sso_client.get(
        "/api/auth/callback?error=access_denied&error_description=User+said+no",
        follow_redirects=False,
    )
    assert response.headers["location"].startswith("/login?error=access_denied")


def test_a_callback_without_a_code_goes_back_to_the_login_page(sso_client) -> None:
    response = sso_client.get("/api/auth/callback", follow_redirects=False)
    assert response.headers["location"].startswith("/login?error=invalid_request")


# ── ログアウト ─────────────────────────────────────────────────────────────
def test_logout_ends_the_session_and_offers_the_idp_logout(sso_client) -> None:
    sign_in(sso_client)
    response = sso_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["end_session_url"] == f"{ISSUER}/logout"
    # Cookie を消しても、サーバ側のセッションが残っていれば戻れてしまう。
    # 消えていることを、Cookie を送り直して確かめる。
    assert sso_client.get("/api/tasks").status_code == 401


# ── 他人のデータに ID で届かないこと ───────────────────────────────────────
def _sign_in_as_other_user(client: TestClient) -> None:
    client.post("/api/auth/logout")
    client.cookies.clear()
    sign_in(client, "hanako-code")


def test_another_users_task_is_not_found(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    task_id = sso_client.post("/api/tasks", json={"title": "太郎のタスク"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    # 403 ではなく 404。403 だと「その ID は存在する」ことを教えてしまう。
    assert sso_client.get(f"/api/tasks/{task_id}").status_code == 404
    assert sso_client.put(f"/api/tasks/{task_id}", json={"title": "乗っ取り"}).status_code == 404
    assert sso_client.delete(f"/api/tasks/{task_id}").status_code == 404


def test_another_users_category_is_not_found(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    category_id = sso_client.post("/api/categories", json={"name": "太郎の分類"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    assert sso_client.get(f"/api/categories/{category_id}").status_code == 404
    assert sso_client.put(f"/api/categories/{category_id}", json={"name": "改名"}).status_code == 404
    assert sso_client.delete(f"/api/categories/{category_id}").status_code == 404


def test_another_users_milestone_is_not_found(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    milestone_id = sso_client.post("/api/milestones", json={"name": "太郎の節目"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    assert sso_client.get(f"/api/milestones/{milestone_id}").status_code == 404
    assert sso_client.put(f"/api/milestones/{milestone_id}", json={"name": "改名"}).status_code == 404
    assert sso_client.delete(f"/api/milestones/{milestone_id}").status_code == 404


def test_another_users_inbox_item_is_not_found(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    item_id = sso_client.post("/api/inbox", json={"title": "太郎のメモ"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    assert sso_client.delete(f"/api/inbox/{item_id}").status_code == 404
    assert sso_client.post(f"/api/inbox/{item_id}/convert", json={}).status_code == 404


def test_work_logs_on_another_users_task_are_not_reachable(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    task_id = sso_client.post("/api/tasks", json={"title": "太郎のタスク"}).json()["id"]
    work_log_id = sso_client.post(
        "/api/work-logs", json={"task_id": task_id, "work_date": "2026-08-30", "hours": 1.5}
    ).json()["id"]

    _sign_in_as_other_user(sso_client)
    assert sso_client.get("/api/work-logs", params={"task_id": task_id}).status_code == 404
    assert sso_client.get(f"/api/work-logs/{work_log_id}").status_code == 404
    assert sso_client.put(f"/api/work-logs/{work_log_id}", json={"hours": 99}).status_code == 404
    assert sso_client.delete(f"/api/work-logs/{work_log_id}").status_code == 404
    # 他人のタスクに実績を積めない
    posted = sso_client.post(
        "/api/work-logs", json={"task_id": task_id, "work_date": "2026-08-30", "hours": 1}
    )
    assert posted.status_code == 404


def test_dependencies_on_another_users_task_are_not_reachable(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    first = sso_client.post("/api/tasks", json={"title": "太郎1"}).json()["id"]
    second = sso_client.post("/api/tasks", json={"title": "太郎2"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    own = sso_client.post("/api/tasks", json={"title": "花子1"}).json()["id"]
    assert sso_client.get(f"/api/tasks/{first}/dependencies").status_code == 404
    assert sso_client.post(
        f"/api/tasks/{first}/dependencies", json={"predecessor_task_id": second}
    ).status_code == 404
    # 自分のタスクから他人のタスクへも繋げない
    assert sso_client.post(
        f"/api/tasks/{own}/dependencies", json={"predecessor_task_id": first}
    ).status_code == 404
    assert sso_client.delete(f"/api/tasks/{first}/dependencies/{second}").status_code == 404
