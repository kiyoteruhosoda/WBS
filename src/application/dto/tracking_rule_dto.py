from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.dto.unset import UNSET, UnsetType
from src.domain.entities.tracking_rule import TrackingRule


@dataclass(frozen=True)
class TrackingRuleView:
    """編集の画面へ返す規則。タスクが消された・閉じられた規則も出す（``task_available`` が偽）。"""

    rule: TrackingRule
    # タスクが消されていれば None
    task_title: str | None
    # PC へ渡すか（タスクがあって、完了・中止でない）
    task_available: bool


@dataclass(frozen=True)
class TrackingRuleFeed:
    """PC の係へ渡す規則（使えるものだけ、上からの順）と、最後に変わった時刻（naive な UTC）。"""

    rules: list[TrackingRuleView]
    updated_at: datetime


@dataclass(frozen=True)
class TrackableTask:
    """打刻を付けられる開いているタスク（PC のタイムラインで付け替える先）。"""

    id: int
    title: str
    project_title: str | None


@dataclass
class CreateTrackingRuleCommand:
    user_id: int
    task_id: int
    app: str | None = None
    title_contains: str | None = None


@dataclass
class UpdateTrackingRuleCommand:
    # UNSET = 変えない。app / title_contains の None は「空にする」（両方空にはできない）
    task_id: int | UnsetType = UNSET
    app: str | None | UnsetType = UNSET
    title_contains: str | None | UnsetType = UNSET
