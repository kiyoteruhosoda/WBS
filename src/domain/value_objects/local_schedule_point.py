"""壁時計（ローカル日付＋時刻）と UTC の瞬間の行き来。

時刻モデル（移植元 docs/time-model.md §3〜§4）: 予定は UTC の瞬間で持ち、ローカル日・
時刻は予定のタイムゾーンで都度求める。ここで扱う瞬間はすべて **naive な UTC**
（`src/shared/clock.utcnow()` と保存値の形に合わせる）。aware な値も受け付け、
UTC へ直してから使う。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, tzinfo

MINUTES_PER_DAY = 24 * 60


def to_naive_utc(instant: datetime) -> datetime:
    """naive は UTC とみなしてそのまま、aware は UTC へ直して tz を外す。"""
    if instant.tzinfo is None:
        return instant
    return instant.astimezone(UTC).replace(tzinfo=None)


def start_instant(day: date, at: time, zone: tzinfo) -> datetime:
    """``zone`` の壁時計 ``day`` ``at`` を UTC の瞬間（naive）にする。

    DST の飛び（存在しない時刻）と重なり（2 度ある時刻）は ``fold=0`` で解く
    ——飛びは切り替え前の時差、重なりは先の方（夏時間側）になる。
    """
    local = datetime.combine(day, at.replace(tzinfo=None), tzinfo=zone)
    return local.astimezone(UTC).replace(tzinfo=None)


def _local(instant: datetime, zone: tzinfo) -> datetime:
    return to_naive_utc(instant).replace(tzinfo=UTC).astimezone(zone)


def local_date_of(instant: datetime, zone: tzinfo) -> date:
    """UTC の瞬間が ``zone`` で何日か。"""
    return _local(instant, zone).date()


def local_time_of(instant: datetime, zone: tzinfo) -> time:
    """UTC の瞬間が ``zone`` で何時何分か（秒まで。マイクロ秒は落とす）。"""
    local = _local(instant, zone)
    return time(local.hour, local.minute, local.second)


def wrapping_duration_minutes(start: time, end: time) -> int:
    """開始・終了の時刻の組を長さ（分）にする。``end <= start`` は日をまたぐとみなす。

    ``end == start`` は 24 時間。画面の「開始〜終了」入力や旧形式のデータを長さへ直す口。
    """
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return minutes if minutes > 0 else minutes + MINUTES_PER_DAY


__all__ = [
    "MINUTES_PER_DAY",
    "local_date_of",
    "local_time_of",
    "start_instant",
    "to_naive_utc",
    "wrapping_duration_minutes",
]
