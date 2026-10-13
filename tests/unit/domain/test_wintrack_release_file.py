"""WinTrack の更新の置き場で中継してよい名前（task #384 / ADR-0044）。"""

from __future__ import annotations

import pytest

from src.domain.value_objects.wintrack_release_file import (
    WinTrackReleaseFileKind,
    wintrack_release_file,
)


@pytest.mark.parametrize(
    ("name", "kind", "media_type"),
    [
        ("releases.win.json", WinTrackReleaseFileKind.INDEX, "application/json"),
        ("RELEASES", WinTrackReleaseFileKind.INDEX, "text/plain; charset=utf-8"),
        ("WinTrack-1.0.12-full.nupkg", WinTrackReleaseFileKind.PACKAGE, "application/octet-stream"),
        ("WinTrack-1.0.13-delta.nupkg", WinTrackReleaseFileKind.PACKAGE, "application/octet-stream"),
    ],
)
def test_the_velopack_files_are_relayed(name, kind, media_type) -> None:
    file = wintrack_release_file(name)
    assert file is not None
    assert (file.kind, file.media_type) == (kind, media_type)


@pytest.mark.parametrize(
    "name",
    [
        "WinTrack-win-Setup.exe",
        "latest.json",
        "releases.beta.json",
        "..nupkg",
        "a..b.nupkg",
        ".hidden.nupkg",
        "WinTrack 1.0.nupkg",
        "releases.win.json.bak",
        "x" * 300 + ".nupkg",
    ],
)
def test_other_names_are_not(name) -> None:
    assert wintrack_release_file(name) is None
