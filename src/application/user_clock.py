"""利用者から見た「今日」。

日付の境目は利用者のタイムゾーンで決まる。サーバは UTC で動くので、
`date.today()` を使うと UTC の日付になり、JST の利用者にとっては毎日
0:00〜9:00 のあいだ「今日」が前日にずれる。

保存・比較は UTC のまま（契約 HANDOVER §14）。ここで扱うのは「画面に見せる
区切り」としての日付だけ。
"""

from __future__ import annotations

from datetime import date
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import UserModel
from src.shared.clock import utcnow


class UserClock:
    """利用者のタイムゾーンで日付を出す。1 リクエスト内は引き直さない。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._cache: dict[int, date] = {}

    def today(self, user_id: int) -> date:
        cached = self._cache.get(user_id)
        if cached is not None:
            return cached
        timezone_name = (
            self._session.execute(
                select(UserModel.timezone).where(UserModel.id == user_id)
            ).scalar()
            or "UTC"
        )
        now = utcnow()
        try:
            resolved = now.astimezone(ZoneInfo(timezone_name)).date()
        except (ZoneInfoNotFoundError, ValueError):
            resolved = now.date()
        self._cache[user_id] = resolved
        return resolved


__all__ = ["UserClock"]
