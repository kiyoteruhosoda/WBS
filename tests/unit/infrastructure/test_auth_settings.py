import pytest

from src.infrastructure.auth.auth_settings import (
    AuthConfigurationError,
    AuthMode,
    load_auth_settings,
)

OIDC_ENV = {
    "AUTH_MODE": "oidc",
    "OIDC_ISSUER": "https://idp.example.com/realms/wbs",
    "OIDC_CLIENT_ID": "wbs",
    "OIDC_REDIRECT_URI": "https://wbs.example.com/api/auth/callback",
}


@pytest.fixture(autouse=True)
def clean_auth_env(monkeypatch):
    for key in list(OIDC_ENV) + [
        "OIDC_CLIENT_SECRET", "OIDC_SCOPES", "OIDC_PROVIDER_NAME", "OIDC_AUTO_PROVISION",
        "OIDC_ALLOWED_EMAIL_DOMAINS", "OIDC_REQUIRE_VERIFIED_EMAIL", "AUTH_SESSION_TTL_HOURS",
        "AUTH_COOKIE_NAME", "AUTH_COOKIE_SECURE", "AUTH_COOKIE_SAMESITE",
        "AUTH_POST_LOGOUT_REDIRECT_URI", "OIDC_HTTP_TIMEOUT_SECONDS", "APP_CLIENT_IDS",
        "ANDROID_APP_PACKAGE", "ANDROID_APP_CERT_FINGERPRINTS",
    ]:
        monkeypatch.delenv(key, raising=False)


def _use_oidc(monkeypatch, **overrides):
    for key, value in {**OIDC_ENV, **overrides}.items():
        monkeypatch.setenv(key, value)


def test_defaults_to_single_user() -> None:
    settings = load_auth_settings()
    assert settings.mode is AuthMode.SINGLE_USER
    assert settings.sso_enabled is False


def test_oidc_mode_reads_the_provider_settings(monkeypatch) -> None:
    _use_oidc(monkeypatch)
    settings = load_auth_settings()
    assert settings.sso_enabled is True
    assert settings.client_id == "wbs"
    assert settings.scope_list == ["openid", "email", "profile"]
    assert settings.policy.auto_provision is True
    assert settings.policy.require_verified_email is True


def test_a_trailing_slash_on_the_issuer_is_dropped(monkeypatch) -> None:
    # ディスカバリ文書の iss と文字列比較するので、末尾の / で不一致にしない
    _use_oidc(monkeypatch, OIDC_ISSUER="https://idp.example.com/realms/wbs/")
    assert load_auth_settings().issuer == "https://idp.example.com/realms/wbs"


@pytest.mark.parametrize("missing", ["OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_REDIRECT_URI"])
def test_oidc_mode_refuses_to_start_half_configured(monkeypatch, missing: str) -> None:
    _use_oidc(monkeypatch)
    monkeypatch.delenv(missing)
    with pytest.raises(AuthConfigurationError) as exc:
        load_auth_settings()
    assert missing in str(exc.value)


def test_a_plaintext_issuer_is_refused(monkeypatch) -> None:
    _use_oidc(monkeypatch, OIDC_ISSUER="http://idp.example.com")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_localhost_may_use_plain_http_for_development(monkeypatch) -> None:
    _use_oidc(monkeypatch, OIDC_ISSUER="http://localhost:8080/realms/wbs")
    assert load_auth_settings().issuer == "http://localhost:8080/realms/wbs"


def test_an_unknown_mode_is_refused(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "ldap")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_allowed_domains_are_split_and_normalised(monkeypatch) -> None:
    _use_oidc(monkeypatch, OIDC_ALLOWED_EMAIL_DOMAINS=" Example.com , partner.example ")
    assert load_auth_settings().policy.allowed_email_domains == ("example.com", "partner.example")


def test_cookie_and_session_settings_can_be_overridden(monkeypatch) -> None:
    _use_oidc(
        monkeypatch,
        AUTH_COOKIE_NAME="my_session",
        AUTH_COOKIE_SECURE="false",
        AUTH_SESSION_TTL_HOURS="1.5",
    )
    settings = load_auth_settings()
    assert settings.cookie_name == "my_session"
    assert settings.cookie_secure is False
    assert settings.session_ttl.total_seconds() == 5400


def test_the_cookie_is_secure_by_default(monkeypatch) -> None:
    _use_oidc(monkeypatch)
    assert load_auth_settings().cookie_secure is True


def test_a_non_numeric_ttl_is_refused(monkeypatch) -> None:
    _use_oidc(monkeypatch, AUTH_SESSION_TTL_HOURS="soon")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_app_tokens_are_closed_by_default(monkeypatch) -> None:
    # 宣言が無ければ、どのアプリのトークンも受け取らない（ADR-0018）
    _use_oidc(monkeypatch)
    assert load_auth_settings().app_client_ids == frozenset()


@pytest.mark.parametrize("raw", [" app-1 , app-2 ,", '["app-1", "app-2"]'], ids=["comma", "json"])
def test_app_client_ids_are_read_as_a_list(monkeypatch, raw: str) -> None:
    _use_oidc(monkeypatch, APP_CLIENT_IDS=raw)
    assert load_auth_settings().app_client_ids == frozenset({"app-1", "app-2"})


def test_a_broken_app_client_ids_list_is_refused(monkeypatch) -> None:
    _use_oidc(monkeypatch, APP_CLIENT_IDS='["app-1"')
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_app_links_are_off_by_default(monkeypatch) -> None:
    settings = load_auth_settings()
    assert settings.android_app_package == ""
    assert settings.android_app_cert_fingerprints == ()


def test_app_links_values_are_read(monkeypatch) -> None:
    monkeypatch.setenv("ANDROID_APP_PACKAGE", " com.nolumia.wbstimer ")
    monkeypatch.setenv("ANDROID_APP_CERT_FINGERPRINTS", '["BB:00", "AA:00"]')
    settings = load_auth_settings()
    assert settings.android_app_package == "com.nolumia.wbstimer"
    assert settings.android_app_cert_fingerprints == ("AA:00", "BB:00")
