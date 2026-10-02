"""端末への通知（task #193 / ADR-0031）を API と送る係で通しで見る。

- 設定: 鍵の無い配備は送れない（購読も断る）。種類ごとの入り / 切り
- 購読: 登録・一覧・この端末へ予定の通知を送るか・外す。他人の購読は見えない・触れない
- 送る係: 時刻の来た通知を本人の端末へ 1 度だけ。他人へは送らない。鍵が無ければ送らない。
  通知サービスが「もう無い」と答えた購読は外す

日付は 2026-10-05（月）。既定の利用者は Asia/Tokyo（10:00 JST = 01:00Z）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec

from src.application.dto.auth_dto import AuthenticatedUserDTO
from src.application.ports.push_sender import DisabledPushSender, PushSender
from src.application.use_cases.push_dispatch_use_cases import DispatchReport
from src.infrastructure.database.models import PushDispatchModel, UserModel
from src.infrastructure.push.push_settings import PushSettings
from src.infrastructure.push.web_push_sender import WebPushSender, b64url
from src.presentation.api import push_dispatch
from src.presentation.api.dependencies import get_current_user, get_db
from src.shared.clock import utcnow

OTHER_EMAIL = "other-push@example.com"
MY_ENDPOINT = "https://fcm.googleapis.com/fcm/send/mine"
OTHER_ENDPOINT = "https://updates.push.services.mozilla.com/wpush/v2/theirs"
ALARM_15_ONLY = {
    "enabled": True,
    "notify_15_min": True,
    "notify_5_min": False,
    "notify_1_min": False,
    "notify_at_start": False,
}


def _as_user(user_id: int, email: str) -> Callable[[], AuthenticatedUserDTO]:
    def current() -> AuthenticatedUserDTO:
        return AuthenticatedUserDTO(
            user_id=user_id, email=email, display_name=email, timezone="Asia/Tokyo", language="ja"
        )

    return current


def _browser_keys() -> dict[str, str]:
    key = ec.generate_private_key(ec.SECP256R1())
    point = key.public_key().public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
    )
    return {"p256dh": b64url(point), "auth": b64url(b"0123456789abcdef")}


class PushService:
    """通知サービスの身代わり。届いた送り先を数え、答えを決められる。"""

    def __init__(self) -> None:
        self.received: list[str] = []
        self.status = 201

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.received.append(str(request.url))
        return httpx.Response(self.status)


@pytest.fixture
def push_service() -> PushService:
    return PushService()


@pytest.fixture
def sender(tmp_path: Path, push_service: PushService) -> WebPushSender:
    path = tmp_path / "vapid.pem"
    path.write_bytes(
        ec.generate_private_key(ec.SECP256R1()).private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    return WebPushSender(
        PushSettings(str(path), "mailto:owner@example.com"),
        client=httpx.Client(transport=httpx.MockTransport(push_service)),
    )


@pytest.fixture
def push_client(client, sender):
    client.app.state.push_sender = sender
    return client


@pytest.fixture
def db(client) -> Iterator:
    session = next(client.app.dependency_overrides.get(get_db, get_db)())
    try:
        yield session
    finally:
        session.close()


@pytest.fixture
def other_user_id(db) -> int:
    user = UserModel(email=OTHER_EMAIL, display_name="他人")
    db.add(user)
    db.flush()
    user_id = user.id
    db.commit()
    return user_id


def _subscribe(client, endpoint: str = MY_ENDPOINT, label: str = "Chrome") -> dict:
    res = client.post(
        "/api/push/subscriptions", json={"endpoint": endpoint, "keys": _browser_keys(), "label": label}
    )
    assert res.status_code == 201, res.text
    return res.json()


def _subscribe_as_other(client, other_user_id: int, endpoint: str = OTHER_ENDPOINT) -> dict:
    client.app.dependency_overrides[get_current_user] = _as_user(other_user_id, OTHER_EMAIL)
    try:
        return _subscribe(client, endpoint, "Firefox")
    finally:
        client.app.dependency_overrides.pop(get_current_user, None)


@pytest.fixture
def dispatch(monkeypatch) -> Callable[[PushSender, datetime], DispatchReport]:
    """送る係の 1 周回（``push_dispatch.dispatch_once`` そのものを、時刻を決めて）。"""

    def run(sender: PushSender, now: datetime) -> DispatchReport:
        monkeypatch.setattr(push_dispatch, "utcnow", lambda: now)
        return push_dispatch.dispatch_once(sender)

    return run


def _event(client, start: str = "2026-10-05T01:00:00Z", **fields) -> dict:
    body = {"title": "設計レビュー", "start": start, "duration_minutes": 60, "alarm": ALARM_15_ONLY, **fields}
    res = client.post("/api/calendar/events", json=body)
    assert res.status_code == 201, res.text
    return res.json()


FIFTEEN_BEFORE = datetime(2026, 10, 5, 0, 45, 10)


# ── 設定 ────────────────────────────────────────────────────────────────


def test_without_the_key_push_is_off_and_subscriptions_are_refused(client) -> None:
    assert client.get("/api/push/config").json() == {"enabled": False, "public_key": None}
    res = client.post(
        "/api/push/subscriptions", json={"endpoint": MY_ENDPOINT, "keys": _browser_keys()}
    )
    assert res.status_code == 409
    assert client.get("/api/push/subscriptions").json() == []


def test_with_the_key_the_public_key_is_handed_out(push_client, sender) -> None:
    body = push_client.get("/api/push/config").json()
    assert body == {"enabled": True, "public_key": sender.public_key()}


def test_preferences_default_to_all_on_and_can_be_changed_one_by_one(client) -> None:
    assert client.get("/api/push/preferences").json() == {
        "event_alarm": True,
        "routine_start": True,
        "timer_left_running": True,
        "closing_due": True,
        "timer_left_running_hours": 4,
    }
    res = client.put("/api/push/preferences", json={"closing_due": False, "timer_left_running_hours": 6})
    assert res.status_code == 200, res.text
    assert res.json()["closing_due"] is False
    assert res.json()["event_alarm"] is True
    assert client.get("/api/push/preferences").json()["timer_left_running_hours"] == 6
    assert client.put("/api/push/preferences", json={"timer_left_running_hours": 0}).status_code == 422
    assert client.put("/api/push/preferences", json={"timer_left_running_hours": 25}).status_code == 422


# ── 購読 ────────────────────────────────────────────────────────────────


def test_subscriptions_are_listed_changed_and_removed(push_client) -> None:
    created = _subscribe(push_client)
    assert created["label"] == "Chrome"
    assert created["receives_calendar"] is True
    assert created["endpoint"] == MY_ENDPOINT
    # 同じ端末から登録し直しても 1 件のまま
    again = _subscribe(push_client, label="Chrome (PWA)")
    assert again["id"] == created["id"]
    assert [s["label"] for s in push_client.get("/api/push/subscriptions").json()] == ["Chrome (PWA)"]

    res = push_client.patch(f"/api/push/subscriptions/{created['id']}", json={"receives_calendar": False})
    assert res.status_code == 200, res.text
    assert res.json()["receives_calendar"] is False

    assert push_client.delete(f"/api/push/subscriptions/{created['id']}").status_code == 204
    assert push_client.get("/api/push/subscriptions").json() == []
    assert push_client.delete(f"/api/push/subscriptions/{created['id']}").status_code == 404


@pytest.mark.parametrize(
    "endpoint",
    ["http://fcm.googleapis.com/x", "https://10.0.0.1/x", "https://example.com/x", "https://localhost/x"],
)
def test_only_push_service_endpoints_are_accepted(push_client, endpoint: str) -> None:
    res = push_client.post(
        "/api/push/subscriptions", json={"endpoint": endpoint, "keys": _browser_keys()}
    )
    assert res.status_code == 422


def test_broken_browser_keys_are_refused(push_client) -> None:
    res = push_client.post(
        "/api/push/subscriptions",
        json={"endpoint": MY_ENDPOINT, "keys": {"p256dh": "abc", "auth": "abc"}},
    )
    assert res.status_code == 422


def test_someone_elses_subscription_cannot_be_seen_or_touched(push_client, other_user_id) -> None:
    theirs = _subscribe_as_other(push_client, other_user_id)
    assert push_client.get("/api/push/subscriptions").json() == []
    assert push_client.patch(f"/api/push/subscriptions/{theirs['id']}", json={"receives_calendar": False}).status_code == 404
    assert push_client.delete(f"/api/push/subscriptions/{theirs['id']}").status_code == 404


def test_a_device_signed_in_by_someone_else_becomes_theirs(push_client, other_user_id) -> None:
    mine = _subscribe(push_client, MY_ENDPOINT)
    theirs = _subscribe_as_other(push_client, other_user_id, MY_ENDPOINT)
    assert theirs["id"] == mine["id"]
    assert push_client.get("/api/push/subscriptions").json() == []


# ── 送る係 ──────────────────────────────────────────────────────────────


def test_a_due_alarm_is_sent_once_to_the_owners_devices_only(push_client, sender, push_service, db, dispatch, other_user_id) -> None:
    event = _event(push_client)
    _subscribe(push_client)
    _subscribe_as_other(push_client, other_user_id)

    report = dispatch(sender, FIFTEEN_BEFORE)
    assert (report.notices, report.delivered) == (1, 1)
    assert push_service.received == [MY_ENDPOINT]

    # 次の周回（まだ送れる時刻の内）でも 2 度は送らない
    assert dispatch(sender, FIFTEEN_BEFORE + timedelta(minutes=1)).notices == 0
    assert push_service.received == [MY_ENDPOINT]
    [record] = db.query(PushDispatchModel).all()
    assert (record.kind, record.notice_key) == ("event_alarm", f"{event['id']}:2026-10-05T01:00:00Z:15")


def test_nothing_is_sent_before_the_time_or_after_the_grace(push_client, sender, push_service, db, dispatch) -> None:
    _event(push_client)
    _subscribe(push_client)
    assert dispatch(sender, FIFTEEN_BEFORE - timedelta(minutes=1)).notices == 0
    assert dispatch(sender, FIFTEEN_BEFORE + timedelta(minutes=5)).notices == 0
    assert push_service.received == []


def test_without_the_key_nothing_is_sent_or_recorded(push_client, push_service, db, dispatch) -> None:
    _event(push_client)
    _subscribe(push_client)
    report = dispatch(DisabledPushSender(), FIFTEEN_BEFORE)
    assert report.skipped
    assert push_service.received == []
    assert db.query(PushDispatchModel).count() == 0


def test_turned_off_kinds_and_devices_left_to_the_timer_app_get_no_alarm(push_client, sender, push_service, db, dispatch) -> None:
    _event(push_client)
    device = _subscribe(push_client)
    push_client.put("/api/push/preferences", json={"event_alarm": False})
    assert dispatch(sender, FIFTEEN_BEFORE).notices == 0

    push_client.put("/api/push/preferences", json={"event_alarm": True})
    push_client.patch(f"/api/push/subscriptions/{device['id']}", json={"receives_calendar": False})
    assert dispatch(sender, FIFTEEN_BEFORE).notices == 0
    assert push_service.received == []


def test_a_timer_left_running_is_sent_even_to_devices_left_to_the_timer_app(push_client, sender, push_service, db, dispatch) -> None:
    device = _subscribe(push_client)
    push_client.patch(f"/api/push/subscriptions/{device['id']}", json={"receives_calendar": False})
    started = utcnow() - timedelta(hours=5)
    res = push_client.post("/api/time-entries/start", json={"at": started.isoformat() + "Z"})
    assert res.status_code in (200, 201), res.text

    now = utcnow()
    assert dispatch(sender, now).notices == 1
    assert dispatch(sender, now + timedelta(minutes=30)).notices == 0
    assert push_service.received == [MY_ENDPOINT]


def test_a_gone_subscription_is_removed(push_client, sender, push_service, db, dispatch) -> None:
    _event(push_client)
    _subscribe(push_client)
    push_service.status = 410
    report = dispatch(sender, FIFTEEN_BEFORE)
    assert report.gone == 1
    assert push_client.get("/api/push/subscriptions").json() == []


def test_the_dispatcher_does_nothing_without_subscriptions(push_client, sender, push_service, db, dispatch) -> None:
    _event(push_client)
    assert dispatch(sender, FIFTEEN_BEFORE).notices == 0
    assert push_service.received == []


def test_the_worker_is_not_started_without_the_key() -> None:
    assert push_dispatch.start_push_dispatch_worker(DisabledPushSender()) is None
