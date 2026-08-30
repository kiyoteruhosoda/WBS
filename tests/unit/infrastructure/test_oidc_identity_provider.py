"""ID トークン検証まわり。本物の RSA 鍵で署名して、通す／弾くを確かめる。"""

from datetime import UTC, datetime, timedelta

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from jwt import PyJWKClient
from jwt.algorithms import RSAAlgorithm

from src.domain.exceptions import AuthenticationError
from src.domain.value_objects.provisioning_policy import ProvisioningPolicy
from src.infrastructure.auth.auth_settings import AuthMode, AuthSettings
from src.infrastructure.auth.oidc_discovery import OidcDiscovery, OidcDiscoveryClient
from src.infrastructure.auth.oidc_identity_provider import OidcIdentityProvider

ISSUER = "https://idp.example.com/realms/wbs"
CLIENT_ID = "wbs"
KEY_ID = "test-key"
NONCE = "nonce-value"


@pytest.fixture(scope="module")
def rsa_key():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(scope="module")
def jwks(rsa_key):
    public_jwk = RSAAlgorithm.to_jwk(rsa_key.public_key(), as_dict=True)
    public_jwk.update({"kid": KEY_ID, "use": "sig", "alg": "RS256"})
    return {"keys": [public_jwk]}


def _settings(**overrides) -> AuthSettings:
    values = {
        "mode": AuthMode.OIDC,
        "issuer": ISSUER,
        "client_id": CLIENT_ID,
        "client_secret": "s3cret",
        "redirect_uri": "https://wbs.example.com/api/auth/callback",
        "scopes": "openid email profile",
        "provider_name": "Test IdP",
        "post_logout_redirect_uri": None,
        "http_timeout_seconds": 5.0,
        "session_ttl": timedelta(hours=12),
        "cookie_name": "wbs_session",
        "cookie_secure": True,
        "cookie_samesite": "lax",
        "policy": ProvisioningPolicy(),
    }
    values.update(overrides)
    return AuthSettings(**values)


DISCOVERY = OidcDiscovery(
    issuer=ISSUER,
    authorization_endpoint=f"{ISSUER}/protocol/openid-connect/auth",
    token_endpoint=f"{ISSUER}/protocol/openid-connect/token",
    jwks_uri=f"{ISSUER}/protocol/openid-connect/certs",
    userinfo_endpoint=f"{ISSUER}/protocol/openid-connect/userinfo",
    end_session_endpoint=f"{ISSUER}/protocol/openid-connect/logout",
    id_token_signing_alg_values_supported=("RS256",),
    token_endpoint_auth_methods_supported=("client_secret_basic",),
)


class StubDiscoveryClient(OidcDiscoveryClient):
    def __init__(self, document: OidcDiscovery = DISCOVERY) -> None:
        super().__init__(ISSUER)
        self._document = document

    def get(self) -> OidcDiscovery:
        return self._document


class OfflineJwksClient(PyJWKClient):
    """JWKS をネットワークではなく手元の辞書から返す。"""

    def __init__(self, jwk_set: dict) -> None:
        super().__init__(DISCOVERY.jwks_uri, cache_keys=False, cache_jwk_set=False)
        self._jwk_set = jwk_set

    def fetch_data(self):
        return self._jwk_set


def _provider(jwks, **settings_overrides) -> OidcIdentityProvider:
    return OidcIdentityProvider(
        _settings(**settings_overrides),
        discovery=StubDiscoveryClient(),
        jwks_client=OfflineJwksClient(jwks),
    )


def _id_token(rsa_key, **claim_overrides) -> str:
    now = datetime.now(UTC)
    claims = {
        "iss": ISSUER,
        "sub": "abc-123",
        "aud": CLIENT_ID,
        "exp": now + timedelta(minutes=5),
        "iat": now,
        "nonce": NONCE,
        "email": "taro@example.com",
        "email_verified": True,
        "name": "Taro",
    }
    claims.update(claim_overrides)
    return jwt.encode(claims, rsa_key, algorithm="RS256", headers={"kid": KEY_ID})


# ── 認可リクエストの組み立て ───────────────────────────────────────────────
def test_authorization_url_carries_pkce_and_the_one_time_values(jwks) -> None:
    request = _provider(jwks).build_authorization_request(
        state="st", nonce="no", code_verifier="v" * 43
    )
    url = request.authorization_url
    assert url.startswith(DISCOVERY.authorization_endpoint + "?")
    assert "response_type=code" in url
    assert "code_challenge_method=S256" in url
    assert "state=st" in url and "nonce=no" in url
    # verifier そのものは URL に出さない
    assert "v" * 43 not in url


