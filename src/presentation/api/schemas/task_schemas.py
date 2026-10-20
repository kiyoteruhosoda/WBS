from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from src.domain.services.completion_forecast import ForecastGap
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
    # 担当者（利用者の id）。省くと作った人、null で担当なし。根のプロジェクトのメンバー以外は 422（ADR-0055）
    assignee_user_id: int | None = None
    # アサイン比率（%）。入れると担当者の 1 日の空きのうちこの割合で進む見込みになる。空なら順番に片付ける（ADR-0058）
    allocation_percent: int | None = Field(default=None, ge=1, le=100)


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
    # null を送ると担当なし。根のプロジェクトのメンバー以外は 422（ADR-0055）
    assignee_user_id: int | None = None
    # null を送ると比率なし（順番に片付ける）。ADR-0058
    allocation_percent: int | None = Field(default=None, ge=1, le=100)


class TaskMoveToProjectRequest(BaseModel):
    """選んだタスクをまとめて別のプロジェクトへ。``project_id`` に ``null`` を送ると未分類へ（ADR-0030）。"""

    task_ids: list[int] = Field(min_length=1, max_length=500)
    project_id: int | None


class TaskMoveToProjectResponse(BaseModel):
    # プロジェクトが替わったタスク（選んだ根と、一緒に移った子孫）。もともとそこに居たものは含まない
    moved_task_ids: list[int]
    # 届かなくなったマイルストーンを外したタスク
    detached_milestone_task_ids: list[int]


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
    # 担当者と、その表示名（ADR-0055）。担当なしは null
    assignee_user_id: int | None = None
    assignee_name: str | None = None
    # アサイン比率（%、ADR-0058）。null は比率なし
    allocation_percent: int | None = None
    # 終わる見込み（ADR-0058。読むたびに、残を担当者の空きに積んで出す）。出さないときは forecast_gap に理由
    forecast_start: date | None = None
    forecast_finish: date | None = None
    forecast_gap: ForecastGap | None = None
    # 見込みの終わりが期限を越える暦の日数（越えなければ 0）
    forecast_overdue_days: int = 0
    completed_at: UtcDatetime | None = None
    deleted_at: UtcDatetime | None = None
    # アーカイブした時刻（ADR-0046）。アーカイブしたタスクは一覧に出ないが、1 件の取得では返る
    archived_at: UtcDatetime | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    model_config = {"from_attributes": True}


class TaskRemovalResponse(BaseModel):
    """タスクを消すとどうなるか（確認の窓に出す。ADR-0046）。

    ``action`` は ``delete``（打刻も実績も無い）か ``archive``（ある。消さずにアーカイブする）。
    ``blocked_by`` が null でなければ、どちらもできない（``running`` = 計測中）。
    """

    task_id: int
    title: str
    action: str
    time_entries: int
    tracked_seconds: int
    work_log_hours: float
    tracking_rules: int
    blocked_by: str | None
    archived: bool
