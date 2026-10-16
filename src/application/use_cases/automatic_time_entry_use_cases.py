"""PC の自動記録（WinTrack）の打刻を受け取る（task #379 / ADR-0042、Working が正の改訂は task #386 / ADR-0045）。

**Working（手の打刻）が正。** WinTrack は区間ごとに送り方を選ぶ:

- ``fill``（既定のタスク）: ほかの打刻（手・自動・走っている打刻）に覆われていない部分だけを打刻にする。
  空きが 2 つ以上なら 2 本以上できる。空きが無ければ作らない（``covered``。エラーではない）
- ``override``（例外作業）: 手の打刻のその時間を切り抜いて作る（片側に掛かれば縮める・中に収まれば消す・
  またげば分ける・走っている打刻は閉じて走らせ直す）。切り抜く前の手の打刻は ``time_entry_carvings`` に残す。
  ほかの自動の打刻とは重ねない（``overlap``）

1 区間ずつ確定し、1 区間を断っても残りは作る。送り直し（同じ ``client_ref``）は受け取りの控えで見分け、
そのとき作った打刻を返す（中身が違っても上書きしない）。作らなかった区間は控えない。
判定の順は「送り直し → 範囲・タスク・mode（invalid）→ 締め（closed）→ 重なり（overlap）/ 覆われ（covered）→ 作る」。

**伸ばす（ADR-0050）。** 同じ ``client_ref`` で始まり・タスク・``mode`` が同じまま終わりだけ遅くなって届いたら、
控えの終わりから新しい終わりまで（増えた分）だけを同じ規則で受ける。その ``client_ref`` の最後の打刻が控えの終わりで
終わっていれば、それを伸ばす（つながらなければ足す）。WinTrack は同じタスクが続く間、終わった時間帯ごとに伸ばして送る。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime, timedelta

from src.application.dto.time_entry_dto import (
    AutoTimeEntryItem,
    AutoTimeEntryOutcome,
    AutoTimeEntryStatus,
    TimeEntryView,
)
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.time_entry_use_cases import build_time_entry_view
from src.domain.entities.auto_time_entry_receipt import AutoTimeEntryReceipt
from src.domain.entities.time_entry import TimeEntry
from src.domain.entities.time_entry_carving import TimeEntryCarving
from src.domain.exceptions import ConflictError, ValidationError
from src.domain.repositories.auto_time_entry_receipt_repository import (
    AutoTimeEntryReceiptRepository,
)
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.time_entry_carving_repository import TimeEntryCarvingRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.services.time_entry_spans import carve, free_spans
from src.domain.value_objects.auto_entry_mode import AutoEntryMode
from src.domain.value_objects.press_time import CLOCK_SKEW_ALLOWANCE, MAX_PRESS_AGE
from src.domain.value_objects.time_entry_source import TimeEntrySource
from src.shared.clock import utcnow

logger = logging.getLogger(__name__)

MAX_AUTO_ENTRIES_PER_REQUEST = 200
"""1 回に受け取る区間の上限（ADR-0042）。"""


class _Rejected(Exception):
    """1 区間を作らない理由（このモジュールの中だけで使う）。"""

    def __init__(self, status: AutoTimeEntryStatus, error: str | None) -> None:
        super().__init__(error or status.value)
        self.status = status
        self.error = error


class AutomaticTimeEntryUseCases:
    def __init__(
        self,
        entries: TimeEntryRepository,
        receipts: AutoTimeEntryReceiptRepository,
        carvings: TimeEntryCarvingRepository,
        tasks: OwnedTaskLookup,
        closing_periods: ClosingPeriodRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._entries = entries
        self._receipts = receipts
        self._carvings = carvings
        self._tasks = tasks
        self._closing_periods = closing_periods
        self._uow = unit_of_work
        self._now = now

    def record(self, user_id: int, items: list[AutoTimeEntryItem]) -> list[AutoTimeEntryOutcome]:
        """送られた区間を 1 つずつ打刻にする。結果は送られた順。"""
        if len(items) > MAX_AUTO_ENTRIES_PER_REQUEST:
            raise ValidationError(
                f"too many entries (at most {MAX_AUTO_ENTRIES_PER_REQUEST} at once)"
            )
        now = self._now()
        titles: dict[int, str | None] = {}
        return [self._record_one(user_id, item, now, titles) for item in items]

    # ── 1 区間 ──────────────────────────────────────────────────────────

    def _record_one(
        self, user_id: int, item: AutoTimeEntryItem, now: datetime, titles: dict[int, str | None]
    ) -> AutoTimeEntryOutcome:
        receipt = self._receipts.find(user_id, item.client_ref)
        if receipt is not None:
            if _extends(receipt, item):
                return self._extend(user_id, item, receipt, now, titles)
            return self._duplicate(user_id, item, now, titles)
        try:
            mode = _mode(item.mode)
            start, end = _window(item, now)
            if self._tasks.find_by_id_for_user(item.task_id, user_id) is None:
                raise _Rejected(AutoTimeEntryStatus.INVALID, "task_not_found")
            if self._is_closed(user_id, start, end):
                raise _Rejected(AutoTimeEntryStatus.CLOSED, "period_closed")
            in_the_way = self._entries.find_overlapping(user_id, start, end)
            if mode is AutoEntryMode.FILL:
                spans = free_spans(start, end, in_the_way)
                if not spans:
                    raise _Rejected(AutoTimeEntryStatus.COVERED, None)
            else:
                self._ensure_can_override(user_id, in_the_way)
        except _Rejected as rejected:
            return AutoTimeEntryOutcome(
                client_ref=item.client_ref, status=rejected.status, error=rejected.error
            )

        # ここから書く（断る理由は上で出し切った）。控えを先に書く: 同じ区間を同時に送り直したら、ここで一意に当たる
        try:
            self._receipts.add(
                AutoTimeEntryReceipt(
                    user_id=user_id,
                    client_ref=item.client_ref,
                    mode=mode,
                    received_at=now,
                    started_at=start,
                    ended_at=end,
                    task_id=item.task_id,
                )
            )
        except ConflictError:
            return self._duplicate(user_id, item, now, titles)
        if mode is AutoEntryMode.FILL:
            created = [
                self._entries.save(_automatic(user_id, item, s, e, AutoEntryMode.FILL))
                for s, e in spans
            ]
        else:
            created = self._override(user_id, item, start, end, in_the_way, now)
        self._uow.commit()
        return AutoTimeEntryOutcome(
            client_ref=item.client_ref,
            status=AutoTimeEntryStatus.CREATED,
            views=[_view(e, now, self._tasks, titles) for e in created],
        )

    def _extend(
        self,
        user_id: int,
        item: AutoTimeEntryItem,
        receipt: AutoTimeEntryReceipt,
        now: datetime,
        titles: dict[int, str | None],
    ) -> AutoTimeEntryOutcome:
        """控えの終わりから新しい終わりまで（増えた分）を受け、同じ ``client_ref`` の打刻を伸ばす・足す。"""
        assert receipt.ended_at is not None
        mine = self._entries.find_by_client_ref(user_id, item.client_ref)
        try:
            _, end = _window(item, now)
            start = receipt.ended_at
            if end <= start:
                # 今に寄せたら伸びなかった（時計のずれ）。送り直しと同じ
                return self._duplicate(user_id, item, now, titles)
            if self._is_closed(user_id, start, end):
                raise _Rejected(AutoTimeEntryStatus.CLOSED, "period_closed")
            in_the_way = [
                e
                for e in self._entries.find_overlapping(user_id, start, end)
                if e.client_ref != item.client_ref or not e.is_automatic
            ]
            if receipt.mode is AutoEntryMode.FILL:
                spans = free_spans(start, end, in_the_way)
            else:
                # 例外の続きは、ほかの自動の打刻（その間に送った既定の打刻など）を避けて伸ばし、手の打刻だけを切り抜く
                manual = [e for e in in_the_way if not e.is_automatic]
                if any(self._is_closed(user_id, e.started_at, e.ended_at) for e in manual):
                    raise _Rejected(AutoTimeEntryStatus.CLOSED, "period_closed")
                spans = free_spans(start, end, [e for e in in_the_way if e.is_automatic])
        except _Rejected as rejected:
            return AutoTimeEntryOutcome(
                client_ref=item.client_ref, status=rejected.status, error=rejected.error
            )

        if receipt.mode is AutoEntryMode.OVERRIDE:
            for span_start, span_end in spans:
                manual = [
                    e
                    for e in self._entries.find_overlapping(user_id, span_start, span_end)
                    if not e.is_automatic
                ]
                self._carve_manual(user_id, item, span_start, span_end, manual, now)
        last = mine[-1] if mine else None
        for span_start, span_end in spans:
            if last is not None and last.ended_at == span_start:
                last.ended_at = span_end
                last = self._entries.save(last)
            else:
                last = self._entries.save(
                    _automatic(user_id, item, span_start, span_end, receipt.mode)
                )
        self._receipts.extend(user_id, item.client_ref, end)
        self._uow.commit()
        logger.info(
            "自動の打刻を伸ばしました",
            extra={
                "event": "time_entries.auto.extended",
                "user_id": user_id,
                "client_ref": item.client_ref,
                "mode": receipt.mode.value,
            },
        )
        return AutoTimeEntryOutcome(
            client_ref=item.client_ref,
            status=AutoTimeEntryStatus.EXTENDED,
            views=[
                _view(e, now, self._tasks, titles)
                for e in self._entries.find_by_client_ref(user_id, item.client_ref)
            ],
        )

    def _ensure_can_override(self, user_id: int, in_the_way: list[TimeEntry]) -> None:
        """ほかの自動の打刻とは重ねない。切り抜く手の打刻が締めた期間に掛かっていれば、切り抜きも起こさない。"""
        if any(e.is_automatic for e in in_the_way):
            raise _Rejected(AutoTimeEntryStatus.OVERLAP, "overlaps_automatic_entry")
        if any(self._is_closed(user_id, e.started_at, e.ended_at) for e in in_the_way):
            raise _Rejected(AutoTimeEntryStatus.CLOSED, "period_closed")

    def _override(
        self,
        user_id: int,
        item: AutoTimeEntryItem,
        start: datetime,
        end: datetime,
        in_the_way: list[TimeEntry],
        now: datetime,
    ) -> list[TimeEntry]:
        """手の打刻のその時間を切り抜いて作る。切り抜く前の手の打刻は記録に残す。"""
        self._carve_manual(user_id, item, start, end, in_the_way, now)
        return [self._entries.save(_automatic(user_id, item, start, end, AutoEntryMode.OVERRIDE))]

    def _carve_manual(
        self,
        user_id: int,
        item: AutoTimeEntryItem,
        start: datetime,
        end: datetime,
        in_the_way: list[TimeEntry],
        now: datetime,
    ) -> None:
        """``[start, end)`` に掛かる手の打刻を切り抜く。切り抜く前の手の打刻は記録に残す。"""
        for manual in in_the_way:
            assert manual.id is not None
            carving = carve(manual, start, end)
            self._carvings.add(
                TimeEntryCarving(
                    id=None,
                    user_id=user_id,
                    client_ref=item.client_ref,
                    time_entry_id=manual.id,
                    action=carving.action,
                    task_id=manual.task_id,
                    source=manual.source.value,
                    memo=manual.memo,
                    started_at=manual.started_at,
                    ended_at=manual.ended_at,
                    window_started_at=start,
                    window_ended_at=end,
                    carved_at=now,
                )
            )
            # 走っている打刻を閉じてから、続きを走らせる（1 人 1 本の索引）
            if carving.remaining is None:
                self._entries.delete(manual.id)
            else:
                self._entries.save(carving.remaining)
            if carving.continuation is not None:
                self._entries.save(carving.continuation)
            logger.info(
                "例外作業で手の打刻を切り抜きました",
                extra={
                    "event": "time_entries.auto.carved",
                    "user_id": user_id,
                    "time_entry_id": manual.id,
                    "action": carving.action.value,
                    "client_ref": item.client_ref,
                },
            )

    def _duplicate(
        self, user_id: int, item: AutoTimeEntryItem, now: datetime, titles: dict[int, str | None]
    ) -> AutoTimeEntryOutcome:
        entries = self._entries.find_by_client_ref(user_id, item.client_ref)
        return AutoTimeEntryOutcome(
            client_ref=item.client_ref,
            status=AutoTimeEntryStatus.DUPLICATE,
            views=[_view(e, now, self._tasks, titles) for e in entries],
        )

    def _is_closed(self, user_id: int, start: datetime, end: datetime | None) -> bool:
        """``[start, end)`` が確定済みの締めの期間に掛かるか（``TimeEntryUseCases._closed_period`` と同じ判定）。"""
        if end is not None and end <= start:
            end = start + timedelta(microseconds=1)
        return bool(self._closing_periods.find_overlapping(user_id, start, end))


def _view(
    entry: TimeEntry, now: datetime, tasks: OwnedTaskLookup, titles: dict[int, str | None]
) -> TimeEntryView:
    return build_time_entry_view(entry, now, tasks, titles)


def _automatic(
    user_id: int, item: AutoTimeEntryItem, start: datetime, end: datetime, mode: AutoEntryMode
) -> TimeEntry:
    return TimeEntry(
        id=None,
        user_id=user_id,
        started_at=start,
        ended_at=end,
        task_id=item.task_id,
        source=TimeEntrySource.AUTO,
        client_ref=item.client_ref,
        auto_mode=mode,
    )


def _extends(receipt: AutoTimeEntryReceipt, item: AutoTimeEntryItem) -> bool:
    """同じ区間の続き（始まり・タスク・mode が同じで、終わりだけ遅い）か。区間を持たない古い控えは伸ばさない。"""
    return (
        receipt.started_at is not None
        and receipt.ended_at is not None
        and item.started_at.replace(microsecond=0) == receipt.started_at
        and item.task_id == receipt.task_id
        and item.mode == receipt.mode.value
        and item.ended_at.replace(microsecond=0) > receipt.ended_at
    )


def _mode(raw: str) -> AutoEntryMode:
    try:
        return AutoEntryMode(raw)
    except ValueError:
        raise _Rejected(AutoTimeEntryStatus.INVALID, "unknown_mode") from None


def _window(item: AutoTimeEntryItem, now: datetime) -> tuple[datetime, datetime]:
    """区間の始まりと終わり（naive な UTC）。範囲の外は invalid。

    範囲は押した時刻（ADR-0018）と同じ: 未来は ``CLOCK_SKEW_ALLOWANCE`` まで「今」に寄せ、
    それより先は断る。``MAX_PRESS_AGE`` より前に始まる区間も断る。秒未満は落とす。
    """
    started_at = item.started_at.replace(microsecond=0)
    ended_at = item.ended_at.replace(microsecond=0)
    if ended_at <= started_at:
        raise _Rejected(AutoTimeEntryStatus.INVALID, "ended_not_after_started")
    if started_at > now + CLOCK_SKEW_ALLOWANCE or ended_at > now + CLOCK_SKEW_ALLOWANCE:
        raise _Rejected(AutoTimeEntryStatus.INVALID, "in_future")
    if started_at < now - MAX_PRESS_AGE:
        raise _Rejected(AutoTimeEntryStatus.INVALID, "too_old")
    started_at, ended_at = min(started_at, now), min(ended_at, now)
    if ended_at <= started_at:
        # 寄せたら長さが無くなった（ほぼ今に始まって、時計のずれの分だけ先で終わる区間）
        raise _Rejected(AutoTimeEntryStatus.INVALID, "ended_not_after_started")
    return started_at, ended_at


__all__ = ["MAX_AUTO_ENTRIES_PER_REQUEST", "AutomaticTimeEntryUseCases"]
