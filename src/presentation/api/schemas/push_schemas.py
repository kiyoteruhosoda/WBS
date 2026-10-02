"""端末への通知（Web Push）の API の形（task #193 / ADR-0031）。"""

from __future__ import annotations

from pydantic import BaseModel, Field

from src.domain.value_objects.push_preferences import (
    MAX_TIMER_LEFT_RUNNING_HOURS,
    MIN_TIMER_LEFT_RUNNING_HOURS,
)
from src.presentation.api.schemas.types import UtcDatetime


class PushConfigResponse(BaseModel):
    #: この配備が端末への通知を送れるか（鍵が無ければ false。購読も受け取らない）
    enabled: bool
    #: ブラウザの ``PushManager.subscribe`` に渡す ``applicationServerKey``（base64url）
    public_key: str | None


class PushPreferencesResponse(BaseModel):
    event_alarm: bool
    routine_start: bool
    timer_left_running: bool
    closing_due: bool
    timer_left_running_hours: int


class PushPreferencesUpdateRequest(BaseModel):
    """省いた欄は今のまま。"""

    event_alarm: bool | None = None
    routine_start: bool | None = None
    timer_left_running: bool | None = None
    closing_due: bool | None = None
    timer_left_running_hours: int | None = Field(
        default=None, ge=MIN_TIMER_LEFT_RUNNING_HOURS, le=MAX_TIMER_LEFT_RUNNING_HOURS
    )


class PushSubscriptionKeys(BaseModel):
    p256dh: str = Field(max_length=128)
    auth: str = Field(max_length=64)


class PushSubscriptionCreateRequest(BaseModel):
    """ブラウザの ``PushSubscription.toJSON()`` の ``endpoint`` / ``keys`` ＋ 端末の名前。"""

    endpoint: str = Field(max_length=2048)
    keys: PushSubscriptionKeys
    label: str = Field(default="", max_length=200)


class PushSubscriptionUpdateRequest(BaseModel):
    receives_calendar: bool


class PushSubscriptionResponse(BaseModel):
    id: int
    #: 送り先。画面が「この端末の購読」を見分けるのに使う（本人にだけ返す）
    endpoint: str
    label: str
    receives_calendar: bool
    created_at: UtcDatetime | None
    last_sent_at: UtcDatetime | None
