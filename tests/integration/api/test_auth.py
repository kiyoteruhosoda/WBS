"""Check an SSO-enabled app end to end from the HTTP entry point.

Only the IdP is swapped out (overriding ``get_identity_provider``). Everything else (cookie
issuance, session persistence, how authorization applies) goes through the same path as production.
"""

import asyncio
import hashlib
import logging

import httpx
import jwt
import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient

from src.application.ports.identity_provider import AuthorizationRequest, IdentityProvider
from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.federated_identity import FederatedIdentity
from src.domain.value_objects.identity_claims import IdentityClaims
from src.domain.value_objects.logout_notice import LOGOUT_EVENT, InvalidLogoutTokenError
from src.infrastructure.database.session import get_engine
from src.presentation.api.dependencies import get_identity_provider

ISSUER = "https://idp.example.com/realms/wbs"
COOKIE = "wbs_access_token"
# Cookie binding the browser, alive only for one round trip of the authorization code flow
STATE_COOKIE = "sso_login_state"

OIDC_ENV = {
    "AUTH_MODE": "oidc",
    "OIDC_ISSUER": ISSUER,
    "OIDC_CLIENT_ID": "wbs",
    "OIDC_CLIENT_SECRET": "s3cret",
    "OIDC_REDIRECT_URI": "https://wbs.example.com/api/auth/callback",
    "SESSION_SIGNING_KEY": "test-signing-key-test-signing-key-0123",
    # TestClient speaks http, so cookies with Secure are not kept
    "AUTH_COOKIE_SECURE": "false",
}


