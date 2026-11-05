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
    "SESSION_SIGNING_KEY": "k" * 32,
}


@pytest.fixture(autouse=True)
def clean_auth_env(monkeypatch):
    for key in list(OIDC_ENV) + [
        "OIDC_CLIENT_SECRET", "OIDC_SCOPES", "OIDC_PROVIDER_NAME", "OIDC_AUTO_PROVISION",
        "OIDC_ALLOWED_EMAIL_DOMAINS", "OIDC_REQUIRE_VERIFIED_EMAIL", "ACCESS_TOKEN_EXPIRES_SECONDS", "SESSION_SIGNING_KEY_FILE",
        "AUTH_COOKIE_NAME", "AUTH_COOKIE_SECURE", "AUTH_COOKIE_SAMESITE",
        "AUTH_POST_LOGOUT_REDIRECT_URI", "OIDC_HTTP_TIMEOUT_SECONDS", "MACHINE_READER_CLIENT_IDS",
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


def test_cookie_and_token_settings_can_be_overridden(monkeypatch) -> None:
    _use_oidc(
        monkeypatch,
        AUTH_COOKIE_NAME="my_session",
        AUTH_COOKIE_SECURE="false",
        ACCESS_TOKEN_EXPIRES_SECONDS="60",
    )
    settings = load_auth_settings()
    assert settings.cookie_name == "my_session"
    assert settings.cookie_secure is False
    assert settings.access_token_ttl.total_seconds() == 60


def test_the_token_lives_five_minutes_and_the_sign_in_is_kept_thirty_days(monkeypatch) -> None:
    _use_oidc(monkeypatch)
    settings = load_auth_settings()
    assert settings.access_token_ttl.total_seconds() == 300
    assert settings.sign_in_carry.total_seconds() == 30 * 24 * 3600


def test_a_lifetime_must_be_positive(monkeypatch) -> None:
    _use_oidc(monkeypatch, ACCESS_TOKEN_EXPIRES_SECONDS="0")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


@pytest.mark.parametrize("key", ["", "short"])
def test_sso_does_not_start_without_a_long_enough_signing_key(monkeypatch, key) -> None:
    """⚠ 起動で落とす。乱数で埋めると、再起動のたびに全員のログインが切れる。"""
    _use_oidc(monkeypatch, SESSION_SIGNING_KEY=key)
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_the_signing_key_is_read_from_its_file(monkeypatch, tmp_path) -> None:
    key_file = tmp_path / "signing-key"
    key_file.write_text("f" * 40 + "\n", encoding="utf-8")
    _use_oidc(monkeypatch, SESSION_SIGNING_KEY="", SESSION_SIGNING_KEY_FILE=str(key_file))
    assert load_auth_settings().session_signing_key == "f" * 40


def test_an_unreadable_key_file_names_only_the_path(monkeypatch, tmp_path) -> None:
    missing = tmp_path / "missing"
    _use_oidc(monkeypatch, SESSION_SIGNING_KEY="", SESSION_SIGNING_KEY_FILE=str(missing))
    with pytest.raises(AuthConfigurationError, match="could not be read"):
        load_auth_settings()


def test_single_user_mode_needs_no_signing_key(monkeypatch) -> None:
    monkeypatch.setenv("AUTH_MODE", "single_user")
    monkeypatch.delenv("SESSION_SIGNING_KEY", raising=False)
    assert load_auth_settings().session_signing_key == ""


def test_the_cookie_is_secure_by_default(monkeypatch) -> None:
    _use_oidc(monkeypatch)
    assert load_auth_settings().cookie_secure is True


def test_a_non_numeric_ttl_is_refused(monkeypatch) -> None:
    _use_oidc(monkeypatch, ACCESS_TOKEN_EXPIRES_SECONDS="soon")
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()


def test_machine_readers_are_closed_by_default(monkeypatch) -> None:
    # 宣言が無ければ、どのアプリの機械のトークンも受け取らない（ADR-0056）
    _use_oidc(monkeypatch)
    assert load_auth_settings().machine_reader_client_ids == frozenset()


@pytest.mark.parametrize("raw", [" app-1 , app-2 ,", '["app-1", "app-2"]'], ids=["comma", "json"])
def test_machine_reader_client_ids_are_read_as_a_list(monkeypatch, raw: str) -> None:
    _use_oidc(monkeypatch, MACHINE_READER_CLIENT_IDS=raw)
    assert load_auth_settings().machine_reader_client_ids == frozenset({"app-1", "app-2"})


def test_a_broken_machine_reader_client_ids_list_is_refused(monkeypatch) -> None:
    _use_oidc(monkeypatch, MACHINE_READER_CLIENT_IDS='["app-1"')
    with pytest.raises(AuthConfigurationError):
        load_auth_settings()
