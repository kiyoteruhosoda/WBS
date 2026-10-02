"""購読の受け取り（task #193 / ADR-0031）。⚠ 送り先は通知サービスの https だけ（SSRF を防ぐ）。"""

from __future__ import annotations

import base64
from datetime import datetime

import pytest

from src.domain.entities.push_subscription import PushSubscription, validate_endpoint
from src.domain.exceptions import ValidationError
from src.domain.value_objects.push_kind import PushKind
from src.domain.value_objects.push_preferences import PushPreferences

P256DH = base64.urlsafe_b64encode(b"\x04" + b"\x01" * 64).decode().rstrip("=")
AUTH = base64.urlsafe_b64encode(b"\x02" * 16).decode().rstrip("=")
NOW = datetime(2026, 10, 2, 0, 0)


@pytest.mark.parametrize(
    "endpoint",
    [
        "https://fcm.googleapis.com/fcm/send/abc",
        "https://updates.push.services.mozilla.com/wpush/v2/abc",
        "https://wns2-par02p.notify.windows.com/w/?token=abc",
        "https://web.push.apple.com/abc",
    ],
)
def test_push_services_of_the_major_browsers_are_accepted(endpoint: str) -> None:
    assert validate_endpoint(endpoint) == endpoint


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://fcm.googleapis.com/fcm/send/abc",
        "https://127.0.0.1/x",
        "https://10.0.0.5/x",
        "https://wbs-api.wbs-prod.svc.cluster.local/x",
        "https://evil.example.com/fcm.googleapis.com",
        "https://fcm.googleapis.com.evil.example/x",
        "https://notfcm.googleapis.com/x",
        "https://fcm.googleapis.com:8443/x",
        "https://user:pass@fcm.googleapis.com/x",
        "",
        "https://fcm.googleapis.com/" + "a" * 2100,
    ],
)
def test_other_endpoints_are_refused(endpoint: str) -> None:
    with pytest.raises(ValidationError):
        validate_endpoint(endpoint)


def test_register_checks_the_browser_keys() -> None:
    subscription = PushSubscription.register(
        user_id=1, endpoint="https://fcm.googleapis.com/x", p256dh=P256DH, auth=AUTH, label=" Chrome ", now=NOW
    )
    assert subscription.label == "Chrome"
    assert subscription.receives_calendar
    with pytest.raises(ValidationError):
        PushSubscription.register(user_id=1, endpoint="https://fcm.googleapis.com/x", p256dh=AUTH, auth=AUTH, label="", now=NOW)
    with pytest.raises(ValidationError):
        PushSubscription.register(user_id=1, endpoint="https://fcm.googleapis.com/x", p256dh=P256DH, auth=P256DH, label="", now=NOW)
    with pytest.raises(ValidationError):
        PushSubscription.register(user_id=1, endpoint="https://fcm.googleapis.com/x", p256dh="***", auth=AUTH, label="", now=NOW)


def test_preferences_default_to_all_on_and_bound_the_hours() -> None:
    preferences = PushPreferences()
    assert all(preferences.allows(kind) for kind in PushKind)
    assert preferences.timer_left_running_hours == 4
    assert preferences.changed(closing_due=False, timer_left_running_hours=None) == PushPreferences(closing_due=False)
    for hours in (0, 25):
        with pytest.raises(ValidationError):
            PushPreferences(timer_left_running_hours=hours)


def test_only_calendar_kinds_can_be_left_to_the_timer_app() -> None:
    assert {k for k in PushKind if k.comes_from_calendar} == {PushKind.EVENT_ALARM, PushKind.ROUTINE_START}
