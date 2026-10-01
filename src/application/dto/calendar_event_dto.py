"""予定のユースケースへの入力。

時刻はすべて **UTC の瞬間 ＋ 長さ（分）** で受け取る（naive は UTC とみなす。aware は
UTC へ直す）。「終日」は入力側の糖衣で、予定のタイムゾーンの 0:00 の瞬間 ＋ 1440 分を渡す。
繰り返しの回は ``OccurrenceKey``（予定のタイムゾーンでの候補日 ＋ 系列の開始時刻）で指す。
展開した回の ``series_key`` をそのまま返せばよい。

``expected_version`` は楽観ロック。読んだときの ``version`` を渡すと、間に別の更新が
入っていたら ``ConflictError`` になる。``None`` なら確かめない。

``alarm``（通知、ADR-0021）は ``UNSET`` と ``None`` を分ける。作るときの ``UNSET`` は既定
（``EventAlarm.default()``: 4 つとも入り）、直すときの ``UNSET`` は今のまま（この回だけ・以降は
元の系列のもの）。``None`` は通知なし。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time

from src.application.dto.unset import UNSET, UnsetType
from src.domain.value_objects.event_alarm import EventAlarm
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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は既定（4 つとも入り）。``None`` は通知なし。"""


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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は既定（4 つとも入り）。``None`` は通知なし。"""


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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は今のまま。``None`` は通知を外す。"""
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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は今のまま。``None`` は通知を外す。"""
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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は元の系列の通知を引き継ぐ。``None`` は通知なし。"""
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
    alarm: EventAlarm | None | UnsetType = UNSET
    """``UNSET`` は元の系列の通知を引き継ぐ。``None`` は通知なし。"""
    expected_version: int | None = None


@dataclass(frozen=True)
class OccurrenceView:
    """閲覧者のタイムゾーンへ投影した 1 回（API の応答の 1 件の元）。

    ``date`` / ``start_time`` は閲覧者の壁時計、``start_utc`` はその瞬間（naive な UTC）。
    ``series_key`` は繰り返しの回だけが持つ（予定のタイムゾーンでの鍵。回の操作でそのまま返す）。
    ``event_version`` は回の操作で ``expected_version`` に渡す版。
    """

    event_id: int
    event_version: int
    is_recurring: bool
    title: str
    start_utc: datetime
    duration_minutes: int
    date: date
    start_time: time
    is_all_day: bool
    color_key: EventColorKey
    location: str | None
    task_id: int | None
    is_moved: bool
    is_overridden: bool
    series_key: OccurrenceKey | None
    alarm: EventAlarm | None = None
    """予定の通知の設定（繰り返しは系列のもの。移した回も同じ）。"""


@dataclass(frozen=True)
class PlannedAlarm:
    """この先の通知 1 件（ADR-0021）。開始の ``minutes_before`` 分前の ``notify_at`` に知らせる。

    瞬間はどれも naive な UTC。``task_id`` / ``task_title`` は結んだタスクがその利用者のもので
    今もあるときだけ（消えた・他人のものなら両方 ``None``）。
    """

    event_id: int
    occurrence_start_utc: datetime
    """この回の開始。予定の id と合わせて回を一意に指す。"""
    minutes_before: int
    notify_at_utc: datetime
    title: str
    duration_minutes: int
    location: str | None
    task_id: int | None
    task_title: str | None
    is_recurring: bool
