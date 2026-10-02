"""Web Push の送り口（task #193 / ADR-0031）。暗号化（RFC 8291）・VAPID（RFC 8292）・答えの読み方・
鍵が無い / 読めないときは送らないこと。"""

from __future__ import annotations

import base64
import json
import struct
from pathlib import Path

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from src.application.ports.push_sender import PushOutcome
from src.domain.entities.push_subscription import PushSubscription
from src.domain.value_objects.push_kind import PushKind
from src.domain.value_objects.push_notice import PushNotice
from src.infrastructure.push.push_settings import PushSettings
from src.infrastructure.push.web_push_sender import WebPushSender, b64url, encrypt_payload

ENDPOINT = "https://fcm.googleapis.com/fcm/send/abc:def"
NOTICE = PushNotice(
    user_id=1, kind=PushKind.EVENT_ALARM, key="12:2026-10-05T01:00:00Z:15",
    title="設計レビュー", body="15 分後に始まります", url="/calendar",
)


def _point(key: ec.EllipticCurvePrivateKey) -> bytes:
    return key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )


def _hkdf(salt: bytes, ikm: bytes, info: bytes, length: int) -> bytes:
    return HKDF(algorithm=hashes.SHA256(), length=length, salt=salt, info=info).derive(ikm)


def _decrypt(body: bytes, ua_key: ec.EllipticCurvePrivateKey, auth_secret: bytes) -> bytes:
    """受け手（ブラウザ）の側の読み方（RFC 8291 §3.4・RFC 8188 §2.1）。"""
    salt = body[:16]
    record_size, id_length = struct.unpack("!IB", body[16:21])
    as_public = body[21 : 21 + id_length]
    record = body[21 + id_length :]
    assert record_size == 4096
    ua_public = _point(ua_key)
    shared = ua_key.exchange(
        ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_public)
    )
    ikm = _hkdf(auth_secret, shared, b"WebPush: info\x00" + ua_public + as_public, 32)
    cek = _hkdf(salt, ikm, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf(salt, ikm, b"Content-Encoding: nonce\x00", 12)
    padded = AESGCM(cek).decrypt(nonce, record, None)
    assert padded.endswith(b"\x02")
    return padded[:-1]


@pytest.fixture
def browser():
    key = ec.generate_private_key(ec.SECP256R1())
    auth_secret = b"0123456789abcdef"
    subscription = PushSubscription(
        id=1, user_id=1, endpoint=ENDPOINT, p256dh=b64url(_point(key)), auth=b64url(auth_secret), label="Chrome",
    )
    return key, auth_secret, subscription


@pytest.fixture
def vapid_file(tmp_path: Path) -> tuple[Path, ec.EllipticCurvePrivateKey]:
    key = ec.generate_private_key(ec.SECP256R1())
    path = tmp_path / "vapid.pem"
    path.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return path, key


def test_the_payload_is_encrypted_so_that_only_the_browser_can_read_it(browser) -> None:
    key, auth_secret, _ = browser
    body = encrypt_payload(b'{"title":"x"}', _point(key), auth_secret)
    assert b"title" not in body
    assert _decrypt(body, key, auth_secret) == b'{"title":"x"}'
    # 送るたびに鍵と salt を作り直す（同じ中身でも同じ暗号文にならない）
    assert encrypt_payload(b'{"title":"x"}', _point(key), auth_secret) != body


def _sender(path: Path, handler) -> WebPushSender:
    client = httpx.Client(transport=httpx.MockTransport(handler))
    return WebPushSender(PushSettings(str(path), "mailto:owner@example.com"), client=client)


def test_send_posts_an_encrypted_message_signed_with_vapid(browser, vapid_file) -> None:
    key, auth_secret, subscription = browser
    path, vapid_key = vapid_file
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201)

    sender = _sender(path, handler)
    assert sender.enabled
    assert sender.public_key() == b64url(_point(vapid_key))
    assert sender.send(subscription, NOTICE) is PushOutcome.DELIVERED

    [request] = seen
    assert str(request.url) == ENDPOINT
    assert request.headers["Content-Encoding"] == "aes128gcm"
    assert int(request.headers["TTL"]) > 0
    scheme, _, params = request.headers["Authorization"].partition(" ")
    assert scheme == "vapid"
    fields = dict(part.strip().split("=", 1) for part in params.split(","))
    assert fields["k"] == sender.public_key()
    claims = jwt.decode(fields["t"], vapid_key.public_key(), algorithms=["ES256"], audience="https://fcm.googleapis.com")
    assert claims["sub"] == "mailto:owner@example.com"

    payload = json.loads(_decrypt(request.content, key, auth_secret))
    assert payload == {
        "title": "設計レビュー",
        "body": "15 分後に始まります",
        "url": "/calendar",
        "tag": "event_alarm:12:2026-10-05T01:00:00Z:15",
        "kind": "event_alarm",
    }


@pytest.mark.parametrize(("status", "outcome"), [(404, PushOutcome.GONE), (410, PushOutcome.GONE), (500, PushOutcome.FAILED), (429, PushOutcome.FAILED)])
def test_the_answer_of_the_push_service_decides_the_outcome(browser, vapid_file, status, outcome) -> None:
    _, _, subscription = browser
    path, _ = vapid_file
    assert _sender(path, lambda _: httpx.Response(status)).send(subscription, NOTICE) is outcome


def test_a_network_error_is_a_failure_not_an_exception(browser, vapid_file) -> None:
    _, _, subscription = browser
    path, _ = vapid_file

    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("down", request=request)

    assert _sender(path, handler).send(subscription, NOTICE) is PushOutcome.FAILED


@pytest.mark.parametrize("settings", [PushSettings(), PushSettings("/run/push/vapid.pem", ""), PushSettings("", "mailto:x@example.com")])
def test_without_both_settings_nothing_is_sent(browser, settings) -> None:
    _, _, subscription = browser
    sender = WebPushSender(settings, client=httpx.Client(transport=httpx.MockTransport(lambda _: pytest.fail("sent"))))
    assert not sender.enabled
    assert sender.public_key() is None
    assert sender.send(subscription, NOTICE) is PushOutcome.FAILED


def test_an_unreadable_or_wrong_key_disables_sending_without_making_a_new_key(browser, tmp_path) -> None:
    _, _, subscription = browser
    missing = tmp_path / "missing.pem"
    sender = WebPushSender(PushSettings(str(missing), "mailto:x@example.com"))
    assert not sender.enabled
    assert sender.send(subscription, NOTICE) is PushOutcome.FAILED
    assert not missing.exists()  # ⚠ 鍵を作り直さない

    rsa_like = tmp_path / "garbage.pem"
    rsa_like.write_text("not a key")
    assert not WebPushSender(PushSettings(str(rsa_like), "mailto:x@example.com")).enabled

    other_curve = tmp_path / "p384.pem"
    other_curve.write_bytes(
        ec.generate_private_key(ec.SECP384R1()).private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()
        )
    )
    assert not WebPushSender(PushSettings(str(other_curve), "mailto:x@example.com")).enabled


def test_b64url_has_no_padding() -> None:
    assert b64url(b"\xff\xfe") == base64.urlsafe_b64encode(b"\xff\xfe").decode().rstrip("=")
