"""App Links の検証ファイル（ADR-0019）。打刻アプリのログインの戻り先をアプリへ渡すための宣言。"""

import pytest
from fastapi.testclient import TestClient

PACKAGE = "com.nolumia.wbstimer"
FINGERPRINT = "AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99:AA:BB:CC:DD:EE:FF:00:11:22:33:44:55:66:77:88:99"


def _client(database_path, monkeypatch, **env: str) -> TestClient:
    for key in ("ANDROID_APP_PACKAGE", "ANDROID_APP_CERT_FINGERPRINTS"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    from main import create_app

    return TestClient(create_app(db_path=database_path))


@pytest.mark.parametrize(
    "env",
    [{}, {"ANDROID_APP_PACKAGE": PACKAGE}, {"ANDROID_APP_CERT_FINGERPRINTS": FINGERPRINT}],
    ids=["nothing", "package-only", "fingerprint-only"],
)
def test_without_both_values_there_is_no_file(database_path, monkeypatch, env) -> None:
    with _client(database_path, monkeypatch, **env) as client:
        assert client.get("/.well-known/assetlinks.json").status_code == 404


def test_the_file_names_the_app_and_its_signing_key(database_path, monkeypatch) -> None:
    with _client(
        database_path,
        monkeypatch,
        ANDROID_APP_PACKAGE=PACKAGE,
        ANDROID_APP_CERT_FINGERPRINTS=f'["{FINGERPRINT}"]',
    ) as client:
        res = client.get("/.well-known/assetlinks.json")
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert res.json() == [
        {
            "relation": ["delegate_permission/common.handle_all_urls"],
            "target": {
                "namespace": "android_app",
                "package_name": PACKAGE,
                "sha256_cert_fingerprints": [FINGERPRINT],
            },
        }
    ]


def test_the_file_needs_no_sign_in(database_path, monkeypatch) -> None:
    # Android と Google の検証は Cookie も資格情報も持たずに取りに来る
    monkeypatch.setenv("AUTH_MODE", "oidc")
    monkeypatch.setenv("OIDC_ISSUER", "https://idp.example.com/realms/wbs")
    monkeypatch.setenv("OIDC_CLIENT_ID", "wbs")
    monkeypatch.setenv("OIDC_REDIRECT_URI", "https://wbs.example.com/api/auth/callback")
    with _client(
        database_path,
        monkeypatch,
        ANDROID_APP_PACKAGE=PACKAGE,
        ANDROID_APP_CERT_FINGERPRINTS=FINGERPRINT,
    ) as client:
        assert client.get("/.well-known/assetlinks.json").status_code == 200
