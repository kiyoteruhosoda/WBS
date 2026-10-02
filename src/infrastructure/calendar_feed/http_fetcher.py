"""URL から iCalendar を取る（ADR-0037）。

利用者が渡した URL をサーバーから読みに行くので、**内側へ向けさせない**:

- ``https`` だけ（``webcal`` / ``webcals`` は ``https`` に読み替える。Google・Outlook の公開 URL は https）
- 宛先のホスト名を引き、どれか 1 つでも全世界向けでないアドレス（私設・ループバック・リンクローカル・
  予約など）なら断る。転送（3xx）の先も同じく確かめる（3 回まで）
- 大きさの上限（``MAX_FEED_BYTES``）を超えたら読むのをやめる。時間切れは ``FETCH_TIMEOUT_SECONDS``

⚠ 名前を引いてから接続するまでの間に答えが変わる（DNS の付け替え）ことまでは防がない。

⚠ URL そのものはログに出さない（Google の非公開アドレス・Outlook の公開 URL は、それだけで中身が読める）。
"""

from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure

MAX_FEED_BYTES = 10 * 1024 * 1024
FETCH_TIMEOUT_SECONDS = 20.0
MAX_REDIRECTS = 3
USER_AGENT = "wbs-calendar-import/1.0"


def normalize_feed_url(raw: str) -> str:
    """``webcal(s)://`` を ``https://`` へ。https でなければ ``invalid_url``。"""
    url = raw.strip()
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme in ("webcal", "webcals"):
        parts = parts._replace(scheme="https")
    elif scheme != "https":
        raise CalendarFeedError(FeedFailure.INVALID_URL)
    if not parts.hostname:
        raise CalendarFeedError(FeedFailure.INVALID_URL)
    return urlunsplit(parts)


def ensure_public_host(host: str, port: int) -> None:
    """ホスト名の全部のアドレスが全世界向けか確かめる（違えば ``blocked_address``）。"""
    try:
        literal = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        literal = None
    if literal is not None:
        addresses = {literal}
    else:
        try:
            infos = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
        except (socket.gaierror, UnicodeError) as exc:
            raise CalendarFeedError(FeedFailure.UNREACHABLE) from exc
        addresses = {ipaddress.ip_address(info[4][0]) for info in infos}
    if not addresses:
        raise CalendarFeedError(FeedFailure.UNREACHABLE)
    for address in addresses:
        if isinstance(address, ipaddress.IPv6Address) and address.ipv4_mapped is not None:
            address = address.ipv4_mapped
        if not address.is_global or address.is_multicast:
            raise CalendarFeedError(FeedFailure.BLOCKED_ADDRESS)


class HttpCalendarFeedFetcher:
    def __init__(
        self,
        *,
        timeout_seconds: float = FETCH_TIMEOUT_SECONDS,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        # 試験だけが差し替える（宛先の確かめは差し替えても効く）
        self._transport = transport

    def fetch(self, url: str) -> bytes:
        current = normalize_feed_url(url)
        with httpx.Client(
            timeout=self._timeout,
            transport=self._transport,
            follow_redirects=False,
            headers={"User-Agent": USER_AGENT, "Accept": "text/calendar, */*;q=0.5"},
        ) as client:
            for _ in range(MAX_REDIRECTS + 1):
                parts = urlsplit(current)
                assert parts.hostname is not None
                ensure_public_host(parts.hostname, parts.port or 443)
                try:
                    with client.stream("GET", current) as response:
                        if response.is_redirect:
                            location = response.headers.get("Location")
                            if not location:
                                raise CalendarFeedError(FeedFailure.HTTP_ERROR)
                            current = normalize_feed_url(urljoin(current, location))
                            continue
                        _raise_for_status(response.status_code)
                        return _read_capped(response)
                except httpx.HTTPError as exc:
                    raise CalendarFeedError(FeedFailure.UNREACHABLE) from exc
        raise CalendarFeedError(FeedFailure.HTTP_ERROR)


def _raise_for_status(status: int) -> None:
    if status < 400:
        return
    if status in (404, 410):
        raise CalendarFeedError(FeedFailure.NOT_FOUND)
    if status in (401, 403):
        raise CalendarFeedError(FeedFailure.FORBIDDEN)
    raise CalendarFeedError(FeedFailure.HTTP_ERROR)


def _read_capped(response: httpx.Response) -> bytes:
    declared = response.headers.get("Content-Length")
    if declared is not None and declared.isdigit() and int(declared) > MAX_FEED_BYTES:
        raise CalendarFeedError(FeedFailure.TOO_LARGE)
    chunks: list[bytes] = []
    size = 0
    for chunk in response.iter_bytes():
        size += len(chunk)
        if size > MAX_FEED_BYTES:
            raise CalendarFeedError(FeedFailure.TOO_LARGE)
        chunks.append(chunk)
    return b"".join(chunks)


__all__ = [
    "MAX_FEED_BYTES",
    "HttpCalendarFeedFetcher",
    "ensure_public_host",
    "normalize_feed_url",
]
