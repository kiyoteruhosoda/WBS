"""API スキーマで使う型。

`UtcDatetime` は保存値を必ず ``Z`` で終わる ISO 文字列として返すための注釈付き型。
素の ``datetime`` のまま返すとオフセットが付かず、ブラウザの ``new Date()`` が
ローカル時刻として読むため表示が 9 時間ずれる（HANDOVER §14）。

レスポンスに時刻を足すときは ``datetime`` ではなくこの型を使う。
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import PlainSerializer

from src.shared.clock import isoformat_utc

UtcDatetime = Annotated[
    datetime,
    PlainSerializer(isoformat_utc, return_type=str, when_used="json"),
]

__all__ = ["UtcDatetime"]
