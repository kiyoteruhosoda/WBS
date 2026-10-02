"""購読する URL を封じる（AES-GCM。ADR-0037）。

⚠ **鍵は値ではなく場所で持つ**（``CALENDAR_FEED_KEY_FILE``）。中身は 32 バイトの鍵を base64 か 16 進で
書いたもの（``openssl rand -base64 32`` の出力）。空・読めない・長さが違えば購読はできない
（1 回だけの URL の読み込みとファイルはできる）。

DB（とその退避）だけが漏れても URL は読めない——鍵は別の場所（k8s の Secret）にある。
鍵を替えると、封じた URL は開けなくなる（購読は ``subscription_unavailable`` で失敗し、入れ直しが要る）。
"""

from __future__ import annotations

import base64
import binascii
import logging
import os
import secrets

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from src.application.ports.calendar_feed import CalendarFeedError, FeedFailure, NoFeedUrlCipher

logger = logging.getLogger(__name__)

KEY_FILE_ENV = "CALENDAR_FEED_KEY_FILE"
_VERSION = "v1"
_AAD = b"wbs-calendar-feed-url"
_NONCE_BYTES = 12


class AesGcmFeedUrlCipher:
    def __init__(self, key: bytes) -> None:
        if len(key) != 32:
            raise ValueError("the calendar feed key must be 32 bytes")
        self._aead = AESGCM(key)

    @property
    def available(self) -> bool:
        return True

    def seal(self, url: str) -> str:
        nonce = secrets.token_bytes(_NONCE_BYTES)
        sealed = self._aead.encrypt(nonce, url.encode("utf-8"), _AAD)
        return f"{_VERSION}:{base64.urlsafe_b64encode(nonce + sealed).decode('ascii')}"

    def open(self, sealed: str) -> str:
        version, _, body = sealed.partition(":")
        try:
            if version != _VERSION:
                raise ValueError(version)
            raw = base64.urlsafe_b64decode(body.encode("ascii"))
            plain = self._aead.decrypt(raw[:_NONCE_BYTES], raw[_NONCE_BYTES:], _AAD)
        except (ValueError, InvalidTag, binascii.Error) as exc:
            raise CalendarFeedError(FeedFailure.SUBSCRIPTION_UNAVAILABLE) from exc
        return plain.decode("utf-8")


def decode_key(text: str) -> bytes | None:
    """鍵のファイルの中身（base64 か 16 進）を 32 バイトにする。読めなければ ``None``。"""
    value = text.strip()
    if len(value) == 64:
        try:
            return bytes.fromhex(value)
        except ValueError:
            pass
    try:
        key = base64.b64decode(value, validate=True)
    except (ValueError, binascii.Error):
        return None
    return key if len(key) == 32 else None


def load_feed_url_cipher() -> AesGcmFeedUrlCipher | NoFeedUrlCipher:
    """``CALENDAR_FEED_KEY_FILE`` の鍵で封じる。無い・読めなければ封じない（購読はできない）。"""
    path = os.getenv(KEY_FILE_ENV, "").strip()
    if not path:
        return NoFeedUrlCipher()
    try:
        with open(path, encoding="utf-8") as handle:
            key = decode_key(handle.read())
    except OSError:
        key = None
    if key is None:
        logger.warning(
            "カレンダーの購読の鍵を読めません（購読はできません）",
            extra={"event": "calendar.import.key_unreadable"},
        )
        return NoFeedUrlCipher()
    return AesGcmFeedUrlCipher(key)


__all__ = ["KEY_FILE_ENV", "AesGcmFeedUrlCipher", "decode_key", "load_feed_url_cipher"]
