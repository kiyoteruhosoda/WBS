"""IdP の管理 API を叩くときの名乗り（``client_credentials`` ＋ ``private_key_jwt``）。"""

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from src.domain.exceptions import IdentityProviderUnavailableError
from src.infrastructure.auth.admin_api_token import AdminApiTokenSource, admin_audience
from src.infrastructure.auth.auth_settings import AuthConfigurationError, load_auth_settings
from src.infrastructure.auth.client_assertion import ASSERTION_TYPE
from src.infrastructure.auth.oidc_discovery import OidcDiscovery

ISSUER = "https://idp.example.com/realms/wbs"


class FakeDiscovery:
    def get(self) -> OidcDiscovery:
        return OidcDiscovery(
            issuer=ISSUER,
            authorization_endpoint=f"{ISSUER}/authorize",
            token_endpoint=f"{ISSUER}/token",
            jwks_uri=f"{ISSUER}/jwks",
            userinfo_endpoint=None,
            end_session_endpoint=None,
            id_token_signing_alg_values_supported=("RS256",),
            token_endpoint_auth_methods_supported=("private_key_jwt",),
        )


@pytest.fixture
def private_key(tmp_path):
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    path = tmp_path / "machine.key"
    path.write_bytes(pem)
    return path, key.public_key()


@pytest.fixture
def settings(monkeypatch, private_key):
    path, _ = private_key
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("OIDC_CLIENT_ID", "wbs")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://wbs.example.com/api/auth/callback")
    monkeypatch.setenv("MACHINE_CLIENT_ID", "wbs-machine")
    monkeypatch.setenv("MACHINE_PRIVATE_KEY_FILE", str(path))
    monkeypatch.setenv("MACHINE_PRIVATE_KEY_KID", "key-1")
    return load_auth_settings()


def capture(monkeypatch, payload, status_code=200):
    sent: list[dict] = []

    def fake_post(url, **kwargs):
        sent.append({"url": url, **kwargs})
        request = httpx.Request("POST", url)
        return httpx.Response(status_code, json=payload, request=request)

    monkeypatch.setattr(httpx, "post", fake_post)
    return sent


def test_the_assertion_names_this_machine_and_the_token_endpoint(
    monkeypatch, settings, private_key
) -> None:
    _, public_key = private_key
    sent = capture(monkeypatch, {"access_token": "t-1", "expires_in": 300})

    assert AdminApiTokenSource(settings, FakeDiscovery()).token() == "t-1"

    form = sent[0]["data"]
    assert form["grant_type"] == "client_credentials"
    assert form["client_assertion_type"] == ASSERTION_TYPE
    # ⚠ **宛名が要る。** 省くと権限の載らないトークンになり、管理 API 側で弾かれる。
    assert form["resource"] == admin_audience(ISSUER) == f"{ISSUER}/admin"

    claims = jwt.decode(
        form["client_assertion"], public_key, algorithms=["RS256"], audience=f"{ISSUER}/token"
    )
    # RFC 7523 §3: iss も sub も client_id 自身。
    assert claims["iss"] == claims["sub"] == "wbs-machine"
    assert claims["jti"]
    assert jwt.get_unverified_header(form["client_assertion"])["kid"] == "key-1"


def test_the_token_is_kept_until_it_is_nearly_due(monkeypatch, settings) -> None:
    sent = capture(monkeypatch, {"access_token": "t-1", "expires_in": 300})
    source = AdminApiTokenSource(settings, FakeDiscovery(), monotonic=lambda: 0.0)

    assert source.token() == source.token()
    assert len(sent) == 1  # 2 回目は取り直さない


def test_an_invalidated_token_is_fetched_again(monkeypatch, settings) -> None:
    sent = capture(monkeypatch, {"access_token": "t-1", "expires_in": 300})
    source = AdminApiTokenSource(settings, FakeDiscovery(), monotonic=lambda: 0.0)
    source.token()
    source.invalidate()
    source.token()

    assert len(sent) == 2


def test_a_lifetime_we_cannot_read_is_treated_as_short(monkeypatch, settings) -> None:
    """⚠ **無期限と読まない。** 期限が読めない応答を無期限と扱うと二度と取り直さない。"""
    sent = capture(monkeypatch, {"access_token": "t-1"})  # expires_in が無い
    clock = _Clock()
    source = AdminApiTokenSource(settings, FakeDiscovery(), monotonic=clock)
    source.token()
    clock.now = 120.0  # 仮定した寿命（60 秒）より先へ進める
    source.token()

    assert len(sent) == 2


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def test_a_refused_token_request_is_not_silently_empty(monkeypatch, settings) -> None:
    capture(monkeypatch, {"error": "invalid_client"}, status_code=400)
    with pytest.raises(IdentityProviderUnavailableError):
        AdminApiTokenSource(settings, FakeDiscovery()).token()


def test_a_missing_key_is_a_configuration_error(monkeypatch, settings) -> None:
    monkeypatch.setenv("MACHINE_PRIVATE_KEY_FILE", "/nowhere/machine.key")
    with pytest.raises(AuthConfigurationError):
        AdminApiTokenSource(load_auth_settings(), FakeDiscovery()).token()


def test_without_a_machine_name_there_is_nothing_to_name(monkeypatch, settings) -> None:
    monkeypatch.delenv("MACHINE_CLIENT_ID")
    with pytest.raises(AuthConfigurationError):
        AdminApiTokenSource(load_auth_settings(), FakeDiscovery()).token()
