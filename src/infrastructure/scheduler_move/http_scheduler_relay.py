"""Scheduler の api へ HTTP で中継する（task #535 / Scheduler の ADR-0054 決定 3。WBS の ADR-0054）。

渡すもの・返すものは Tracker への中継（``tracker_move/http_tracker_relay.py``）と同じに決めてある。
⚠ **渡すヘッダーは決めたものだけ**（``Authorization`` は渡す。WBS の Cookie は渡さない ——
Scheduler には意味が無く、WBS のログインを外へ出すことになる）。返すヘッダーも決めたものだけ。
"""

from __future__ import annotations

import httpx

from src.application.ports.scheduler_relay import (
    SchedulerRelayedResponse,
    SchedulerRelayRequest,
    SchedulerUnreachableError,
)

#: Scheduler へ渡すヘッダー（小文字）
FORWARDED_REQUEST_HEADERS = frozenset(
    {"authorization", "content-type", "accept", "accept-language", "user-agent", "if-none-match"}
)
#: 端末へ返すヘッダー（小文字）
RETURNED_RESPONSE_HEADERS = frozenset(
    {"content-type", "www-authenticate", "retry-after", "location", "cache-control", "etag"}
)
#: Tracker への中継と同じ長さ（アラームの口は 7 日分を読むだけなので、ふつうは 1 秒もかからない）
DEFAULT_TIMEOUT_SECONDS = 30.0


class HttpSchedulerRelay:
    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            timeout=timeout_seconds,
            transport=transport,
            # 中継先の転送は端末へ返す（ここで辿らない）
            follow_redirects=False,
        )

    async def relay(self, request: SchedulerRelayRequest) -> SchedulerRelayedResponse:
        url = f"{request.path}?{request.query}" if request.query else request.path
        headers = {
            name: value
            for name, value in request.headers.items()
            if name.lower() in FORWARDED_REQUEST_HEADERS
        }
        try:
            response = await self._client.request(
                request.method, url, headers=headers, content=request.body or None
            )
        except httpx.HTTPError as exc:
            raise SchedulerUnreachableError(f"{type(exc).__name__}: {exc}") from exc
        return SchedulerRelayedResponse(
            status_code=response.status_code,
            headers={
                name.lower(): value
                for name, value in response.headers.items()
                if name.lower() in RETURNED_RESPONSE_HEADERS
            },
            body=response.content,
        )

    async def aclose(self) -> None:
        await self._client.aclose()


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "FORWARDED_REQUEST_HEADERS",
    "HttpSchedulerRelay",
    "RETURNED_RESPONSE_HEADERS",
]
