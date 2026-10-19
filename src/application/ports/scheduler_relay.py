"""Scheduler へ予定のアラームの口を中継する口（task #535 / WBS の ADR-0054。実装は
``src/infrastructure/scheduler_move/http_scheduler_relay.py``）。

WBS は利用者の代わりに名乗らない。届いた ``Authorization`` をそのまま渡し、答えをそのまま返すだけ。
形は Tracker への中継（``tracker_relay.py``）と同じだが、2 つの関所は段 4 で別々に消すので、共有しない。
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol


@dataclass(frozen=True)
class SchedulerRelayRequest:
    method: str
    #: ``/api/...``（WBS に来たままの道）
    path: str
    #: ``?`` を含まない問い合わせの文字列（無ければ空）
    query: str
    #: 渡してよいヘッダーだけ（名前は小文字）
    headers: Mapping[str, str]
    body: bytes = b""


@dataclass(frozen=True)
class SchedulerRelayedResponse:
    status_code: int
    #: 返してよいヘッダーだけ（名前は小文字）
    headers: Mapping[str, str] = field(default_factory=dict)
    body: bytes = b""


class SchedulerUnreachableError(Exception):
    """Scheduler に届かなかった・時間内に答えなかった（端末は 5xx を受けて引き直す）。"""


class SchedulerRelay(Protocol):
    async def relay(self, request: SchedulerRelayRequest) -> SchedulerRelayedResponse: ...

    async def aclose(self) -> None: ...


__all__ = [
    "SchedulerRelay",
    "SchedulerRelayRequest",
    "SchedulerRelayedResponse",
    "SchedulerUnreachableError",
]
