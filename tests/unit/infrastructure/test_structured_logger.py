"""ログの設定（task #495）。取り込んだカレンダーの URL を、通信の道具の標準の行でログに出さない。"""

from __future__ import annotations

import logging
from collections.abc import Iterator

import httpx
import pytest

from src.application.ports.calendar_feed import CalendarFeedError
from src.infrastructure.calendar_feed.http_fetcher import HttpCalendarFeedFetcher
from src.infrastructure.logging.structured_logger import QUIET_URL_LOGGERS, setup_logging

# Google の「iCal 形式の非公開アドレス」の形（private- の部分を知っていれば誰でも読める）
SECRET_PATH = "/calendar/ical/someone%40example.com/private-0123456789abcdef/basic.ics"
SECRET_QUERY = "token=s3cr3t"
URL = f"https://93.184.216.34{SECRET_PATH}?{SECRET_QUERY}"
ICS = b"BEGIN:VCALENDAR\r\nEND:VCALENDAR\r\n"


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.DEBUG)
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(record.getMessage())


@pytest.fixture
def collected(tmp_path) -> Iterator[_Collect]:
    root = logging.getLogger()
    saved_handlers, saved_level = root.handlers[:], root.level
    saved_levels = {name: logging.getLogger(name).level for name in (*QUIET_URL_LOGGERS, "access")}
    setup_logging(log_dir=str(tmp_path))
    collect = _Collect()
    root.addHandler(collect)
    try:
        yield collect
    finally:
        root.handlers[:] = saved_handlers
        root.setLevel(saved_level)
        for name, level in saved_levels.items():
            logging.getLogger(name).setLevel(level)


def _fetch(handler) -> None:
    HttpCalendarFeedFetcher(transport=httpx.MockTransport(handler)).fetch(URL)


def _assert_no_url(lines: list[str]) -> None:
    joined = "\n".join(lines)
    assert "private-0123456789abcdef" not in joined
    assert SECRET_QUERY not in joined


def test_reading_a_feed_does_not_log_its_url(collected: _Collect) -> None:
    _fetch(lambda request: httpx.Response(200, content=ICS))
    _assert_no_url(collected.lines)


@pytest.mark.parametrize("status", [404, 403, 500])
def test_a_failed_read_does_not_log_its_url(collected: _Collect, status: int) -> None:
    with pytest.raises(CalendarFeedError):
        _fetch(lambda request: httpx.Response(status))
    _assert_no_url(collected.lines)


def test_a_redirect_does_not_log_either_url(collected: _Collect) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == SECRET_PATH:
            return httpx.Response(302, headers={"Location": "/moved/private-0123456789abcdef.ics"})
        return httpx.Response(200, content=ICS)

    _fetch(handler)
    _assert_no_url(collected.lines)


def test_http_client_warnings_still_reach_the_log(collected: _Collect) -> None:
    logging.getLogger("httpx").warning("kept")
    assert "kept" in collected.lines