def test_query_string_on_the_authorization_endpoint_is_preserved(jwks) -> None:
    document = OidcDiscovery(**{
        **DISCOVERY.__dict__,
        "authorization_endpoint": f"{ISSUER}/auth?tenant=main",
    })
    provider = OidcIdentityProvider(
        _settings(), discovery=StubDiscoveryClient(document), jwks_client=OfflineJwksClient(jwks)
    )
    url = provider.build_authorization_request(
        state="st", nonce="no", code_verifier="v"
    ).authorization_url
    assert "?tenant=main&" in url


# ── ID トークンの検証 ─────────────────────────────────────────────────────
def test_a_valid_token_yields_the_identity(rsa_key, jwks) -> None:
    claims = _provider(jwks)._verify_id_token(_id_token(rsa_key), nonce=NONCE)
    assert claims["sub"] == "abc-123"


def test_a_token_signed_by_another_key_is_refused(jwks) -> None:
    other_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    forged = _id_token(other_key)
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(forged, nonce=NONCE)


def test_an_unsigned_token_is_refused(rsa_key, jwks) -> None:
    # alg=none への降格。許可アルゴリズムを絞っているので通ってはいけない。
    unsigned = jwt.encode(
        {"iss": ISSUER, "sub": "abc-123", "aud": CLIENT_ID, "nonce": NONCE},
        key=None,
        algorithm="none",
        headers={"kid": KEY_ID},
    )
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(unsigned, nonce=NONCE)


def test_an_expired_token_is_refused(rsa_key, jwks) -> None:
    expired = _id_token(rsa_key, exp=datetime.now(UTC) - timedelta(seconds=1))
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(expired, nonce=NONCE)


def test_a_token_for_another_audience_is_refused(rsa_key, jwks) -> None:
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(_id_token(rsa_key, aud="another-app"), nonce=NONCE)


def test_a_token_from_another_issuer_is_refused(rsa_key, jwks) -> None:
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(_id_token(rsa_key, iss="https://evil.example"), nonce=NONCE)


def test_a_token_with_a_different_nonce_is_refused(rsa_key, jwks) -> None:
    # 別のログイン向けに出た（あるいは以前の）トークンの使い回しを止める
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(_id_token(rsa_key, nonce="someone-elses"), nonce=NONCE)


def test_a_token_without_a_nonce_is_refused(rsa_key, jwks) -> None:
    token = _id_token(rsa_key)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop("nonce")
    without_nonce = jwt.encode(payload, rsa_key, algorithm="RS256", headers={"kid": KEY_ID})
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(without_nonce, nonce=NONCE)


def test_a_token_authorised_for_another_client_is_refused(rsa_key, jwks) -> None:
    token = _id_token(rsa_key, aud=[CLIENT_ID, "other"], azp="other")
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(token, nonce=NONCE)


def test_required_claims_must_be_present(rsa_key, jwks) -> None:
    token = jwt.encode(
        {"iss": ISSUER, "aud": CLIENT_ID, "nonce": NONCE},  # sub / exp / iat が無い
        rsa_key,
        algorithm="RS256",
        headers={"kid": KEY_ID},
    )
    with pytest.raises(AuthenticationError):
        _provider(jwks)._verify_id_token(token, nonce=NONCE)


# ── ログアウト URL ────────────────────────────────────────────────────────
def test_end_session_url_includes_the_client_and_return_address(jwks) -> None:
    url = _provider(jwks).build_end_session_url(
        post_logout_redirect_uri="https://wbs.example.com/login"
    )
    assert url.startswith(DISCOVERY.end_session_endpoint + "?")
    assert "client_id=wbs" in url
    assert "post_logout_redirect_uri=https%3A%2F%2Fwbs.example.com%2Flogin" in url


def test_no_end_session_url_when_the_idp_has_none(jwks) -> None:
    document = OidcDiscovery(**{**DISCOVERY.__dict__, "end_session_endpoint": None})
    provider = OidcIdentityProvider(
        _settings(), discovery=StubDiscoveryClient(document), jwks_client=OfflineJwksClient(jwks)
    )
    assert provider.build_end_session_url(post_logout_redirect_uri=None) is None


# ── コード交換（トークンエンドポイント）──────────────────────────────────
class _FakeResponse:
    def __init__(self, payload: dict, status_code: int = 200) -> None:
        self._payload = payload
        self.status_code = status_code

    def json(self) -> dict:
        return self._payload

    def raise_for_status(self) -> None:
        return None


