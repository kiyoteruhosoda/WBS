"""端末への通知を Web Push で送る（task #193 / ADR-0031）。

雛形 fastapitemplate の ``WebPushSender``（ADR-0047）と同じ振る舞いで、``pywebpush`` を入れずに
既にある依存（``cryptography``〈``pyjwt[crypto]`` が連れてくる〉・``pyjwt``・``httpx``）で書く:

- 中身の暗号化は RFC 8291（``aes128gcm``。RFC 8188 の 1 レコード）
- 送り手の名乗りは RFC 8292（VAPID。ES256 の JWT と公開鍵を ``Authorization: vapid t=…, k=…``）

⚠ **秘密鍵は値ではなく場所で持つ**（``WEB_PUSH_VAPID_PRIVATE_KEY_FILE``。P-256 の PEM）。
読めなければ「送れない」として記録に残し、**鍵を作り直さない**（作り直すと配った公開鍵と食い違い、
すべての購読が静かに届かなくなる）。⚠ 鍵を替えると、いまある購読はすべて届かなくなる
（利用者が設定画面で購読し直すまで出ない）。
"""

from __future__ import annotations

import base64
import json
import logging
import os
import struct
from datetime import UTC, timedelta
from pathlib import Path
from urllib.parse import urlsplit

import httpx
import jwt
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.application.ports.push_sender import PushOutcome
from src.domain.entities.push_subscription import PushSubscription
from src.domain.value_objects.push_notice import PushNotice
from src.infrastructure.push.push_settings import PushSettings
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

#: 端末が電源を切っているあいだ、通知サービスに預けておく時間（秒）。予定の通知は遅れると
#: 意味が無いので短く取る（締め・止め忘れも、数時間後に出ても画面で気付ける）。
TTL_SECONDS = 60 * 60
#: 通知サービス 1 件あたりの待ち時間（秒）
TIMEOUT_SECONDS = 10
#: VAPID の JWT の期限（RFC 8292 は 24 時間まで）
_VAPID_LIFETIME = timedelta(hours=12)
#: 1 レコードの大きさ（RFC 8188）。中身は 1 レコードに収める
_RECORD_SIZE = 4096
#: 中身の上限（レコード − 認証タグ 16 − 区切り 1 − 余白）。超えたら本文を切る
_MAX_PLAINTEXT = 3000
#: 通知サービスが「その購読はもう無い」と答える状態
_GONE_STATUSES = frozenset({404, 410})


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _point(public_key: ec.EllipticCurvePublicKey) -> bytes:
    return public_key.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def encrypt_payload(
    plaintext: bytes,
    ua_public: bytes,
    auth_secret: bytes,
    *,
    sender_key: ec.EllipticCurvePrivateKey | None = None,
    salt: bytes | None = None,
) -> bytes:
    """RFC 8291 の ``aes128gcm`` で包んだ本文（ヘッダ ＋ 1 レコード）。

    ``sender_key`` / ``salt`` は試験のためだけに渡せる（既定は送るたびに作り直す）。
    """
    sender_key = sender_key or ec.generate_private_key(ec.SECP256R1())
    salt = salt or os.urandom(16)
    as_public = _point(sender_key.public_key())
    ua_key = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_public)
    shared = sender_key.exchange(ec.ECDH(), ua_key)
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    # 最後のレコードの区切りは 0x02（RFC 8188）
    record = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    header = salt + struct.pack("!IB", _RECORD_SIZE, len(as_public)) + as_public
    return header + record


def payload_of(notice: PushNotice) -> bytes:
    """Service Worker（``frontend/src/serviceWorker/pushNotice.ts``）が読む中身。"""
    body = notice.body
    while True:
        data = json.dumps(
            {"title": notice.title, "body": body, "url": notice.url, "tag": notice.tag, "kind": notice.kind.value},
            ensure_ascii=False,
        ).encode("utf-8")
        if len(data) <= _MAX_PLAINTEXT or not body:
            return data
        body = body[: len(body) // 2]


class WebPushSender:
    """``PushSender`` の実装。"""

    def __init__(self, settings: PushSettings, client: httpx.Client | None = None) -> None:
        self._settings = settings
        self._client = client
        self._key: ec.EllipticCurvePrivateKey | None = None
        #: 読めなかったことを 1 度だけ記録する（送る係は 60 秒ごとに来る）
        self._warned = False

    @property
    def enabled(self) -> bool:
        return self._settings.configured and self._load() is not None

    def _load(self) -> ec.EllipticCurvePrivateKey | None:
        if not self._settings.configured:
            return None
        if self._key is None:
            path = self._settings.vapid_private_key_file
            try:
                key = serialization.load_pem_private_key(Path(path).read_bytes(), password=None)
            except (OSError, ValueError, TypeError):
                key = None
            if not isinstance(key, ec.EllipticCurvePrivateKey) or not isinstance(key.curve, ec.SECP256R1):
                if not self._warned:
                    self._warned = True
                    # パスは秘密ではないので出してよい（どこを直せばよいかが分かる）。中身は出さない
                    logger.warning(
                        "Web Push の鍵（P-256 の PEM）を読めません。端末への通知は送りません",
                        extra={"event": "push.key_unreadable", "path": path},
                    )
                return None
            self._key = key
        return self._key

    def public_key(self) -> str | None:
        key = self._load()
        return b64url(_point(key.public_key())) if key is not None else None

    def _vapid_header(self, endpoint: str, key: ec.EllipticCurvePrivateKey) -> str:
        parts = urlsplit(endpoint)
        expires = utcnow().replace(tzinfo=UTC) + _VAPID_LIFETIME
        token = jwt.encode(
            {"aud": f"{parts.scheme}://{parts.netloc}", "exp": int(expires.timestamp()), "sub": self._settings.subject},
            key,
            algorithm="ES256",
            headers={"typ": "JWT"},
        )
        return f"vapid t={token}, k={b64url(_point(key.public_key()))}"

    def send(self, subscription: PushSubscription, notice: PushNotice) -> PushOutcome:
        key = self._load()
        if key is None:
            return PushOutcome.FAILED
        try:
            body = encrypt_payload(payload_of(notice), subscription.p256dh_bytes(), subscription.auth_bytes())
        except ValueError:
            # 端末の鍵が壊れている（登録の検査をすり抜けた）。もう届かないので外す
            return PushOutcome.GONE
        headers = {
            "Authorization": self._vapid_header(subscription.endpoint, key),
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "TTL": str(TTL_SECONDS),
            "Urgency": "high",
        }
        client = self._client or httpx.Client(timeout=TIMEOUT_SECONDS)
        try:
            response = client.post(subscription.endpoint, content=body, headers=headers)
        except httpx.HTTPError as exc:
            logger.warning(
                "Web Push を送れませんでした",
                extra={"event": "push.failed", "reason": type(exc).__name__},
            )
            return PushOutcome.FAILED
        finally:
            if self._client is None:
                client.close()
        if response.status_code in _GONE_STATUSES:
            return PushOutcome.GONE
        if response.is_success:
            return PushOutcome.DELIVERED
        logger.warning(
            "Web Push を送れませんでした",
            extra={"event": "push.failed", "status": response.status_code},
        )
        return PushOutcome.FAILED


__all__ = ["WebPushSender", "b64url", "encrypt_payload", "payload_of"]