class FakeIdentityProvider(IdentityProvider):
    """An IdP that returns that person's claims for each authorization code.

    Stop notifications (``logout_token``) are received in the spelling "``<sub>|<sid>|<jti>``".
    **Signature verification is the infrastructure layer's responsibility**, so it is not mocked here.
    """

    def __init__(self) -> None:
        self.codes: dict[str, IdentityClaims] = {
            "taro-code": IdentityClaims(
                identity=FederatedIdentity(issuer=ISSUER, subject="taro"),
                email="taro@example.com",
                email_verified=True,
                display_name="Taro",
                session_id="taro-session",
            ),
            "hanako-code": IdentityClaims(
                identity=FederatedIdentity(issuer=ISSUER, subject="hanako"),
                email="hanako@example.com",
                email_verified=True,
                display_name="Hanako",
                session_id="hanako-session",
            ),
        }
        self.rejected: set[str] = set()
        # The app's access tokens (ADR-0018). Spelling → claims. Signature verification is the infrastructure layer's responsibility
        self.access_tokens: dict[str, dict] = {}
        # Machine tokens (ADR-0056). Spelling → claims (``aud`` is matched against the audience)
        self.machine_tokens: dict[str, dict] = {}

    @property
    def display_name(self) -> str:
        return "Test IdP"

    def build_authorization_request(self, *, state, nonce, code_verifier, silent=False):
        prompt = "&prompt=none" if silent else ""
        return AuthorizationRequest(
            authorization_url=f"{ISSUER}/auth?state={state}&nonce={nonce}{prompt}",
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

    @property
    def federated_issuer(self):
        return ISSUER

    def verify_machine_token(self, token, *, audience):
        claims = self.machine_tokens.get(token)
        if claims is None or claims.get("aud") != audience:
            raise AuthenticationError("Machine token verification failed")
        return claims

    def verify_access_token(self, token):
        claims = self.access_tokens.get(token)
        if claims is None:
            raise AuthenticationError("Access token verification failed")
        return claims

    def verify_logout_token(self, token):
        if token in self.rejected:
            raise InvalidLogoutTokenError("forged")
        subject, _, rest = token.partition("|")
        session_id, _, jti = rest.partition("|")
        claims = {
            "iss": ISSUER,
            "aud": "wbs",
            "jti": jti,
            "events": {LOGOUT_EVENT: {}},
        }
        if subject:
            claims["sub"] = subject
        if session_id:
            claims["sid"] = session_id
        return claims


@pytest.fixture
def sso_provider():
    """Create just one IdP for this test.

    ⚠ **Don't recreate it per request.** If recreated, even when a test sets up "this IdP rejects the next
    token", a different instance is actually called (and does not reject).
    """
    return FakeIdentityProvider()


@pytest.fixture
def sso_client(database_path, monkeypatch, sso_provider):
    for key, value in OIDC_ENV.items():
        monkeypatch.setenv(key, value)
    from main import create_app

    app = create_app(db_path=database_path)
    app.dependency_overrides[get_identity_provider] = lambda: sso_provider
    with TestClient(app) as client:
        yield client


def sign_in(client: TestClient, code: str = "taro-code") -> None:
    """Walk sign-in start → IdP → callback in place of a browser."""
    started = client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    client.get(f"/api/auth/callback?code={code}&state={state}", follow_redirects=False)


def sign_in_alive(client: TestClient) -> bool:
    """Whether the sign-in record that the access token in hand points to still exists (ADR-0071).

    Access tokens don't hit the DB, so they stay valid until they expire. Whether it stopped is judged by the record row (with no row,
    re-issuing settings and logging out don't work, and once it expires the screen asks the IdP again).
    """
    token = client.cookies.get(COOKIE)
    if not token:
        return False
    session_id = jwt.decode(token, options={"verify_signature": False})["rsid"]
    with get_engine().connect() as connection:
        row = connection.execute(
            sa.text("SELECT 1 FROM refresh_sessions WHERE id = :id"), {"id": session_id}
        ).first()
    return row is not None


# ── Publishing settings ─────────────────────────────────────────────────────
def test_config_advertises_sso_without_a_session(sso_client) -> None:
    # This is information for drawing the sign-in screen, so it must be readable without signing in
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


# ── Authorization is applied ────────────────────────────────────────────────
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
        ("get", "/api/actuals/tasks"),
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
    # External monitoring cannot pass authentication
    assert sso_client.get("/api/health").status_code == 200


# ── Sign-in round trip ──────────────────────────────────────────────────────
def test_login_sends_the_browser_to_the_idp(sso_client) -> None:
    response = sso_client.get("/api/auth/login", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith(f"{ISSUER}/auth?")


def test_login_in_single_user_mode_is_not_found(client) -> None:
    # In a deployment with SSO off, this entry point does not exist at all (a 401 would make the screen loop)
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


# ── Callback failures ───────────────────────────────────────────────────────
def test_an_unknown_state_goes_back_to_the_login_page(sso_client) -> None:
    # Pass the browser binding, and check only that the state is unknown to the server
    sso_client.cookies.set(STATE_COOKIE, "never-issued")
    response = sso_client.get(
        "/api/auth/callback?code=taro-code&state=never-issued", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"].startswith("/login?error=authentication_failed")
    assert COOKIE not in response.headers.get("set-cookie", "")


def test_a_callback_from_another_browser_is_refused(sso_client) -> None:
    """Login CSRF: tricking someone else into hitting the callback of a round trip the attacker started.

    The state really exists on the server, so that alone does not stop it. It can only be rejected by matching it
    against the cookie that only the starting browser has.
    """
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    sso_client.cookies.delete(STATE_COOKIE)  # from another browser (= without the cookie)

    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert response.headers["location"].startswith("/login?error=invalid_request")
    assert COOKIE not in response.headers.get("set-cookie", "")
    assert sso_client.get("/api/tasks").status_code == 401


def test_a_login_started_in_another_tab_still_completes(sso_client) -> None:
    # Starting a second sign-in in another tab does not lock out the round trip started first
    first = sso_client.get("/api/auth/login", follow_redirects=False)
    first_state = first.headers["location"].split("state=")[1].split("&")[0]
    sso_client.get("/api/auth/login", follow_redirects=False)

    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={first_state}", follow_redirects=False
    )
    assert response.headers["location"] == "/"
    assert sso_client.get("/api/tasks").status_code == 200


def test_a_state_cannot_be_used_twice(sso_client) -> None:
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    sso_client.get(f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False)

    # The temporary cookie was deleted by the first one. We want to see that it is also used up on the server side,
    # so we put the cookie back and resend.
    sso_client.cookies.set(STATE_COOKIE, state)
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


# ── Silent check (prompt=none, ADR-0062) ────────────────────────────────────
def _start_silently(client: TestClient, next_path: str | None = None) -> str:
    query = "silent=1" + (f"&next={next_path}" if next_path else "")
    started = client.get(f"/api/auth/login?{query}", follow_redirects=False)
    assert started.headers["location"].endswith("&prompt=none")
    return started.headers["location"].split("state=")[1].split("&")[0]


def test_an_ordinary_login_does_not_ask_silently(sso_client) -> None:
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    assert "prompt=none" not in started.headers["location"]


def test_a_silent_check_signs_in_like_an_ordinary_login(sso_client) -> None:
    state = _start_silently(sso_client, "/gantt")
    response = sso_client.get(
        f"/api/auth/callback?code=taro-code&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/gantt"
    assert response.headers["set-cookie"].startswith(f"{COOKIE}=")


@pytest.mark.parametrize(
    "error",
    ["login_required", "consent_required", "interaction_required", "account_selection_required"],
)
def test_not_being_signed_in_to_the_idp_is_not_an_error(sso_client, error) -> None:
    """If the silent check returns "not signed in", go back to the sign-in screen without an error."""
    state = _start_silently(sso_client, "/gantt")
    response = sso_client.get(
        f"/api/auth/callback?error={error}&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/login?sso_silent=1&next=%2Fgantt"


def test_a_silent_check_from_the_top_carries_no_next(sso_client) -> None:
    state = _start_silently(sso_client)
    response = sso_client.get(
        f"/api/auth/callback?error=login_required&state={state}", follow_redirects=False
    )
    assert response.headers["location"] == "/login?sso_silent=1"


def test_other_idp_errors_are_still_shown_after_a_silent_check(sso_client) -> None:
    state = _start_silently(sso_client)
    response = sso_client.get(
        f"/api/auth/callback?error=access_denied&state={state}", follow_redirects=False
    )
    assert response.headers["location"].startswith("/login?error=access_denied")


def test_login_required_on_an_ordinary_login_is_still_an_error(sso_client) -> None:
    started = sso_client.get("/api/auth/login", follow_redirects=False)
    state = started.headers["location"].split("state=")[1].split("&")[0]
    response = sso_client.get(
        f"/api/auth/callback?error=login_required&state={state}", follow_redirects=False
    )
    assert response.headers["location"].startswith("/login?error=login_required")


def test_a_silent_decline_from_another_browser_is_still_an_error(sso_client) -> None:
    """If the round trip was not started by this browser, don't return silently."""
    state = _start_silently(sso_client)
    sso_client.cookies.delete(STATE_COOKIE)
    response = sso_client.get(
        f"/api/auth/callback?error=login_required&state={state}", follow_redirects=False
    )
    assert response.headers["location"].startswith("/login?error=login_required")


# ── Logout ──────────────────────────────────────────────────────────────────
def test_logout_ends_the_session_and_offers_the_idp_logout(sso_client) -> None:
    sign_in(sso_client)
    response = sso_client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json()["end_session_url"] == f"{ISSUER}/logout"
    # The cookie is gone (checking the record is in test_sign_in_sessions).
    assert sso_client.get("/api/tasks").status_code == 401


# ── Other users' data is not reachable by ID ────────────────────────────────
def _sign_in_as_other_user(client: TestClient) -> None:
    client.post("/api/auth/logout")
    client.cookies.clear()
    sign_in(client, "hanako-code")


def test_another_users_task_is_not_found(sso_client) -> None:
    sign_in(sso_client, "taro-code")
    task_id = sso_client.post("/api/tasks", json={"title": "太郎のタスク"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    # 404, not 403. A 403 would reveal that "the ID exists".
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


def test_another_users_category_cannot_be_put_on_a_task(sso_client) -> None:
    """Creating, editing and creating from a memo all reject another user's category as if it did not exist (task #762)."""
    sign_in(sso_client, "taro-code")
    theirs = sso_client.post("/api/categories", json={"name": "太郎の分類"}).json()["id"]

    _sign_in_as_other_user(sso_client)
    mine = sso_client.post("/api/categories", json={"name": "花子の分類"}).json()["id"]
    assert sso_client.post("/api/tasks", json={"title": "x", "category_id": theirs}).status_code == 404

    task = sso_client.post("/api/tasks", json={"title": "x", "category_id": mine}).json()
    assert sso_client.put(f"/api/tasks/{task['id']}", json={"category_id": theirs}).status_code == 404
    # Passes if the category was not re-selected
    assert sso_client.put(f"/api/tasks/{task['id']}", json={"category_id": mine}).status_code == 200

    item = sso_client.post("/api/inbox", json={"title": "メモ"}).json()["id"]
    assert sso_client.post(f"/api/inbox/{item}/convert", json={"category_id": theirs}).status_code == 404
    assert sso_client.post(f"/api/inbox/{item}/convert", json={"category_id": mine}).status_code == 201


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
    # Cannot log actuals on another user's task
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
    # Cannot link from my task to another user's task either
    assert sso_client.post(
        f"/api/tasks/{own}/dependencies", json={"predecessor_task_id": first}
    ).status_code == 404
    assert sso_client.delete(f"/api/tasks/{first}/dependencies/{second}").status_code == 404


@pytest.fixture
def access_lines():
    """Access log lines. ⚠ Creating the app removes the handler, so put this after ``sso_client`` in the test arguments."""
    lines: list[logging.LogRecord] = []

    class Collect(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            lines.append(record)

    handler = Collect()
    logger = logging.getLogger("access")
    logger.disabled = False
    logger.setLevel(logging.INFO)
    logger.addHandler(handler)
    yield lines
    logger.removeHandler(handler)


def _id_hash(user_id: int) -> str:
    return hashlib.sha256(str(user_id).encode()).hexdigest()[:16]


def test_the_access_log_names_the_signed_in_user_only_by_hash(sso_client, access_lines) -> None:
    sign_in(sso_client)
    user_id = sso_client.get("/api/auth/me").json()["user_id"]
    sso_client.cookies.clear()
    assert sso_client.get("/api/auth/me").status_code == 401

    lines = [line for line in access_lines if line.path == "/api/auth/me"]
    assert [(line.status_code, line.user_id_hash) for line in lines] == [
        (200, _id_hash(user_id)),
        (401, None),
    ]
    assert "taro@example.com" not in str(vars(lines[0]))


def test_the_access_log_does_not_mix_users_of_concurrent_requests(sso_client, access_lines) -> None:
    sessions: dict[str | None, str | None] = {None: None}
    for code in ("taro-code", "hanako-code"):
        sign_in(sso_client, code)
        user_id = sso_client.get("/api/auth/me").json()["user_id"]
        sessions[_id_hash(user_id)] = sso_client.cookies[COOKIE]
        sso_client.cookies.clear()

    async def send_all() -> list[tuple[str | None, str]]:
        transport = httpx.ASGITransport(app=sso_client.app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:

            async def send(expected: str | None) -> tuple[str | None, str]:
                session = sessions[expected]
                headers = {"Cookie": f"{COOKIE}={session}"} if session else {}
                response = await client.get("/api/auth/me", headers=headers)
                return expected, response.headers["X-Request-Id"]

            return await asyncio.gather(*(send(expected) for expected in list(sessions) * 20))

    sent = asyncio.run(send_all())

    logged = {line.request_id: line.user_id_hash for line in access_lines}
    assert [logged[request_id] for _, request_id in sent] == [expected for expected, _ in sent]