def test_exchange_code_sends_the_verifier_and_returns_the_claims(rsa_key, jwks, monkeypatch) -> None:
    posted: dict = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        posted.update({"url": url, "data": data, "auth": auth})
        return _FakeResponse({"id_token": _id_token(rsa_key), "access_token": "at"})

    monkeypatch.setattr("httpx.post", fake_post)
    claims = _provider(jwks).exchange_code(code="the-code", code_verifier="the-verifier", nonce=NONCE)

    assert posted["url"] == DISCOVERY.token_endpoint
    assert posted["data"]["grant_type"] == "authorization_code"
    assert posted["data"]["code"] == "the-code"
    assert posted["data"]["code_verifier"] == "the-verifier"
    # client_secret_basic しか告げない IdP には Authorization ヘッダで送る
    assert posted["auth"] == (CLIENT_ID, "s3cret")
    assert "client_secret" not in posted["data"]

    assert claims.identity.issuer == ISSUER
    assert claims.identity.subject == "abc-123"
    assert claims.email == "taro@example.com"
    assert claims.email_verified is True
    assert claims.resolved_display_name() == "Taro"


def test_client_secret_goes_in_the_body_when_the_idp_asks_for_it(rsa_key, jwks, monkeypatch) -> None:
    document = OidcDiscovery(**{
        **DISCOVERY.__dict__,
        "token_endpoint_auth_methods_supported": ("client_secret_post",),
    })
    provider = OidcIdentityProvider(
        _settings(), discovery=StubDiscoveryClient(document), jwks_client=OfflineJwksClient(jwks)
    )
    posted: dict = {}

    def fake_post(url, data=None, auth=None, headers=None, timeout=None):
        posted.update({"data": data, "auth": auth})
        return _FakeResponse({"id_token": _id_token(rsa_key)})

    monkeypatch.setattr("httpx.post", fake_post)
    provider.exchange_code(code="c", code_verifier="v", nonce=NONCE)
    assert posted["data"]["client_secret"] == "s3cret"
    assert posted["auth"] is None


def test_a_rejected_code_surfaces_as_an_authentication_error(jwks, monkeypatch) -> None:
    monkeypatch.setattr(
        "httpx.post",
        lambda *a, **k: _FakeResponse({"error": "invalid_grant"}, status_code=400),
    )
    with pytest.raises(AuthenticationError):
        _provider(jwks).exchange_code(code="c", code_verifier="v", nonce=NONCE)


def test_a_token_response_without_an_id_token_is_refused(jwks, monkeypatch) -> None:
    monkeypatch.setattr("httpx.post", lambda *a, **k: _FakeResponse({"access_token": "at"}))
    with pytest.raises(AuthenticationError):
        _provider(jwks).exchange_code(code="c", code_verifier="v", nonce=NONCE)


def test_email_is_read_from_userinfo_when_the_id_token_omits_it(rsa_key, jwks, monkeypatch) -> None:
    token = _id_token(rsa_key)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop("email")
    payload.pop("email_verified")
    without_email = jwt.encode(payload, rsa_key, algorithm="RS256", headers={"kid": KEY_ID})

    monkeypatch.setattr(
        "httpx.post", lambda *a, **k: _FakeResponse({"id_token": without_email, "access_token": "at"})
    )
    monkeypatch.setattr(
        "httpx.get",
        lambda *a, **k: _FakeResponse(
            {"sub": "abc-123", "email": "taro@example.com", "email_verified": True}
        ),
    )
    claims = _provider(jwks).exchange_code(code="c", code_verifier="v", nonce=NONCE)
    assert claims.email == "taro@example.com"
    assert claims.email_verified is True


def test_a_userinfo_response_for_another_subject_is_refused(rsa_key, jwks, monkeypatch) -> None:
    token = _id_token(rsa_key)
    payload = jwt.decode(token, options={"verify_signature": False})
    payload.pop("email")
    without_email = jwt.encode(payload, rsa_key, algorithm="RS256", headers={"kid": KEY_ID})

    monkeypatch.setattr(
        "httpx.post", lambda *a, **k: _FakeResponse({"id_token": without_email, "access_token": "at"})
    )
    monkeypatch.setattr(
        "httpx.get", lambda *a, **k: _FakeResponse({"sub": "someone-else", "email": "x@example.com"})
    )
    with pytest.raises(AuthenticationError):
        _provider(jwks).exchange_code(code="c", code_verifier="v", nonce=NONCE)
