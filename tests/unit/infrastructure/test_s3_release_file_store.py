"""配布面（Garage）から WinTrack の更新の置き場を読む実装（task #384 / ADR-0044）。

置き場へは行かない。``boto3.client`` を差し替え、渡した資格情報と読んだ先を見る。
"""

from __future__ import annotations

import io
from pathlib import Path
from typing import Any

import pytest
from botocore.exceptions import ClientError

from src.application.ports.release_file_store import ReleaseFileUnavailableError
from src.infrastructure.wintrack_release import s3_release_file_store
from src.infrastructure.wintrack_release.s3_release_file_store import S3ReleaseFileStore
from src.infrastructure.wintrack_release.wintrack_release_settings import (
    WinTrackReleaseSettings,
    load_wintrack_release_settings,
)

SECRET = "garage-secret-for-tests"


class _Body(io.BytesIO):
    def iter_chunks(self, size: int):
        while chunk := self.read(size):
            yield chunk


class _Client:
    def __init__(self, objects: dict[str, bytes]) -> None:
        self.objects = objects
        self.asked: list[tuple[str, str]] = []

    def get_object(self, *, Bucket: str, Key: str) -> dict[str, Any]:  # noqa: N803 — boto3 の引数名
        self.asked.append((Bucket, Key))
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "missing"}}, "GetObject")
        body = self.objects[Key]
        return {"Body": _Body(body), "ContentLength": len(body)}


class _Boto3:
    def __init__(self, client: _Client) -> None:
        self.client_instance = client
        self.kwargs: dict[str, Any] = {}

    def client(self, service: str, **kwargs: Any) -> _Client:
        assert service == "s3"
        self.kwargs = kwargs
        return self.client_instance


@pytest.fixture
def secret_file(tmp_path: Path) -> Path:
    path = tmp_path / "secret-access-key"
    path.write_text(SECRET + "\n", encoding="utf-8")
    return path


@pytest.fixture
def boto(monkeypatch) -> _Boto3:
    fake = _Boto3(
        _Client({"wintrack/releases.win.json": b'{"Assets":[]}', "wintrack/W-1.0.1-full.nupkg": b"x" * 10})
    )
    monkeypatch.setattr(s3_release_file_store, "boto3", fake)
    return fake


def _store(secret_file: Path | str) -> S3ReleaseFileStore:
    return S3ReleaseFileStore(
        WinTrackReleaseSettings(
            endpoint_url="http://garage.blob-prod.svc.cluster.local:3900",
            region="garage",
            bucket="artifacts",
            prefix="wintrack/",
            access_key_id="GKread",
            secret_access_key_file=str(secret_file),
        )
    )


def test_reads_under_the_prefix_with_the_key_from_the_file(boto, secret_file) -> None:
    assert _store(secret_file).read("releases.win.json", 1024) == b'{"Assets":[]}'
    assert boto.client_instance.asked == [("artifacts", "wintrack/releases.win.json")]
    assert boto.kwargs["aws_access_key_id"] == "GKread"
    assert boto.kwargs["aws_secret_access_key"] == SECRET
    assert boto.kwargs["endpoint_url"] == "http://garage.blob-prod.svc.cluster.local:3900"
    assert boto.kwargs["config"].s3 == {"addressing_style": "path"}


def test_packages_are_read_in_chunks(boto, secret_file) -> None:
    stream = _store(secret_file).open("W-1.0.1-full.nupkg")
    assert stream.size == 10
    assert b"".join(stream.chunks) == b"x" * 10


def test_a_missing_object_is_unavailable(boto, secret_file) -> None:
    with pytest.raises(ReleaseFileUnavailableError):
        _store(secret_file).read("RELEASES", 1024)


def test_a_too_large_index_is_unavailable(boto, secret_file) -> None:
    with pytest.raises(ReleaseFileUnavailableError):
        _store(secret_file).read("releases.win.json", 5)


@pytest.mark.parametrize("content", [None, "  \n"], ids=["missing-file", "empty-file"])
def test_an_unreadable_secret_is_unavailable(boto, tmp_path, content) -> None:
    path = tmp_path / "secret"
    if content is not None:
        path.write_text(content, encoding="utf-8")
    with pytest.raises(ReleaseFileUnavailableError):
        _store(path).read("releases.win.json", 1024)
    assert boto.client_instance.asked == []


def test_settings_are_off_until_all_are_given(monkeypatch) -> None:
    for key in (
        "WINTRACK_RELEASES_S3_ENDPOINT_URL",
        "WINTRACK_RELEASES_S3_REGION",
        "WINTRACK_RELEASES_S3_BUCKET",
        "WINTRACK_RELEASES_S3_PREFIX",
        "WINTRACK_RELEASES_S3_ACCESS_KEY_ID",
        "WINTRACK_RELEASES_S3_SECRET_ACCESS_KEY_FILE",
    ):
        monkeypatch.delenv(key, raising=False)
    assert load_wintrack_release_settings().configured is False
    monkeypatch.setenv("WINTRACK_RELEASES_S3_ENDPOINT_URL", "http://garage:3900")
    monkeypatch.setenv("WINTRACK_RELEASES_S3_BUCKET", "artifacts")
    monkeypatch.setenv("WINTRACK_RELEASES_S3_ACCESS_KEY_ID", "GKread")
    assert load_wintrack_release_settings().configured is False
    monkeypatch.setenv("WINTRACK_RELEASES_S3_SECRET_ACCESS_KEY_FILE", "/run/secrets/wintrack-releases")
    settings = load_wintrack_release_settings()
    assert settings.configured is True
    assert settings.prefix == "wintrack/"
    monkeypatch.setenv("WINTRACK_RELEASES_S3_PREFIX", "/apps/wintrack")
    assert load_wintrack_release_settings().prefix == "apps/wintrack/"
