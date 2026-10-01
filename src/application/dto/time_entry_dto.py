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
    # 押した時刻（naive な UTC）。None は「今」。アプリが電波の無いときに溜めた押下を送る（ADR-0018）
    at: datetime | None = None


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


@dataclass
class CreateTimeEntryCommand:
    """締めの画面で空き時間に打刻を足す（``source=manual``）。時刻は naive な UTC。"""

    user_id: int
    started_at: datetime
    ended_at: datetime
    task_id: int | None = None
    memo: str | None = None


@dataclass
class MergeTimeEntriesCommand:
    """打刻をつなぐ。いちばん早い打刻が残り、始まりから最後の終わりまでの 1 本になる。

    ``task_id`` が UNSET なら、残る打刻のタスク（未割当なら、ほかの打刻で最初に見つかったタスク）。
    """

    user_id: int
    entry_ids: list[int]
    task_id: int | None | UnsetType = UNSET


@dataclass
class EntryFromOccurrenceCommand:
    """予定の回をそのまま打刻にする。回は（予定の id, 始まりの瞬間）で指す。

    ``task_id`` が UNSET なら回に結ばれたタスク（消えていれば未割当）。
    """

    user_id: int
    event_id: int
    start: datetime
    task_id: int | None | UnsetType = UNSET


@dataclass(frozen=True)
class SplitTimeEntryResult:
    first: TimeEntryView
    """元の打刻（分けた時刻で終わる）。"""
    second: TimeEntryView
    """分けた時刻から始まる新しい打刻（``source=split``）。"""
