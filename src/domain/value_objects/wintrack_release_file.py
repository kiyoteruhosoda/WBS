"""WinTrack の更新の置き場で、WBS が中継してよいファイル（task #384 / ADR-0044）。

Velopack の ``SimpleWebSource`` が読むのは、版の一覧（``releases.win.json``、古い形の ``RELEASES``）と
パッケージ（``*.nupkg``）だけ。それ以外の名前は置き場にあっても渡さない（配布面のほかのものへ届かせない）。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from enum import StrEnum

INDEX_FILE_NAMES = frozenset({"releases.win.json", "RELEASES"})
"""版の一覧。小さく、版を出すたびに書き換わる。"""

_PACKAGE_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,199}\.nupkg")
"""パッケージ（``WinTrack-1.0.12-full.nupkg`` など）。名前を変えずに置かれ、中身は変わらない。"""


class WinTrackReleaseFileKind(StrEnum):
    INDEX = "index"
    PACKAGE = "package"


@dataclass(frozen=True)
class WinTrackReleaseFile:
    name: str
    kind: WinTrackReleaseFileKind

    @property
    def media_type(self) -> str:
        if self.name.endswith(".json"):
            return "application/json"
        if self.kind is WinTrackReleaseFileKind.INDEX:
            return "text/plain; charset=utf-8"
        return "application/octet-stream"


def wintrack_release_file(name: str) -> WinTrackReleaseFile | None:
    """中継してよい名前なら、その種類。だめなら None。"""
    if name in INDEX_FILE_NAMES:
        return WinTrackReleaseFile(name, WinTrackReleaseFileKind.INDEX)
    if _PACKAGE_NAME.fullmatch(name) and ".." not in name:
        return WinTrackReleaseFile(name, WinTrackReleaseFileKind.PACKAGE)
    return None


__all__ = [
    "INDEX_FILE_NAMES",
    "WinTrackReleaseFile",
    "WinTrackReleaseFileKind",
    "wintrack_release_file",
]
