"""Tracker の api へ HTTP で中継する（task #526 / ADR-0053 決定 3）。

⚠ **渡すヘッダーは決めたものだけ**（``Authorization`` は渡す。WBS の Cookie は渡さない ——
Tracker には意味が無く、WBS のログインを外へ出すことになる）。返すヘッダーも決めたものだけ
（長さと転送の符号化は作り直す。WBS の画面のための ``Set-Cookie`` は Tracker からは来ないはず
だが、来ても返さない）。
"""

from __future__ import annotations

import httpx

from src.application.ports.tracker_relay import (
    RelayedResponse,
    RelayRequest,
    TrackerUnreachableError,
)

#: Tracker へ渡すヘッダー（小文字）
FORWARDED_REQUEST_HEADERS = frozenset(
    {"authorization", "content-type", "accept", "accept-language", "user-agent", "if-none-match"}
)
#: 端末へ返すヘッダー（小文字）
RETURNED_RESPONSE_HEADERS = frozenset(
    {"content-type", "www-authenticate", "retry-after", "location", "cache-control", "etag"}
)
#: WinTrack が 1 回に送る区間の数（数百）を Tracker が書き終えるまで待つ長さ
DEFAULT_TIMEOUT_SECONDS = 30.0


class HttpTrackerRelay:
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

    async def relay(self, request: RelayRequest) -> RelayedResponse:
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
            raise TrackerUnreachableError(f"{type(exc).__name__}: {exc}") from exc
        return RelayedResponse(
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
    "HttpTrackerRelay",
    "RETURNED_RESPONSE_HEADERS",
]
