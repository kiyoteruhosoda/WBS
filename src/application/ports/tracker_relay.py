"""Tracker へ打刻まわりの口を中継する口（task #526 / ADR-0053。実装は
``src/infrastructure/tracker_move/http_tracker_relay.py``）。

WBS は利用者の代わりに名乗らない。届いた ``Authorization`` をそのまま渡し、答えをそのまま返すだけ。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class RelayRequest:
    method: str
    #: ``/api/...``（WBS に来たままの道）
    path: str
    #: ``?`` を含まない問い合わせの文字列（無ければ空）
    query: str
    #: 渡してよいヘッダーだけ（名前は小文字）
    headers: Mapping[str, str]
    body: bytes = b""


@dataclass(frozen=True)
class RelayedResponse:
    status_code: int
    #: 返してよいヘッダーだけ（名前は小文字）
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


class TrackerUnreachableError(Exception):
    """Tracker に届かなかった・時間内に答えなかった（端末は 5xx を受けて送り直す）。"""


class TrackerRelay(Protocol):
    async def relay(self, request: RelayRequest) -> RelayedResponse: ...

    async def aclose(self) -> None: ...


__all__ = ["RelayRequest", "RelayedResponse", "TrackerRelay", "TrackerUnreachableError"]
