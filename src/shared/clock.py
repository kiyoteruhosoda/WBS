"""時刻の取り扱い。

契約（HANDOVER §14）: 保存・比較・ログはすべて UTC で、ローカルタイムへ直すのは
画面に出す瞬間だけ。「今」を取る口はここ 1 つに集約する。

素の ``datetime.now()`` はコンテナのローカル時刻を返すので使わない。
``datetime.now(UTC)`` も**ここ以外では呼ばない**（生成口が 2 つあると、次に
方針を変えるときに片方が残る）。`tests/unit/test_time_contract.py` が見張る。

``utcnow()`` が返すのは **naive な UTC**。DB（SQLite / MariaDB）の ``DATETIME``
はタイムゾーンを持たず、書いた値は naive で返ってくる。生成側だけ aware にすると
「入れたばかりの値は aware、読み直した値は naive」となり、両者を比べた瞬間に
``TypeError: can't compare offset-naive and offset-aware datetimes`` で落ちる。
保存する形に合わせておけば、その組み合わせが起こらない。

ローカルタイムへ直すときは、naive を UTC とみなして付け直してから変換する
（`src/application/user_clock.py`）。境界へ出す文字列は `isoformat_utc()`。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """現在時刻を naive な UTC で返す（保存値と同じ形）。"""
    return datetime.now(UTC).replace(tzinfo=None)


def isoformat_utc(value: datetime) -> str:
    """API の外へ出す ISO 文字列。末尾は必ず ``Z`` になる。

    naive な値は UTC とみなす。``Z`` の無い ISO 文字列はブラウザの ``new Date()``
    がローカル時刻として読むので、境界を出る値は必ずここを通す。
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


__all__ = ["isoformat_utc", "utcnow"]
