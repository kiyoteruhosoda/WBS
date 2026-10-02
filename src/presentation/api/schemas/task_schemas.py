from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from src.domain.value_objects.task_status import TaskStatus
from src.presentation.api.schemas.types import UtcDatetime


class TaskCreateRequest(BaseModel):
    title: str
    category_id: int | None = None
    priority: int = Field(default=3, ge=1, le=5)
    urgency: int = Field(default=3, ge=1, le=5)
    status: TaskStatus = TaskStatus.TODO
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    # 手で持つ残（時間）。空なら「見積 − 実績」を既定に使う（ADR-0010）。更新で null を送ると空へ戻す
    remaining_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # 空 = 未分類。親を持つタスクは親のプロジェクトに入る（省くと親に揃える。違う値は 422。ADR-0024）
    project_id: int | None = None


class TaskUpdateRequest(BaseModel):
    title: str | None = None
    category_id: int | None = None
    priority: int | None = Field(default=None, ge=1, le=5)
    urgency: int | None = Field(default=None, ge=1, le=5)
    status: TaskStatus | None = None
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: Decimal | None = None
    # 手で持つ残（時間）。空なら「見積 − 実績」を既定に使う（ADR-0010）。更新で null を送ると空へ戻す
    remaining_hours: Decimal | None = Field(default=None, ge=0, le=Decimal("9999.99"))
    memo: str | None = None
    parent_task_id: int | None = None
    # null を送るとマイルストーンを外す。プロジェクトの外のものは 422（ADR-0024）
    milestone_id: int | None = None
    # null を送ると未分類へ。子孫も一緒に移る。子タスクは親と違う値を送ると 422
    project_id: int | None = None


class TaskResponse(BaseModel):
    id: int
    user_id: int
    title: str
    category_id: int | None = None
    priority: int
    urgency: int
    status: str
    start_date: date | None = None
    due_date: date | None = None
    estimated_hours: float | None = None
    # 自分の残（手の値、空なら見積 − 実績。DONE は 0）と、手で入れた値そのもの
    remaining_hours: float | None = None
    remaining_hours_entered: float | None = None
    # 自分の実績（work_logs の合計）
    actual_hours: float = 0.0
    has_subtasks: bool = False
    # 進捗率の式に入れた実績と残（子を持つなら自分と全子孫の積み上げ）
    rollup_actual_hours: float = 0.0
    rollup_remaining_hours: float | None = None
    # 実績 ÷（実績 ＋ 残）× 100。DONE は 100。分母 0・残が決まらないときは null
    progress_percent: float | None = None
    # 予定済みの時間: 今日以降に始まる、このタスクに結ばれた予定の回の合計（終日の回は数えない。ADR-0014）。
    # まだ取っていない分 = 残 − 予定済み（0 未満は 0）。予定を見ない応答・残が決まらないときは null
    scheduled_hours: float | None = None
    unscheduled_hours: float | None = None
    priority_score: int = 0
    memo: str | None = None
    parent_task_id: int | None = None
    milestone_id: int | None = None
    # 属するプロジェクト（null = 未分類）と、表示用の道筋（「親 / 子」）
    project_id: int | None = None
    project_path: str | None = None
    completed_at: UtcDatetime | None = None
    deleted_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}
