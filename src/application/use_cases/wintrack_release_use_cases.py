"""WinTrack の更新の置き場を中継する（task #384 / ADR-0044）。

WinTrack（Velopack）は ``https://wbs.nolumia.com/api/wintrack/releases/`` を更新の置き場として読む。
中身は配布面（Garage の ``artifacts`` の ``wintrack/``）にあり、配布面は SSO の後ろなので PC から
直接は読めない。WBS が Bearer で本人を確かめてから、配布面を読んで渡す。

- **読めないときは「無い」**（``NotFoundError`` = 404）。WinTrack は「更新を確かめられない」として静かに扱う
- 版の一覧（小さい）は**プロセスの中で短く覚える**。PC が起動のたび・定期に聞いてきても、そのたびに
  配布面へ行かない。読みに行くのは同時に 1 本だけ。読めなかったことも少しの間だけ覚える
- パッケージ（大きい）は覚えずに少しずつ流す（名前ごとに中身は変わらない）
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass

from src.application.ports.release_file_store import (
    ReleaseFileStore,
    ReleaseFileStream,
    ReleaseFileUnavailableError,
)
from src.domain.exceptions import NotFoundError
from src.domain.value_objects.wintrack_release_file import (
    WinTrackReleaseFile,
    WinTrackReleaseFileKind,
    wintrack_release_file,
)

logger = logging.getLogger(__name__)

INDEX_TTL_SECONDS = 60.0
"""版の一覧を覚える長さ。新しい版は出してから最大この時間遅れて PC に見える。"""

FAILURE_TTL_SECONDS = 30.0
"""読めなかったことを覚える長さ。配布面が落ちている間、PC が来るたびに待たせない。"""

MAX_INDEX_BYTES = 1024 * 1024
"""版の一覧の上限（数 KB のもの。これを超えるものは一覧とみなさない）。"""


@dataclass(frozen=True)
class _Remembered:
    body: bytes | None
    until: float


@dataclass(frozen=True)
class IndexFileBody:
    file: WinTrackReleaseFile
    body: bytes


@dataclass(frozen=True)
class PackageFileBody:
    file: WinTrackReleaseFile
    stream: ReleaseFileStream


class WinTrackReleases:
    """プロセスで 1 つ持つ（覚えた一覧を使い回すため）。"""

    def __init__(
        self,
        store: ReleaseFileStore,
        *,
        monotonic: Callable[[], float] = time.monotonic,
        index_ttl_seconds: float = INDEX_TTL_SECONDS,
        failure_ttl_seconds: float = FAILURE_TTL_SECONDS,
    ) -> None:
        self._store = store
        self._monotonic = monotonic
        self._index_ttl_seconds = index_ttl_seconds
        self._failure_ttl_seconds = failure_ttl_seconds
        self._lock = threading.Lock()
        self._remembered: dict[str, _Remembered] = {}

    def fetch(self, name: str) -> IndexFileBody | PackageFileBody:
        """中継するファイル。名前が許されない・設定が無い・読めないときは ``NotFoundError``。"""
        file = wintrack_release_file(name)
        if file is None or not self._store.configured:
            raise NotFoundError("WinTrackReleaseFile", name)
        if file.kind is WinTrackReleaseFileKind.INDEX:
            body = self._index(name)
            if body is None:
                raise NotFoundError("WinTrackReleaseFile", name)
            return IndexFileBody(file=file, body=body)
        try:
            stream = self._store.open(name)
        except ReleaseFileUnavailableError as exc:
            _log_unavailable(name, exc)
            raise NotFoundError("WinTrackReleaseFile", name) from exc
        return PackageFileBody(file=file, stream=stream)

    def forget(self) -> None:
        """覚えた一覧を捨てる（試験用）。"""
        with self._lock:
            self._remembered.clear()

    def _index(self, name: str) -> bytes | None:
        with self._lock:
            now = self._monotonic()
            remembered = self._remembered.get(name)
            if remembered is not None and now < remembered.until:
                return remembered.body
            try:
                body: bytes | None = self._store.read(name, MAX_INDEX_BYTES)
                ttl = self._index_ttl_seconds
            except ReleaseFileUnavailableError as exc:
                _log_unavailable(name, exc)
                body = None
                ttl = self._failure_ttl_seconds
            self._remembered[name] = _Remembered(body=body, until=now + ttl)
            return body


def _log_unavailable(name: str, exc: ReleaseFileUnavailableError) -> None:
    logger.warning(
        "WinTrack の更新の置き場を読めませんでした",
        extra={"event": "wintrack.releases.unavailable", "file": name, "reason": str(exc)},
    )


__all__ = [
    "FAILURE_TTL_SECONDS",
    "INDEX_TTL_SECONDS",
    "IndexFileBody",
    "PackageFileBody",
    "WinTrackReleases",
]
