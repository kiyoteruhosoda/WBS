from __future__ import annotations

from pydantic import BaseModel, Field

from src.application.dto.tracking_rule_dto import TrackableTask, TrackingRuleView
from src.domain.entities.tracking_rule import APP_MAX_LENGTH, TITLE_CONTAINS_MAX_LENGTH
from src.presentation.api.schemas.types import UtcDatetime


class TrackingRuleResponse(BaseModel):
    """PC の係へ渡す規則。``task_id`` は常に、ある・開いているタスク。"""

    id: int
    position: int
    app: str | None
    title_contains: str | None
    task_id: int
    task_title: str

    @classmethod
    def from_view(cls, view: TrackingRuleView) -> TrackingRuleResponse:
        r = view.rule
        assert r.id is not None and view.task_title is not None
        return cls(
            id=r.id,
            position=r.position,
            app=r.app,
            title_contains=r.title_contains,
            task_id=r.task_id,
            task_title=view.task_title,
        )


class TrackingRuleFeedResponse(BaseModel):
    """自分の規則（使えるものだけ）を ``position`` の昇順に。PC は上から最初に当たったものを使う。
    「それ以外すべて」（両方空）はいつも最後。

    ``updated_at`` は規則か、規則の行き先のタスクが最後に変わった時刻。
    """

    rules: list[TrackingRuleResponse]
    updated_at: UtcDatetime


class EditableTrackingRuleResponse(BaseModel):
    """編集の画面の 1 行。タスクが消された・閉じられた規則も出す（``task_available`` が偽、PC へは渡らない）。"""

    id: int
    position: int
    app: str | None
    title_contains: str | None
    task_id: int
    # タスクが消されていれば null
    task_title: str | None
    task_available: bool
    created_at: UtcDatetime | None
    updated_at: UtcDatetime | None

    @classmethod
    def from_view(cls, view: TrackingRuleView) -> EditableTrackingRuleResponse:
        r = view.rule
        assert r.id is not None
        return cls(
            id=r.id,
            position=r.position,
            app=r.app,
            title_contains=r.title_contains,
            task_id=r.task_id,
            task_title=view.task_title,
            task_available=view.task_available,
            created_at=r.created_at,
            updated_at=r.updated_at,
        )


class TrackingRuleCreateRequest(BaseModel):
    """規則を足す（「それ以外すべて」の上に入る）。

    ``app`` と ``title_contains`` の両方が空なら「それ以外すべて」（1 人 1 つまで。2 つ目は 422。ADR-0045）。
    """

    app: str | None = Field(default=None, max_length=APP_MAX_LENGTH)
    title_contains: str | None = Field(default=None, max_length=TITLE_CONTAINS_MAX_LENGTH)
    task_id: int


class TrackingRuleUpdateRequest(BaseModel):
    """送った欄だけを変える。``app`` / ``title_contains`` の null は「空にする」
    （両方空にすると「それ以外すべて」。既にほかにあれば 422）。"""

    app: str | None = Field(default=None, max_length=APP_MAX_LENGTH)
    title_contains: str | None = Field(default=None, max_length=TITLE_CONTAINS_MAX_LENGTH)
    task_id: int | None = None


class TrackingRuleOrderRequest(BaseModel):
    """上からの順。渡さなかった規則はその後ろに、今の順のまま。"""

    rule_ids: list[int] = Field(min_length=1, max_length=500)


class TrackableTaskResponse(BaseModel):
    id: int
    title: str
    project_title: str | None

    @classmethod
    def from_task(cls, task: TrackableTask) -> TrackableTaskResponse:
        return cls(id=task.id, title=task.title, project_title=task.project_title)


class TrackableTasksResponse(BaseModel):
    """自分が打刻を付けられる開いているタスク（PC のタイムラインで付け替える先）。"""

    tasks: list[TrackableTaskResponse]
