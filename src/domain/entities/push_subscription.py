"""ブラウザ・PWA の Web Push の購読 1 件（端末 1 台ぶん。task #193 / ADR-0031）。

ブラウザの ``PushManager.subscribe()`` が返す ``endpoint`` と鍵の組（``p256dh`` / ``auth``）を持つ。
同じ ``endpoint`` は 1 行だけ（同じ端末で別の人がログインし直したら、後の人の購読になる）。

⚠ **送り先（``endpoint``）は利用者が送ってくる URL で、サーバがそこへ POST する。** 内向きの
アドレスへ向けさせない（SSRF）ため、https で、ブラウザの通知サービスのホストのものだけ受け取る
（``PUSH_SERVICE_HOST_SUFFIXES``）。
"""

from __future__ import annotations

import base64
import binascii
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import urlsplit

from src.domain.exceptions import ValidationError

#: 受け取る通知サービスのホスト（完全一致か、その下のホスト）。
#: Chrome / Edge（Android 含む）= FCM、Firefox = Mozilla、Edge（Windows）= WNS、Safari = Apple。
PUSH_SERVICE_HOST_SUFFIXES = (
    "fcm.googleapis.com",
    "push.services.mozilla.com",
    "notify.windows.com",
    "push.apple.com",
)
MAX_ENDPOINT_LENGTH = 2048
MAX_LABEL_LENGTH = 100
#: ``p256dh`` は P-256 の非圧縮の点（65 バイト）、``auth`` は 16 バイト（RFC 8291）。
P256DH_LENGTH = 65
AUTH_SECRET_LENGTH = 16


def _decode_b64url(value: str, name: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))
    except (binascii.Error, ValueError) as exc:
        raise ValidationError(f"{name} must be base64url") from exc


def validate_endpoint(endpoint: str) -> str:
    endpoint = endpoint.strip()
    if not endpoint or len(endpoint) > MAX_ENDPOINT_LENGTH:
        raise ValidationError("endpoint is empty or too long")
    parts = urlsplit(endpoint)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or not host or parts.username or parts.password:
        raise ValidationError("endpoint must be an https URL")
    if parts.port not in (None, 443):
        raise ValidationError("endpoint must use the default https port")
    if not any(host == s or host.endswith(f".{s}") for s in PUSH_SERVICE_HOST_SUFFIXES):
        raise ValidationError("endpoint is not a known push service")
    return endpoint


@dataclass
class PushSubscription:
    id: int | None
    user_id: int
    endpoint: str
    p256dh: str
    auth: str
    label: str
    #: 予定から出る通知（予定の通知・定常業務の開始）をこの端末へ送るか。
    #: 打刻アプリ（wbstimer）が鳴らす端末では切る（ADR-0031 の 3）。
    receives_calendar: bool = True
    created_at: datetime | None = None
    last_sent_at: datetime | None = None

    @classmethod
    def register(
        cls,
        *,
        user_id: int,
        endpoint: str,
        p256dh: str,
        auth: str,
        label: str,
        now: datetime,
    ) -> PushSubscription:
        if len(_decode_b64url(p256dh, "p256dh")) != P256DH_LENGTH:
            raise ValidationError("p256dh must be an uncompressed P-256 point")
        if len(_decode_b64url(auth, "auth")) != AUTH_SECRET_LENGTH:
            raise ValidationError("auth must be 16 bytes")
        return cls(
            id=None,
            user_id=user_id,
            endpoint=validate_endpoint(endpoint),
            p256dh=p256dh,
            auth=auth,
            label=(label.strip() or "-")[:MAX_LABEL_LENGTH],
            created_at=now,
        )

    def p256dh_bytes(self) -> bytes:
        return _decode_b64url(self.p256dh, "p256dh")

    def auth_bytes(self) -> bytes:
        return _decode_b64url(self.auth, "auth")


__all__ = ["PUSH_SERVICE_HOST_SUFFIXES", "PushSubscription", "validate_endpoint"]
