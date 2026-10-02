"""URL から iCalendar を取る口（task #196 / ADR-0037）。https だけ・内側の宛先は断る・転送の先も確かめる・
大きさの上限・HTTP の失敗の読み分け。"""

from __future__ import annotations

import httpx
import pytest

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure
from src.infrastructure.calendar_feed import http_fetcher
from src.infrastructure.calendar_feed.http_fetcher import (
    HttpCalendarFeedFetcher,
    ensure_public_host,
    normalize_feed_url,
)

PUBLIC = "https://93.184.216.34/calendar.ics"
ICS = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


def _fetcher(handler) -> HttpCalendarFeedFetcher:
    return HttpCalendarFeedFetcher(transport=httpx.MockTransport(handler))


def _reason(call) -> FeedFailure:
    with pytest.raises(CalendarFeedError) as caught:
        call()
    return caught.value.reason


def test_webcal_is_read_as_https_and_other_schemes_are_refused() -> None:
    assert normalize_feed_url(" webcal://calendar.example.com/a.ics ") == "https://calendar.example.com/a.ics"
    assert _reason(lambda: normalize_feed_url("http://calendar.example.com/a.ics")) == FeedFailure.INVALID_URL
    assert _reason(lambda: normalize_feed_url("file:///etc/passwd")) == FeedFailure.INVALID_URL
    assert _reason(lambda: normalize_feed_url("https:///a.ics")) == FeedFailure.INVALID_URL


@pytest.mark.parametrize(
    "host", ["127.0.0.1", "10.0.0.5", "192.168.1.1", "169.254.169.254", "[::1]", "::ffff:10.0.0.1", "0.0.0.0"]
)
def test_inner_addresses_are_refused(host: str) -> None:
    assert _reason(lambda: ensure_public_host(host, 443)) == FeedFailure.BLOCKED_ADDRESS


def test_a_name_resolving_to_an_inner_address_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(
        http_fetcher.socket, "getaddrinfo",
        lambda host, port, type=0: [(2, 1, 6, "", ("93.184.216.34", port)), (2, 1, 6, "", ("10.1.2.3", port))],
    )
    assert _reason(lambda: ensure_public_host("calendar.example.com", 443)) == FeedFailure.BLOCKED_ADDRESS


def test_reads_the_content() -> None:
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["ua"] = request.headers["User-Agent"]
        return httpx.Response(200, content=ICS)

    assert _fetcher(handler).fetch(PUBLIC) == ICS
    assert seen["ua"].startswith("wbs-calendar-import/")


def test_a_redirect_to_an_inner_address_is_refused() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"})

    assert _reason(lambda: _fetcher(handler).fetch(PUBLIC)) == FeedFailure.BLOCKED_ADDRESS


def test_a_redirect_to_a_public_address_is_followed() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/calendar.ics":
            return httpx.Response(301, headers={"Location": "/moved.ics"})
        return httpx.Response(200, content=ICS)

    assert _fetcher(handler).fetch(PUBLIC) == ICS


@pytest.mark.parametrize(
    ("status", "reason"),
    [(404, FeedFailure.NOT_FOUND), (410, FeedFailure.NOT_FOUND), (403, FeedFailure.FORBIDDEN), (500, FeedFailure.HTTP_ERROR)],
)
def test_http_failures_are_told_apart(status: int, reason: FeedFailure) -> None:
    assert _reason(lambda: _fetcher(lambda r: httpx.Response(status)).fetch(PUBLIC)) == reason


def test_too_large_content_is_refused(monkeypatch) -> None:
    monkeypatch.setattr(http_fetcher, "MAX_FEED_BYTES", 10)
    assert _reason(lambda: _fetcher(lambda r: httpx.Response(200, content=ICS)).fetch(PUBLIC)) == FeedFailure.TOO_LARGE


def test_connection_failures_are_unreachable() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused", request=request)

    assert _reason(lambda: _fetcher(handler).fetch(PUBLIC)) == FeedFailure.UNREACHABLE
