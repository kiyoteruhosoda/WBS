"""``version.json`` から版を読む（task #168、ADR-0011）。"""

import json

import pytest

from src.infrastructure.build_info import load_build_info

STAMPED = {
    "version": "abc1234",
    "commit_hash": "abc1234",
    "commit_hash_full": "abc1234" + "0" * 33,
    "branch": "main",
    "commit_date": "2026-10-01T00:00:00+00:00",
    "build_date": "2026-10-01T01:02:03Z",
}


@pytest.fixture(autouse=True)
def clean_build_env(monkeypatch):
    for key in ("APP_VERSION", "GIT_SHA", "BUILD_TIME", "APP_ENV"):
        monkeypatch.delenv(key, raising=False)


def test_reads_the_stamped_version_file(tmp_path) -> None:
    path = tmp_path / "version.json"
    path.write_text(json.dumps(STAMPED), encoding="utf-8")

    info = load_build_info(path)

    assert info.version == "abc1234"
    assert info.git_sha == "abc1234"
    assert info.build_time == "2026-10-01T01:02:03Z"


def test_without_the_file_it_says_dev(tmp_path) -> None:
    info = load_build_info(tmp_path / "missing.json")

    assert info.git_sha == "dev"
    assert info.build_time == "unknown"
    assert info.version  # パッケージの版か 0.0.0。空にはしない


@pytest.mark.parametrize("body", ["", "{not json", "[]", '{"commit_hash": 1}'])
def test_a_broken_file_is_treated_as_missing(tmp_path, body) -> None:
    path = tmp_path / "version.json"
    path.write_text(body, encoding="utf-8")

    info = load_build_info(path)

    assert info.git_sha == "dev"
    assert info.build_time == "unknown"


def test_environment_variables_win_over_the_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "version.json"
    path.write_text(json.dumps(STAMPED), encoding="utf-8")
    monkeypatch.setenv("GIT_SHA", "fromenv")
    monkeypatch.setenv("APP_ENV", "production")

    info = load_build_info(path)

    assert info.git_sha == "fromenv"
    assert info.version == "abc1234"
    assert info.environment == "production"
