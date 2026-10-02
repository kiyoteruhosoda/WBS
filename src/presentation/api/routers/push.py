"""端末への通知（Web Push）の設定（task #193 / ADR-0031）。

- ``GET /push/config``: 送れる配備か・ブラウザの購読に渡す公開鍵
- ``GET`` / ``PUT /push/preferences``: 種類ごとの入り / 切り・止め忘れと見なす時間
- ``GET`` / ``POST /push/subscriptions``・``PATCH`` / ``DELETE /push/subscriptions/{id}``:
  端末ごとの購読（一覧・登録・予定の通知をこの端末へ送るか・外す）

どれも Web のセッション Cookie だけ（打刻アプリは自分で鳴らす。ADR-0031 の 3）。送るのは API の定期処理。
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Request, Response, status

from src.application.ports.push_sender import PushSender
from src.application.use_cases.push_settings_use_cases import PushSettingsUseCases
from src.domain.entities.push_subscription import PushSubscription
from src.domain.value_objects.push_preferences import PushPreferences
from src.infrastructure.repositories.push_preferences_repository import (
    SqlAlchemyPushPreferencesRepository,
)
from src.infrastructure.repositories.push_subscription_repository import (
    SqlAlchemyPushSubscriptionRepository,
)
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.push_schemas import (
    PushConfigResponse,
    PushPreferencesResponse,
    PushPreferencesUpdateRequest,
    PushSubscriptionCreateRequest,
    PushSubscriptionResponse,
    PushSubscriptionUpdateRequest,
)

router = APIRouter(prefix="/push", tags=["push"])


def get_push_sender(request: Request) -> PushSender:
    return request.app.state.push_sender


def get_push_settings_use_cases(
    db: DbDep, sender: Annotated[PushSender, Depends(get_push_sender)]
) -> PushSettingsUseCases:
    return PushSettingsUseCases(
        SqlAlchemyPushSubscriptionRepository(db),
        SqlAlchemyPushPreferencesRepository(db),
        sender,
        db,
    )


PushSettingsDep = Annotated[PushSettingsUseCases, Depends(get_push_settings_use_cases)]


def _preferences(p: PushPreferences) -> PushPreferencesResponse:
    return PushPreferencesResponse(
        event_alarm=p.event_alarm,
        routine_start=p.routine_start,
        timer_left_running=p.timer_left_running,
        closing_due=p.closing_due,
        timer_left_running_hours=p.timer_left_running_hours,
    )


def _subscription(s: PushSubscription) -> PushSubscriptionResponse:
    assert s.id is not None
    return PushSubscriptionResponse(
        id=s.id,
        endpoint=s.endpoint,
        label=s.label,
        receives_calendar=s.receives_calendar,
        created_at=s.created_at,
        last_sent_at=s.last_sent_at,
    )


@router.get("/config", response_model=PushConfigResponse)
def get_config(uc: PushSettingsDep, _user: CurrentUserDep) -> PushConfigResponse:
    config = uc.config()
    return PushConfigResponse(enabled=config.enabled, public_key=config.public_key)


@router.get("/preferences", response_model=PushPreferencesResponse)
def get_preferences(uc: PushSettingsDep, user: CurrentUserDep) -> PushPreferencesResponse:
    return _preferences(uc.get_preferences(user.user_id))


@router.put("/preferences", response_model=PushPreferencesResponse)
def update_preferences(
    body: PushPreferencesUpdateRequest, uc: PushSettingsDep, user: CurrentUserDep
) -> PushPreferencesResponse:
    return _preferences(
        uc.update_preferences(
            user.user_id,
            event_alarm=body.event_alarm,
            routine_start=body.routine_start,
            timer_left_running=body.timer_left_running,
            closing_due=body.closing_due,
            timer_left_running_hours=body.timer_left_running_hours,
        )
    )


@router.get("/subscriptions", response_model=list[PushSubscriptionResponse])
def list_subscriptions(uc: PushSettingsDep, user: CurrentUserDep) -> list[PushSubscriptionResponse]:
    return [_subscription(s) for s in uc.list_subscriptions(user.user_id)]


@router.post(
    "/subscriptions", response_model=PushSubscriptionResponse, status_code=status.HTTP_201_CREATED
)
def subscribe(
    body: PushSubscriptionCreateRequest, uc: PushSettingsDep, user: CurrentUserDep
) -> PushSubscriptionResponse:
    return _subscription(
        uc.subscribe(
            user.user_id,
            endpoint=body.endpoint,
            p256dh=body.keys.p256dh,
            auth=body.keys.auth,
            label=body.label,
        )
    )


@router.patch("/subscriptions/{subscription_id}", response_model=PushSubscriptionResponse)
def update_subscription(
    subscription_id: int,
    body: PushSubscriptionUpdateRequest,
    uc: PushSettingsDep,
    user: CurrentUserDep,
) -> PushSubscriptionResponse:
    return _subscription(
        uc.set_receives_calendar(user.user_id, subscription_id, body.receives_calendar)
    )


@router.delete("/subscriptions/{subscription_id}", status_code=status.HTTP_204_NO_CONTENT)
def unsubscribe(subscription_id: int, uc: PushSettingsDep, user: CurrentUserDep) -> Response:
    uc.unsubscribe(user.user_id, subscription_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
