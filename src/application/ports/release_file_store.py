"""配布面（Garage の ``artifacts``）から WinTrack の更新の置き場のファイルを読む口（ADR-0044）。"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from typing import Protocol


class ReleaseFileUnavailableError(Exception):
    """読めなかった（設定が無い・鍵のファイルが無い・置き場に無い・置き場が落ちている）。"""


@dataclass
class ReleaseFileStream:
    """読み始めたファイル。``chunks`` を読み切るか ``close`` で、置き場との繋がりを返す。"""

    size: int | None
    chunks: Iterator[bytes]


class ReleaseFileStore(Protocol):
    @property
    def configured(self) -> bool:
        """読む先が揃っているか（揃っていなければ何も読まない）。"""
        ...

    def read(self, name: str, max_bytes: int) -> bytes:
        """小さいファイルを丸ごと読む。``max_bytes`` を超えたら ``ReleaseFileUnavailableError``。"""
        ...

    def open(self, name: str) -> ReleaseFileStream:
        """大きいファイルを少しずつ読む。"""
        ...
