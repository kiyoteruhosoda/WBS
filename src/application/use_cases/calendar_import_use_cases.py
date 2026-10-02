"""カレンダーの取り込みのユースケース（task #196 / ADR-0037）。

外の iCalendar（.ics。Google カレンダーの「iCal 形式の非公開アドレス」・Outlook の「予定表の公開」・
従来の Outlook の「予定表の保存」など）を、読み取り専用のカレンダー（``CalendarKind.IMPORTED``）として持つ。
どのサービスのものかは区別しない。入れ方は 2 つだけ:

- ファイル: 上げた中身を 1 回読む
- URL: 1 回読む。``subscribe`` なら URL を封じて覚え、定期的に読み込み直す（購読）。購読しないなら
  URL は保存しない（公開をすぐ止めてよい）

読み込むたびに、そのカレンダーの回を丸ごと入れ替える（繰り返しは今日の前後の期間で展開して持つ）。
新しい入れ方で読み込み直すと、購読はその入れ方のものに置き換わる（ファイルで入れ直せば購読をやめる）。

取り込んだ回は予定（``calendar_events``）とは別に持ち、計画・締め・打刻・通知には入れない。画面は
``list_occurrence_views`` で引き、カレンダーと「今日」に重ねる。

どの操作も ``user_id`` で持ち主を確かめる（他人・無いカレンダーは 404）。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import date, datetime, time, timedelta
from urllib.parse import urlsplit

from src.application.dto.calendar_import_dto import (
    FeedSource,
    FileFeedSource,
    ImportedOccurrenceView,
    UrlFeedSource,
)
from src.application.ports.calendar_feed import (
    CalendarFeedError,
    CalendarFeedFetcher,
    CalendarFeedParser,
    FeedFailure,
    FeedUrlCipher,
)
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.calendar import Calendar
from src.domain.entities.calendar_import import CalendarImport, FeedSubscription, ImportSource
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.repositories.calendar_import_repository import (
    CalendarImportRepository,
    ImportedOccurrenceRepository,
)
from src.domain.repositories.calendar_repository import CalendarRepository
from src.domain.repositories.user_account_repository import UserAccountRepository
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.imported_occurrence import ImportedOccurrence
from src.domain.value_objects.local_schedule_point import (
    local_date_of,
    local_time_of,
    start_instant,
)
from src.domain.value_objects.time_zone import TimeZoneId
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

WINDOW_PAST_DAYS = 92
"""読み込むとき、今日より何日前の回から持つか。"""
WINDOW_FUTURE_DAYS = 400
"""読み込むとき、今日より何日先の回まで持つか。"""
MAX_OCCURRENCES = 5000
"""1 つのカレンダーに持つ回の上限（超えたら読み込まない）。"""
SUBSCRIPTION_INTERVAL = timedelta(minutes=15)
"""購読を読み込み直す間隔。"""
MAX_VIEW_DAYS = 800
"""回を一度に引ける期間の上限（日）。"""
_MINUTES_PER_DAY = 1440


class CalendarImportUseCases:
    def __init__(
        self,
        calendars: CalendarRepository,
        imports: CalendarImportRepository,
        occurrences: ImportedOccurrenceRepository,
        users: UserAccountRepository,
        fetcher: CalendarFeedFetcher,
        parser: CalendarFeedParser,
        cipher: FeedUrlCipher,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._calendars = calendars
        self._imports = imports
        self._occurrences = occurrences
        self._users = users
        self._fetcher = fetcher
        self._parser = parser
        self._cipher = cipher
        self._uow = unit_of_work
        self._now = now

    @property
    def subscription_available(self) -> bool:
        """URL を購読できる配備か（封じる鍵がある）。"""
        return self._cipher.available

    # ── 作る・読み込み直す ──────────────────────────────────────────────

    def create_imported_calendar(
        self, user_id: int, name: str, color_key: EventColorKey, source: FeedSource
    ) -> tuple[Calendar, CalendarImport]:
        """読み込んでから作る（読めなければ何も作らない）。末尾に足し、最初から表示。"""
        occurrences, subscription = self._read(user_id, source)
        now = self._now()
        existing = self._calendars.find_all(user_id)
        calendar = self._calendars.save(
            Calendar.create_imported(
                user_id=user_id, name=name, color_key=color_key,
                sort_order=_next_sort_order(existing), created_at=now,
            )
        )
        assert calendar.id is not None
        self._occurrences.replace(calendar.id, occurrences)
        calendar_import = self._imports.save(
            CalendarImport(
                calendar_id=calendar.id, source=_source_kind(source), imported_at=now,
                event_count=len(occurrences), subscription=subscription, last_attempt_at=now,
            )
        )
        self._uow.commit()
        return calendar, calendar_import

    def reimport(self, calendar_id: int, user_id: int, source: FeedSource) -> CalendarImport:
        """新しいファイル・URL で入れ替える。購読はこの入れ方のものに置き換わる。"""
        calendar = self._owned_imported(calendar_id, user_id)
        occurrences, subscription = self._read(user_id, source)
        return self._replace(calendar, occurrences, _source_kind(source), subscription)

    def refresh(self, calendar_id: int, user_id: int) -> CalendarImport:
        """購読している URL を今すぐ読み込み直す。購読していなければ 409。

        読めなければ理由を覚えて ``CalendarFeedError`` を投げる（中身は前のまま）。
        """
        calendar = self._owned_imported(calendar_id, user_id)
        calendar_import = self._import_of(calendar)
        if calendar_import.subscription is None:
            raise ConflictError("this calendar is not subscribed to a URL")
        self._refresh_subscription(calendar, calendar_import, raise_on_failure=True)
        return self._import_of(calendar)

    def unsubscribe(self, calendar_id: int, user_id: int) -> CalendarImport:
        """購読をやめる（URL を忘れる。読み込んだ回は残す）。"""
        calendar = self._owned_imported(calendar_id, user_id)
        calendar_import = self._import_of(calendar)
        calendar_import.unsubscribe()
        saved = self._imports.save(calendar_import)
        self._uow.commit()
        return saved

    def refresh_due_subscriptions(self) -> int:
        """間隔の来た購読を読み込み直す（定期の係が呼ぶ）。読み込めた数を返す。

        ⚠ web は複数のワーカーで動くので同じ時刻に重なりうる。入れ替えは冪等なので、重なっても
        同じ中身になるだけ。1 つの失敗で残りを止めない。
        """
        due_before = self._now() - SUBSCRIPTION_INTERVAL
        refreshed = 0
        for calendar_import in self._imports.find_subscribed():
            if calendar_import.last_attempt_at is not None and calendar_import.last_attempt_at > due_before:
                continue
            calendar = self._calendars.find_by_id(calendar_import.calendar_id)
            if calendar is None or not calendar.is_imported:
                continue
            if self._refresh_subscription(calendar, calendar_import, raise_on_failure=False):
                refreshed += 1
        return refreshed

    # ── 引く ────────────────────────────────────────────────────────────

    def imports_of(self, user_id: int) -> dict[int, CalendarImport]:
        """利用者の取り込んだカレンダーの読み込みの状態（カレンダーの id → 状態）。"""
        ids = [c.id for c in self._calendars.find_all(user_id) if c.is_imported and c.id is not None]
        return {i.calendar_id: i for i in self._imports.find_many(ids)}

    def list_occurrence_views(
        self, user_id: int, from_date: date, to_date: date, viewer_time_zone: str
    ) -> list[ImportedOccurrenceView]:
        """期間（閲覧者のローカル日、両端を含む）の取り込んだ回を、日付・開始時刻の順に。

        表示の選択に関係なく全部の取り込んだカレンダーを返す（絞りは画面で行う。予定の回の一覧と同じ）。
        """
        if from_date > to_date:
            raise ValidationError("from_date must be on or before to_date")
        if (to_date - from_date).days > MAX_VIEW_DAYS:
            raise ValidationError(f"the period must be at most {MAX_VIEW_DAYS} days")
        viewer = TimeZoneId(viewer_time_zone).zone
        calendars = {
            c.id: c for c in self._calendars.find_all(user_id) if c.is_imported and c.id is not None
        }
        if not calendars:
            return []
        rows = self._occurrences.find(
            calendars.keys(),
            from_utc=start_instant(from_date, time(0), viewer),
            to_utc=start_instant(to_date + timedelta(days=1), time(0), viewer),
            from_date=from_date,
            to_date=to_date,
        )
        views: list[ImportedOccurrenceView] = []
        for calendar_id, occurrence in rows:
            color = calendars[calendar_id].color_key
            if occurrence.is_all_day:
                assert occurrence.start_date is not None and occurrence.end_date is not None
                day = max(occurrence.start_date, from_date)
                last = min(occurrence.end_date - timedelta(days=1), to_date)
                while day <= last:
                    views.append(
                        ImportedOccurrenceView(
                            calendar_id=calendar_id, title=occurrence.title,
                            location=occurrence.location,
                            start_utc=start_instant(day, time(0), viewer),
                            duration_minutes=_MINUTES_PER_DAY, date=day, start_time=time(0),
                            is_all_day=True, calendar_color_key=color,
                        )
                    )
                    day += timedelta(days=1)
                continue
            assert occurrence.start_utc is not None and occurrence.end_utc is not None
            day = local_date_of(occurrence.start_utc, viewer)
            if not from_date <= day <= to_date:
                continue
            minutes = int((occurrence.end_utc - occurrence.start_utc).total_seconds() // 60)
            views.append(
                ImportedOccurrenceView(
                    calendar_id=calendar_id, title=occurrence.title, location=occurrence.location,
                    start_utc=occurrence.start_utc, duration_minutes=max(minutes, 0), date=day,
                    start_time=local_time_of(occurrence.start_utc, viewer), is_all_day=False,
                    calendar_color_key=color,
                )
            )
        views.sort(key=lambda v: (v.date, not v.is_all_day, v.start_time, v.title))
        return views

    # ── 内側 ────────────────────────────────────────────────────────────

    def _read(
        self, user_id: int, source: FeedSource
    ) -> tuple[list[ImportedOccurrence], FeedSubscription | None]:
        """読み込んで回にする。URL を購読するなら封じたものも返す（封じられなければ読む前に断る）。"""
        subscription: FeedSubscription | None = None
        if isinstance(source, UrlFeedSource):
            if source.subscribe:
                if not self._cipher.available:
                    raise CalendarFeedError(FeedFailure.SUBSCRIPTION_UNAVAILABLE)
                subscription = FeedSubscription(
                    sealed_url=self._cipher.seal(source.url), url_hint=url_hint(source.url)
                )
            content = self._fetcher.fetch(source.url)
        else:
            content = source.content
        return self._parse(user_id, content), subscription

    def _parse(self, user_id: int, content: bytes) -> list[ImportedOccurrence]:
        today = self._now().date()
        occurrences = self._parser.parse(
            content,
            from_date=today - timedelta(days=WINDOW_PAST_DAYS),
            to_date=today + timedelta(days=WINDOW_FUTURE_DAYS),
            default_time_zone=self._time_zone_of(user_id),
        )
        if len(occurrences) > MAX_OCCURRENCES:
            raise CalendarFeedError(FeedFailure.TOO_MANY_EVENTS)
        return occurrences

    def _refresh_subscription(
        self, calendar: Calendar, calendar_import: CalendarImport, *, raise_on_failure: bool
    ) -> bool:
        assert calendar_import.subscription is not None
        subscription = calendar_import.subscription
        try:
            url = self._cipher.open(subscription.sealed_url)
            occurrences = self._parse(calendar.user_id, self._fetcher.fetch(url))
        except CalendarFeedError as exc:
            calendar_import.record_failure(exc.reason.value, self._now())
            self._imports.save(calendar_import)
            self._uow.commit()
            logger.info(
                "購読しているカレンダーを読み込めませんでした",
                extra={
                    "event": "calendar.import.refresh_failed",
                    "calendar_id": calendar.id,
                    "reason": exc.reason.value,
                },
            )
            if raise_on_failure:
                raise
            return False
        self._replace(calendar, occurrences, ImportSource.URL, subscription)
        return True

    def _replace(
        self,
        calendar: Calendar,
        occurrences: list[ImportedOccurrence],
        source: ImportSource,
        subscription: FeedSubscription | None,
    ) -> CalendarImport:
        assert calendar.id is not None
        now = self._now()
        self._occurrences.replace(calendar.id, occurrences)
        calendar_import = self._imports.find(calendar.id) or CalendarImport(
            calendar_id=calendar.id, source=source, imported_at=now, event_count=0
        )
        calendar_import.record_success(
            source=source, event_count=len(occurrences), at=now, subscription=subscription
        )
        saved = self._imports.save(calendar_import)
        self._uow.commit()
        return saved

    def _owned_imported(self, calendar_id: int, user_id: int) -> Calendar:
        calendar = owned_by(
            self._calendars.find_by_id(calendar_id), user_id,
            resource="Calendar", resource_id=calendar_id,
        )
        if not calendar.is_imported:
            raise ValidationError("only an imported calendar can be read from a file or URL")
        return calendar

    def _import_of(self, calendar: Calendar) -> CalendarImport:
        assert calendar.id is not None
        calendar_import = self._imports.find(calendar.id)
        if calendar_import is None:
            raise NotFoundError("CalendarImport", calendar.id)
        return calendar_import

    def _time_zone_of(self, user_id: int) -> str:
        user = self._users.find_by_id(user_id)
        return user.timezone if user is not None else "UTC"


def url_hint(url: str) -> str:
    """画面に出す URL の手掛かり: ホスト名と最後の区切り（秘密の部分を含めない）。

    Google の非公開アドレスは途中の ``private-…`` が秘密、Outlook の公開 URL も途中の長い符号が
    秘密なので、ホスト名と末尾のファイル名だけを出す（例: ``calendar.google.com …/basic.ics``）。
    """
    parts = urlsplit(url.strip())
    host = parts.hostname or ""
    tail = parts.path.rstrip("/").rsplit("/", 1)[-1] if parts.path else ""
    if len(tail) > 24:
        tail = ""
    return f"{host} …/{tail}" if tail else f"{host} …"


def _source_kind(source: FeedSource) -> ImportSource:
    return ImportSource.FILE if isinstance(source, FileFeedSource) else ImportSource.URL


def _next_sort_order(existing: list[Calendar]) -> int:
    """末尾（予定のカレンダーを作るときと同じ決め方）。"""
    return max((c.sort_order for c in existing), default=-1) + 1


__all__ = [
    "MAX_OCCURRENCES",
    "SUBSCRIPTION_INTERVAL",
    "WINDOW_FUTURE_DAYS",
    "WINDOW_PAST_DAYS",
    "CalendarImportUseCases",
    "url_hint",
]
