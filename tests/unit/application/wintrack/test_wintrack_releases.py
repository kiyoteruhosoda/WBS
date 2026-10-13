"""WinTrack の更新の置き場の中継（task #384 / ADR-0044）: 覚える・読めないときは「無い」・名前の制限。"""

from __future__ import annotations

import pytest

from src.application.ports.release_file_store import (
    ReleaseFileStream,
    ReleaseFileUnavailableError,
)
from src.application.use_cases.wintrack_release_use_cases import (
    IndexFileBody,
    PackageFileBody,
    WinTrackReleases,
)
from src.domain.exceptions import NotFoundError


class FakeStore:
    def __init__(self, files: dict[str, bytes], *, configured: bool = True) -> None:
        self.files = files
        self.configured = configured
        self.reads: list[str] = []
        self.failing = False

    def read(self, name: str, max_bytes: int) -> bytes:
        self.reads.append(name)
        if self.failing or name not in self.files:
            raise ReleaseFileUnavailableError(f"no {name}")
        return self.files[name]

    def open(self, name: str) -> ReleaseFileStream:
        self.reads.append(name)
        if self.failing or name not in self.files:
            raise ReleaseFileUnavailableError(f"no {name}")
        body = self.files[name]
        return ReleaseFileStream(size=len(body), chunks=iter([body[:3], body[3:]]))


class Clock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


INDEX = b'{"Assets": []}'
PACKAGE = b"PK\x03\x04-package"


@pytest.fixture
def store() -> FakeStore:
    return FakeStore({"releases.win.json": INDEX, "WinTrack-1.0.3-full.nupkg": PACKAGE})


@pytest.fixture
def clock() -> Clock:
    return Clock()


@pytest.fixture
def releases(store, clock) -> WinTrackReleases:
    return WinTrackReleases(store, monotonic=clock, index_ttl_seconds=60, failure_ttl_seconds=30)


def test_the_index_is_remembered_for_a_short_while(releases, store, clock) -> None:
    first = releases.fetch("releases.win.json")
    assert isinstance(first, IndexFileBody) and first.body == INDEX
    store.files["releases.win.json"] = b'{"Assets": ["new"]}'
    clock.now += 59
    assert releases.fetch("releases.win.json").body == INDEX  # type: ignore[union-attr]
    clock.now += 2
    assert releases.fetch("releases.win.json").body == b'{"Assets": ["new"]}'  # type: ignore[union-attr]
    assert store.reads == ["releases.win.json", "releases.win.json"]


def test_an_unreadable_index_is_not_found_and_not_asked_again_at_once(releases, store, clock) -> None:
    store.failing = True
    with pytest.raises(NotFoundError):
        releases.fetch("releases.win.json")
    store.failing = False
    with pytest.raises(NotFoundError):
        releases.fetch("releases.win.json")
    assert store.reads == ["releases.win.json"]
    clock.now += 31
    assert isinstance(releases.fetch("releases.win.json"), IndexFileBody)


def test_packages_are_streamed_every_time(releases, store) -> None:
    for _ in range(2):
        found = releases.fetch("WinTrack-1.0.3-full.nupkg")
        assert isinstance(found, PackageFileBody)
        assert found.stream.size == len(PACKAGE)
        assert b"".join(found.stream.chunks) == PACKAGE
    assert store.reads == ["WinTrack-1.0.3-full.nupkg"] * 2


def test_a_missing_package_is_not_found(releases) -> None:
    with pytest.raises(NotFoundError):
        releases.fetch("WinTrack-9.9.9-full.nupkg")


@pytest.mark.parametrize("name", ["WinTrack-win-Setup.exe", "../secrets", "latest.json"])
def test_other_names_never_reach_the_store(releases, store, name) -> None:
    with pytest.raises(NotFoundError):
        releases.fetch(name)
    assert store.reads == []


def test_without_settings_nothing_is_read(clock) -> None:
    store = FakeStore({"releases.win.json": INDEX}, configured=False)
    releases = WinTrackReleases(store, monotonic=clock)
    with pytest.raises(NotFoundError):
        releases.fetch("releases.win.json")
    assert store.reads == []
