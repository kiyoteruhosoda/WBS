"""WinTrack の更新の置き場の中継の口（task #384 / ADR-0044）。配布面は差し替える。"""

from __future__ import annotations

import pytest

from src.application.ports.release_file_store import (
    ReleaseFileStream,
    ReleaseFileUnavailableError,
)
from src.application.use_cases.wintrack_release_use_cases import WinTrackReleases
from src.infrastructure.wintrack_release.s3_release_file_store import S3ReleaseFileStore
from src.infrastructure.wintrack_release.wintrack_release_settings import WinTrackReleaseSettings
from src.presentation.api.dependencies import get_wintrack_releases

INDEX = b'{"Assets":[{"PackageId":"WinTrack","Version":"1.0.3"}]}'
PACKAGE = b"PK\x03\x04" + b"0" * 2048


class FakeStore:
    configured = True

    def read(self, name: str, max_bytes: int) -> bytes:
        if name == "releases.win.json":
            return INDEX
        raise ReleaseFileUnavailableError(name)

    def open(self, name: str) -> ReleaseFileStream:
        if name == "WinTrack-1.0.3-full.nupkg":
            return ReleaseFileStream(size=len(PACKAGE), chunks=iter([PACKAGE[:1000], PACKAGE[1000:]]))
        raise ReleaseFileUnavailableError(name)


@pytest.fixture
def relayed(client):
    client.app.dependency_overrides[get_wintrack_releases] = lambda: WinTrackReleases(FakeStore())
    yield client
    client.app.dependency_overrides.pop(get_wintrack_releases, None)


def test_without_settings_every_file_is_not_found(client) -> None:
    # 設定が空でも起動し、404 を返す（WinTrack は「更新を確かめられない」として静かに扱う）
    client.app.dependency_overrides[get_wintrack_releases] = lambda: WinTrackReleases(
        S3ReleaseFileStore(WinTrackReleaseSettings())
    )
    try:
        for name in ("releases.win.json", "RELEASES", "WinTrack-1.0.3-full.nupkg"):
            assert client.get(f"/api/wintrack/releases/{name}").status_code == 404
    finally:
        client.app.dependency_overrides.pop(get_wintrack_releases, None)


def test_the_index_is_relayed(relayed) -> None:
    res = relayed.get("/api/wintrack/releases/releases.win.json?localVersion=1.0.2&id=WinTrack")
    assert res.status_code == 200, res.text
    assert res.content == INDEX
    assert res.headers["content-type"].startswith("application/json")
    assert res.headers["cache-control"] == "no-store"


def test_a_package_is_streamed(relayed) -> None:
    res = relayed.get("/api/wintrack/releases/WinTrack-1.0.3-full.nupkg")
    assert res.status_code == 200
    assert res.content == PACKAGE
    assert res.headers["content-type"] == "application/octet-stream"
    assert res.headers["content-length"] == str(len(PACKAGE))


@pytest.mark.parametrize(
    "name", ["RELEASES", "WinTrack-9.9.9-full.nupkg", "WinTrack-win-Setup.exe", "latest.json"]
)
def test_missing_or_other_files_are_not_found(relayed, name) -> None:
    assert relayed.get(f"/api/wintrack/releases/{name}").status_code == 404
