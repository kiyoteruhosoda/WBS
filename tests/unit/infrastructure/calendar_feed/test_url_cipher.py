"""購読する URL を封じる（task #196 / ADR-0037）。"""

from __future__ import annotations

import base64

import pytest

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure, NoFeedUrlCipher
from src.infrastructure.calendar_feed.url_cipher import (
    KEY_FILE_ENV,
    AesGcmFeedUrlCipher,
    decode_key,
    load_feed_url_cipher,
)

KEY = bytes(range(32))
URL = "https://calendar.google.com/calendar/ical/me%40example.com/private-0123456789abcdef/basic.ics"


def test_sealed_url_opens_and_does_not_contain_the_url() -> None:
    cipher = AesGcmFeedUrlCipher(KEY)
    sealed = cipher.seal(URL)
    assert "private-0123456789abcdef" not in sealed and sealed.startswith("v1:")
    assert cipher.open(sealed) == URL
    assert cipher.seal(URL) != sealed  # 毎回違う nonce


def test_another_key_or_tampering_cannot_open() -> None:
    sealed = AesGcmFeedUrlCipher(KEY).seal(URL)
    other = AesGcmFeedUrlCipher(bytes(32))
    for attempt in (lambda: other.open(sealed), lambda: AesGcmFeedUrlCipher(KEY).open(sealed[:-4] + "AAAA")):
        with pytest.raises(CalendarFeedError) as caught:
            attempt()
        assert caught.value.reason == FeedFailure.SUBSCRIPTION_UNAVAILABLE


def test_key_text_is_base64_or_hex() -> None:
    assert decode_key(base64.b64encode(KEY).decode() + "\n") == KEY
    assert decode_key(KEY.hex()) == KEY
    assert decode_key("short") is None
    assert decode_key(base64.b64encode(b"x" * 16).decode()) is None


def test_without_a_key_file_there_is_no_subscription(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv(KEY_FILE_ENV, raising=False)
    assert isinstance(load_feed_url_cipher(), NoFeedUrlCipher)
    broken = tmp_path / "key"
    broken.write_text("not a key")
    monkeypatch.setenv(KEY_FILE_ENV, str(broken))
    assert not load_feed_url_cipher().available
    good = tmp_path / "good"
    good.write_text(base64.b64encode(KEY).decode())
    monkeypatch.setenv(KEY_FILE_ENV, str(good))
    assert load_feed_url_cipher().available
