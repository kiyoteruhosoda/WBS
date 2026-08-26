"""利用者から見た「今日」。

日付の境目は利用者のタイムゾーンで決まる。サーバは UTC で動くので、
`date.today()` を使うと UTC の日付になり、JST の利用者にとっては毎日
0:00〜9:00 のあいだ「今日」が前日にずれる。

保存・比較は UTC のまま（契約 HANDOVER §14）。ここで扱うのは「画面に見せる
区切り」としての日付だけ。利用者の日付で切った区間を UTC の保存値と突き合わせる
ときは `utc_window()` を通す。
"""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta, tzinfo
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import select
from sqlalchemy.orm import Session

from src.infrastructure.database.models import UserModel
from src.shared.clock import utcnow


class UserClock:
    """利用者のタイムゾーンで日付を出す。1 リクエスト内は引き直さない。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._zones: dict[int, tzinfo] = {}
        self._today: dict[int, date] = {}

    def zone(self, user_id: int) -> tzinfo:
        """利用者のタイムゾーン。未設定・不正な値は UTC に倒す。"""
        cached = self._zones.get(user_id)
        if cached is not None:
            return cached
        timezone_name = (
            self._session.execute(
                select(UserModel.timezone).where(UserModel.id == user_id)
            ).scalar()
            or "UTC"
        )
        try:
            resolved: tzinfo = ZoneInfo(timezone_name)
        except (ZoneInfoNotFoundError, ValueError):
            resolved = UTC
        self._zones[user_id] = resolved
        return resolved

    def today(self, user_id: int) -> date:
        cached = self._today.get(user_id)
        if cached is not None:
            return cached
        # utcnow() は保存値と同じ naive な UTC。付け直してから利用者の TZ へ。
        resolved = utcnow().replace(tzinfo=UTC).astimezone(self.zone(user_id)).date()
        self._today[user_id] = resolved
        return resolved

    def utc_window(self, user_id: int, first_day: date, last_day: date) -> tuple[datetime, datetime]:
        """利用者の ``first_day`` 0:00 から ``last_day`` の終わりまでを UTC で返す。

        戻りは ``[開始, 終了)`` の半開区間（保存値と同じ UTC naive）。

        保存値は UTC なので、利用者のタイムゾーンで切った日付をそのまま DATETIME 列と
        比べると境目が時差の分ずれる。JST なら月曜 0:00〜9:00 にできた行が前の週にも
        今の週にも入らず、どこからも数えられなくなる。日付をそのまま渡すと終端が
        「最終日の 0:00」になってしまう取りこぼしも、ここで半開区間にして防ぐ。
        """
        zone = self.zone(user_id)
        start = datetime.combine(first_day, time.min, tzinfo=zone)
        end = datetime.combine(last_day + timedelta(days=1), time.min, tzinfo=zone)
        return (
            start.astimezone(UTC).replace(tzinfo=None),
            end.astimezone(UTC).replace(tzinfo=None),
        )


__all__ = ["UserClock"]
