"""IdP へ出ていく HTTP が 4 経路とも User-Agent を名乗ることの確認。

ライブラリ既定の UA は WAF に自動化ツールとして弾かれることがある。とくに
**JWKS だけは PyJWT の ``PyJWKClient`` が urllib で取りに行く**ため、httpx 側に
ヘッダを足しても効かない。この食い違いを突き止めるのは難しい —— トークン交換
までは成功して署名検証だけが落ちるので、画面には「ログインに失敗しました」と
しか出ず、サーバのログにも例外が残らない。

だから「4 経路とも」を機械で見張る。
"""

from datetime import timedelta

import httpx
import pytest

from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.infrastructure.auth import oidc_discovery, oidc_identity_provider
from src.infrastructure.auth.auth_settings import AuthMode, AuthSettings
from src.infrastructure.auth.idp_http import USER_AGENT
from src.infrastructure.auth.oidc_discovery import OidcDiscovery, OidcDiscoveryClient
from src.infrastructure.auth.oidc_identity_provider import OidcIdentityProvider

ISSUER = "https://idp.example.com/realms/wbs"
CLIENT_ID = "wbs"

DISCOVERY = OidcDiscovery(
    issuer=ISSUER,
    authorization_endpoint=f"{ISSUER}/auth",
    token_endpoint=f"{ISSUER}/token",
    jwks_uri=f"{ISSUER}/certs",
    userinfo_endpoint=f"{ISSUER}/userinfo",
    end_session_endpoint=None,
    id_token_signing_alg_values_supported=("RS256",),
    token_endpoint_auth_methods_supported=("none",),
)

DISCOVERY_PAYLOAD = {
    "issuer": ISSUER,
    "authorization_endpoint": DISCOVERY.authorization_endpoint,
    "token_endpoint": DISCOVERY.token_endpoint,
    "jwks_uri": DISCOVERY.jwks_uri,
}


def _settings() -> AuthSettings:
    return AuthSettings(
        mode=AuthMode.OIDC,
        issuer=ISSUER,
        client_id=CLIENT_ID,
        client_secret=None,
        redirect_uri="https://wbs.example.com/api/auth/callback",
        scopes="openid email profile",
        provider_name="Test IdP",
        post_logout_redirect_uri=None,
        http_timeout_seconds=5.0,
        session_ttl=timedelta(hours=12),
        cookie_name="wbs_session",
        cookie_secure=True,
        cookie_samesite="lax",
        policy=ProvisioningPolicy(),
    )


class StubDiscoveryClient(OidcDiscoveryClient):
    def __init__(self) -> None:
        super().__init__(ISSUER)

    def get(self) -> OidcDiscovery:
        return DISCOVERY


def _response(payload: dict) -> httpx.Response:
    return httpx.Response(200, json=payload, request=httpx.Request("GET", ISSUER))


# ── 1. ディスカバリ（httpx.get） ────────────────────────────────────────────
def test_the_discovery_document_is_fetched_with_a_user_agent(monkeypatch) -> None:
    seen: dict = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return _response(DISCOVERY_PAYLOAD)

    monkeypatch.setattr(oidc_discovery.httpx, "get", fake_get)
    OidcDiscoveryClient(ISSUER).get()
    assert seen["headers"]["User-Agent"] == USER_AGENT


# ── 2. トークンエンドポイント（httpx.post） ─────────────────────────────────
def test_the_token_request_carries_a_user_agent(monkeypatch) -> None:
    seen: dict = {}

    def fake_post(url, **kwargs):
        seen.update(kwargs)
        return _response({"access_token": "at"})

    monkeypatch.setattr(oidc_identity_provider.httpx, "post", fake_post)
    provider = OidcIdentityProvider(_settings(), discovery=StubDiscoveryClient())
    provider._request_tokens("code", "verifier")
    assert seen["headers"]["User-Agent"] == USER_AGENT
    # Accept を上書きしていないこと（ヘッダを足したつもりで潰す事故を止める）
    assert seen["headers"]["Accept"] == "application/json"


# ── 3. userinfo（httpx.get） ───────────────────────────────────────────────
def test_the_userinfo_request_carries_a_user_agent(monkeypatch) -> None:
    seen: dict = {}

    def fake_get(url, **kwargs):
        seen.update(kwargs)
        return _response({"sub": "abc"})

    monkeypatch.setattr(oidc_identity_provider.httpx, "get", fake_get)
    provider = OidcIdentityProvider(_settings(), discovery=StubDiscoveryClient())
    provider._fetch_userinfo(DISCOVERY.userinfo_endpoint, "at")
    assert seen["headers"]["User-Agent"] == USER_AGENT
    # Bearer を落としていないこと
    assert seen["headers"]["Authorization"] == "Bearer at"


# ── 4. JWKS（PyJWKClient ＝ urllib。ここが抜けやすい） ──────────────────────
def test_the_jwks_client_is_built_with_a_user_agent(monkeypatch) -> None:
    """httpx ではなく urllib を使う唯一の経路。同じヘッダが渡ること。"""
    seen: dict = {}

    class SpyJwksClient:
        def __init__(self, uri, **kwargs):
            seen["uri"] = uri
            seen.update(kwargs)

    monkeypatch.setattr(oidc_identity_provider, "PyJWKClient", SpyJwksClient)
    provider = OidcIdentityProvider(_settings(), discovery=StubDiscoveryClient())
    provider._get_jwks_client(DISCOVERY.jwks_uri)
    assert seen["uri"] == DISCOVERY.jwks_uri
    assert seen["headers"]["User-Agent"] == USER_AGENT


# ── 弾かれたときに何が起きるかの記録 ────────────────────────────────────────
def test_a_rejected_jwks_fetch_surfaces_as_an_authentication_error(monkeypatch) -> None:
    """UA を弾かれると「トークンは通ったのに署名検証だけ落ちる」形になる。

    この経路が ``AuthenticationError`` になることを固定しておく。画面には
    「ログインに失敗しました」としか出ないので、切り分けはログと突き合わせに
    なる —— せめて例外の型は変えない。
    """
    import jwt

    class RefusingJwksClient:
        def __init__(self, uri, **kwargs):
            pass

        def get_signing_key_from_jwt(self, token):
            raise jwt.PyJWKClientConnectionError(
                'Fail to fetch data from the url, err: "HTTP Error 403: Forbidden"'
            )

    monkeypatch.setattr(oidc_identity_provider, "PyJWKClient", RefusingJwksClient)
    provider = OidcIdentityProvider(_settings(), discovery=StubDiscoveryClient())
    with pytest.raises(AuthenticationError, match="ID token verification failed"):
        provider._verify_id_token("not.a.real.token", nonce="n")
