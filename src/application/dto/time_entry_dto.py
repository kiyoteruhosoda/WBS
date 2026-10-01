from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.dto.unset import UNSET, UnsetType
from src.domain.entities.time_entry import TimeEntry


@dataclass
class StartTimerCommand:
    user_id: int
    # UNSET = 既定の順（いまの予定のタスク → 直前の打刻のタスク → 未割当）で決める
    # None  = 未割当で始める（明示）
    task_id: int | None | UnsetType = UNSET
    memo: str | None = None


@dataclass
class UpdateTimeEntryCommand:
    # UNSET = 変更しない / None = 明示的にクリアする（task_id・memo）
    # 時刻は naive な UTC。ended_at を None にする（走っている状態へ戻す）ことはできない
    started_at: datetime | UnsetType = UNSET
    ended_at: datetime | UnsetType = UNSET
    task_id: int | None | UnsetType = UNSET
    memo: str | None | UnsetType = UNSET


@dataclass(frozen=True)
class TimeEntryView:
    """画面・アプリへ返す打刻。タスク名と「長すぎる」の印を添える。"""

    entry: TimeEntry
    task_title: str | None
    # 走っている打刻は「いま」までの長さ
    duration_seconds: int
    is_long_running: bool


@dataclass(frozen=True)
class StartTimerResult:
    started: TimeEntryView
    # 走っていた打刻を止めて切り替えたときの、止めた方
    stopped: TimeEntryView | None
