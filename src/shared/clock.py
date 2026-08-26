"""時刻の取り扱い。

契約（HANDOVER §14）: 保存・比較・ログはすべて UTC で、ローカルタイムへ直すのは
画面に出す瞬間だけ。「今」を取る口をここ 1 か所に集約する。

素の ``datetime.now()`` はコンテナのローカル時刻を返す。stdlib の naive な UTC
（Python 3.12 以降は非推奨）も使わない。どちらも ``utcnow()`` に寄せる。
"""

from __future__ import annotations

from datetime import UTC, datetime


def utcnow() -> datetime:
    """現在時刻を aware な UTC で返す。"""
    return datetime.now(UTC)


def isoformat_utc(value: datetime) -> str:
    """API の外へ出す ISO 文字列。末尾は必ず ``Z`` になる。

    naive な値は UTC とみなす（SQLite の DATETIME 列は tz を持たないまま返る）。
    ``Z`` の無い ISO 文字列はブラウザの ``new Date()`` がローカル時刻として読むので、
    境界を出る値は必ずここを通す。
    """
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat().replace("+00:00", "Z")


__all__ = ["isoformat_utc", "utcnow"]
