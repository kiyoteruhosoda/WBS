"""予定のユースケースへの入力。

時刻はすべて **UTC の瞬間 ＋ 長さ（分）** で受け取る（naive は UTC とみなす。aware は
UTC へ直す）。「終日」は入力側の糖衣で、予定のタイムゾーンの 0:00 の瞬間 ＋ 1440 分を渡す。
繰り返しの回は ``OccurrenceKey``（予定のタイムゾーンでの候補日 ＋ 系列の開始時刻）で指す。
展開した回の ``series_key`` をそのまま返せばよい。

``expected_version`` は楽観ロック。読んだときの ``version`` を渡すと、間に別の更新が
入っていたら ``ConflictError`` になる。``None`` なら確かめない。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.application.dto.unset import UNSET, UnsetType
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.event_schedule import OccurrenceKey
from src.domain.value_objects.recurrence import RecurrenceRule


@dataclass
class CreateSingleEventCommand:
    user_id: int
    title: str
    time_zone: str
    start_utc: datetime
    duration_minutes: int
    location: str | None = None
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None


@dataclass
class CreateRecurringEventCommand:
    user_id: int
    title: str
    time_zone: str
    anchor_utc: datetime
    """先頭の回の開始の瞬間。"""
    duration_minutes: int
    recurrence_rule: RecurrenceRule
    location: str | None = None
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None = None


@dataclass
class UpdateEventCommand:
    """詳細を置き換える。単発で ``start_utc`` と ``duration_minutes`` があれば日時も移す。"""

    event_id: int
    user_id: int
    title: str
    location: str | None = None
    description: str | None = None
    task_id: int | None = None
    start_utc: datetime | None = None
    duration_minutes: int | None = None
    color_key: EventColorKey | None = None
    """``None`` は今の色のまま（ドラッグなどの部分的な更新で色を消さない）。"""
    expected_version: int | None = None


@dataclass
class RescheduleSingleEventCommand:
    """単発の日時だけを移す（詳細・色・メモは触らない）。"""

    event_id: int
    user_id: int
    start_utc: datetime
    duration_minutes: int
    expected_version: int | None = None


@dataclass
class UpdateRecurringSeriesCommand:
    """すべての回を直す。"""

    event_id: int
    user_id: int
    title: str
    duration_minutes: int
    recurrence_rule: RecurrenceRule
    location: str | None = None
    description: str | None = None
    task_id: int | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    anchor_utc: datetime | None = None
    """新しい先頭の回の瞬間。``None`` は今のアンカーのまま（既存の鍵がずれない）。"""
    expected_version: int | None = None


@dataclass
class OccurrenceCommand:
    """繰り返しの 1 回を指す操作（飛ばす・飛ばすの取り消し・移動の取り消し・以降を消す）。"""

    event_id: int
    user_id: int
    occurrence_key: OccurrenceKey
    expected_version: int | None = None


@dataclass
class MoveOccurrenceCommand:
    """その回だけ別の日時へ移す。``title`` / ``location`` は ``None`` なら系列のまま。"""

    event_id: int
    user_id: int
    occurrence_key: OccurrenceKey
    start_utc: datetime
    duration_minutes: int
    title: str | None = None
    location: str | None = None
    expected_version: int | None = None


@dataclass
class SplitThisOccurrenceCommand:
    """この回だけを直す: 系列からその回を飛ばし、同じタイムゾーンの単発を新しく作る。"""

    event_id: int
    user_id: int
    occurrence_key: OccurrenceKey
    title: str
    start_utc: datetime
    duration_minutes: int
    location: str | None = None
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None | UnsetType = UNSET
    """``UNSET`` は系列のタスクを引き継ぐ。"""
    expected_version: int | None = None


@dataclass
class ChangeFollowingOccurrencesCommand:
    """この回以降を直す: 元の系列をこの回の前日で終え、この回からの新しい系列を作る。"""

    event_id: int
    user_id: int
    from_occurrence_key: OccurrenceKey
    title: str
    anchor_utc: datetime
    """新しい系列の先頭の回の瞬間。"""
    duration_minutes: int
    recurrence_rule: RecurrenceRule
    location: str | None = None
    description: str | None = None
    color_key: EventColorKey = EventColorKey.DEFAULT
    task_id: int | None | UnsetType = UNSET
    """``UNSET`` は元の系列のタスクを引き継ぐ。"""
    expected_version: int | None = None
