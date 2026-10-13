"""PC の自動記録の規則（WinTrack、task #381 / ADR-0043）。

``GET ""`` と ``GET /tasks`` は PC の係（WinTrack）が assay のアクセストークンで叩く
（``AppOrWebUserDep``、ADR-0018）。編集（``/editor`` の一覧・作る・直す・消す・並べ替え）は
WBS の画面からで、Cookie だけ。照合は PC の中でするので、表題はここへ来ない。
"""

from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.tracking_rule_dto import (
    CreateTrackingRuleCommand,
    UpdateTrackingRuleCommand,
)
from src.application.dto.unset import UNSET
from src.domain.exceptions import ValidationError
from src.presentation.api.dependencies import (
    AppOrWebUserDep,
    CurrentUserDep,
    TrackingRuleUseCasesDep,
)
from src.presentation.api.schemas.tracking_rule_schemas import (
    EditableTrackingRuleResponse,
    TrackableTaskResponse,
    TrackableTasksResponse,
    TrackingRuleCreateRequest,
    TrackingRuleFeedResponse,
    TrackingRuleOrderRequest,
    TrackingRuleResponse,
    TrackingRuleUpdateRequest,
)

router = APIRouter(prefix="/tracking-rules", tags=["tracking-rules"])


@router.get("", response_model=TrackingRuleFeedResponse)
def get_tracking_rules(
    uc: TrackingRuleUseCasesDep, current_user: AppOrWebUserDep
) -> TrackingRuleFeedResponse:
    """自分の規則のうち使えるもの（タスクがあって開いている）を上からの順に。「それ以外すべて」は最後。"""
    feed = uc.feed(current_user.user_id)
    return TrackingRuleFeedResponse(
        rules=[TrackingRuleResponse.from_view(v) for v in feed.rules],
        updated_at=feed.updated_at,
    )


# ⚠ 固定の道（tasks / editor / order）は ``/{rule_id}`` より先に置く（後ろだと id として読まれて 422）。
@router.get("/tasks", response_model=TrackableTasksResponse)
def get_trackable_tasks(
    uc: TrackingRuleUseCasesDep, current_user: AppOrWebUserDep
) -> TrackableTasksResponse:
    """自分が打刻を付けられる開いているタスク。"""
    return TrackableTasksResponse(
        tasks=[TrackableTaskResponse.from_task(t) for t in uc.trackable_tasks(current_user.user_id)]
    )


@router.get("/editor", response_model=list[EditableTrackingRuleResponse])
def list_editable_tracking_rules(
    uc: TrackingRuleUseCasesDep, current_user: CurrentUserDep
) -> list[EditableTrackingRuleResponse]:
    """編集の画面の一覧。タスクが使えなくなった規則も含める。"""
    return [EditableTrackingRuleResponse.from_view(v) for v in uc.list_rules(current_user.user_id)]


@router.put("/order", response_model=list[EditableTrackingRuleResponse])
def reorder_tracking_rules(
    body: TrackingRuleOrderRequest, uc: TrackingRuleUseCasesDep, current_user: CurrentUserDep
) -> list[EditableTrackingRuleResponse]:
    views = uc.reorder(current_user.user_id, body.rule_ids)
    return [EditableTrackingRuleResponse.from_view(v) for v in views]


@router.post("", response_model=EditableTrackingRuleResponse, status_code=status.HTTP_201_CREATED)
def create_tracking_rule(
    body: TrackingRuleCreateRequest, uc: TrackingRuleUseCasesDep, current_user: CurrentUserDep
) -> EditableTrackingRuleResponse:
    command = CreateTrackingRuleCommand(
        user_id=current_user.user_id,
        task_id=body.task_id,
        app=body.app,
        title_contains=body.title_contains,
    )
    return EditableTrackingRuleResponse.from_view(uc.create(command))


@router.patch("/{rule_id}", response_model=EditableTrackingRuleResponse)
def update_tracking_rule(
    rule_id: int,
    body: TrackingRuleUpdateRequest,
    uc: TrackingRuleUseCasesDep,
    current_user: CurrentUserDep,
) -> EditableTrackingRuleResponse:
    sent = body.model_fields_set
    if "task_id" in sent and body.task_id is None:
        raise ValidationError("task_id cannot be null")
    command = UpdateTrackingRuleCommand(
        task_id=body.task_id if body.task_id is not None else UNSET,
        app=body.app if "app" in sent else UNSET,
        title_contains=body.title_contains if "title_contains" in sent else UNSET,
    )
    return EditableTrackingRuleResponse.from_view(
        uc.update(rule_id, current_user.user_id, command)
    )


@router.delete("/{rule_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_tracking_rule(
    rule_id: int, uc: TrackingRuleUseCasesDep, current_user: CurrentUserDep
) -> None:
    uc.delete(rule_id, current_user.user_id)
