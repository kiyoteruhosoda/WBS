def test_healthz_ok(client) -> None:
    response = client.get("/healthz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "timestamp_utc" in data
    assert isinstance(data["uptime_seconds"], float)


def test_readyz_ok(client) -> None:
    response = client.get("/readyz")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["checks"]["database"] == "ok"
    assert "timestamp_utc" in data


def test_info_available_under_api_prefix(client) -> None:
    # フロントエンドは nginx 経由で /api/ 配下しか到達できない
    response = client.get("/api/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "git_sha" in data


def test_info(client) -> None:
    response = client.get("/info")
    assert response.status_code == 200
    data = response.json()
    assert "version" in data
    assert "git_sha" in data
    assert "build_time" in data
    assert "environment" in data


def _client_with_version_file(monkeypatch, database_path, version_file):
    from fastapi.testclient import TestClient

    from main import create_app
    from src.infrastructure import build_info

    for key in ("APP_VERSION", "GIT_SHA", "BUILD_TIME"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(build_info, "VERSION_FILE", version_file)
    return TestClient(create_app(db_path=database_path))


def test_info_reports_the_stamped_commit(monkeypatch, database_path, tmp_path) -> None:
    # 本番の経路: ビルドの前に scripts/generate_version.sh が刻んだ版を答える（task #168）
    version_file = tmp_path / "version.json"
    version_file.write_text(
        '{"version": "abc1234", "commit_hash": "abc1234", "branch": "main",'
        ' "build_date": "2026-10-01T01:02:03Z"}',
        encoding="utf-8",
    )
    with _client_with_version_file(monkeypatch, database_path, version_file) as client:
        data = client.get("/info").json()

    assert set(data) == {"version", "git_sha", "build_time", "environment"}
    assert data["version"] == "abc1234"
    assert data["git_sha"] == "abc1234"
    assert data["build_time"] == "2026-10-01T01:02:03Z"


def test_info_without_version_file_says_dev(monkeypatch, database_path, tmp_path) -> None:
    with _client_with_version_file(monkeypatch, database_path, tmp_path / "missing.json") as client:
        data = client.get("/info").json()

    assert set(data) == {"version", "git_sha", "build_time", "environment"}
    assert data["git_sha"] == "dev"
    assert data["build_time"] == "unknown"
