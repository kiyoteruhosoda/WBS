"""打刻のユースケース（task #154 / ADR-0008、締めの補正は task #161 / ADR-0012）。

普段の操作は 2 つだけ: **Start**（走っていれば切り替え）と **Stop**（冪等）。
ほかは画面の上部の表示（いま走っている打刻）と、締めのための補正
（期間の一覧・修正・削除・手での追加・分割・結合・まとめてタスクを振る・予定の回から作る）。

どの操作も ``user_id`` で持ち主を確かめる（他人の打刻は「無い」として扱う）。
**確定した締めの期間に掛かる打刻は書き換えさせない**（``ConflictError`` = 409）。判定は
期間の行が持つ区切りの瞬間で行う（``closing_periods``、ADR-0012）。
「今」は ``now``（既定は ``src.shared.clock.utcnow``）で取り、1 つの操作の中では 1 度だけ読む
（切り替えで、止めた時刻と始めた時刻を同じにするため）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import datetime, timedelta

from src.application.dto.time_entry_dto import (
    CreateTimeEntryCommand,
    EntryFromOccurrenceCommand,
    MergeTimeEntriesCommand,
    SplitTimeEntryResult,
    StartTimerCommand,
    StartTimerResult,
    TimeEntryView,
    UpdateTimeEntryCommand,
)
from src.application.dto.unset import UNSET, UnsetType
from src.application.ports.occurrence_source import NoOccurrences, OccurrenceSource
from src.application.ports.scheduled_task_lookup import NoScheduledTask, ScheduledTaskLookup
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.value_objects.press_time import effective_press_time
from src.domain.value_objects.time_entry_source import TimeEntrySource
from src.shared.clock import utcnow

MAX_ENTRIES_PER_OPERATION = 500
"""まとめて扱う打刻の上限（結合・まとめてタスクを振る）。"""


class TimeEntryUseCases:
    def __init__(
        self,
        entries: TimeEntryRepository,
        tasks: OwnedTaskLookup,
        unit_of_work: UnitOfWork,
        *,
        scheduled_tasks: ScheduledTaskLookup | None = None,
        closing_periods: ClosingPeriodRepository | None = None,
        occurrences: OccurrenceSource | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._entries = entries
        self._tasks = tasks
        self._uow = unit_of_work
        self._scheduled_tasks = scheduled_tasks or NoScheduledTask()
        # None は「締めを繋がない」（打刻だけを見る試験）。API では必ず繋ぐ
        self._closing_periods = closing_periods
        self._occurrences = occurrences or NoOccurrences()
        self._now = now

    # ── 普段の 2 つ ────────────────────────────────────────────────────

    def start(self, command: StartTimerCommand) -> StartTimerResult:
        """始める。走っている打刻があれば、それを同じ時刻で止めてから始める（切り替え）。

        ``command.at``（押した時刻、ADR-0018）があればその時刻で切り替える。走っている打刻と
        同じ時刻の Start は**送り直し**とみなして何もしない（アプリが応答を受け取り損ねて
        もう一度送ったとき、長さ 0 の打刻を作らない）。
        """
        now = self._now()
        at = effective_press_time(command.at, now)
        user_id = command.user_id

        running = self._entries.find_running(user_id)
        if running is not None and command.at is not None:
            if at == running.started_at:
                return StartTimerResult(started=self._view(running, now), stopped=None)
            if at < running.started_at:
                raise ValidationError("at must not be before the running time entry started")
        if at < now:
            self._ensure_no_overlap(user_id, at, now, running)

        task_id = self._task_for_start(user_id, command.task_id, at)
        if running is not None:
            self._ensure_open(user_id, running.started_at, at)
        self._ensure_open(user_id, at, at)

        stopped: TimeEntry | None = None
        if running is not None:
            running.stop(at)
            stopped = self._entries.save(running)

        started = self._entries.save(
            TimeEntry.start(user_id=user_id, at=at, task_id=task_id, memo=command.memo)
        )
        self._uow.commit()
        return StartTimerResult(
            started=self._view(started, now),
            stopped=self._view(stopped, now) if stopped is not None else None,
        )

    def stop(self, user_id: int, at: datetime | None = None) -> TimeEntryView | None:
        """止める。走っていなければ何もせず None（2 度押しても同じ結果になる）。

        ``at``（押した時刻、naive な UTC。ADR-0018）があればその時刻で止める。走っている打刻の
        始まりより前は断る。
        """
        now = self._now()
        stop_at = effective_press_time(at, now)
        running = self._entries.find_running(user_id)
        if running is None:
            return None
        if at is not None and stop_at < running.started_at:
            raise ValidationError("at must not be before the running time entry started")
        self._ensure_open(user_id, running.started_at, stop_at)
        running.stop(stop_at)
        saved = self._entries.save(running)
        self._uow.commit()
        return self._view(saved, now)

    # ── 引く ────────────────────────────────────────────────────────────

    def current(self, user_id: int) -> TimeEntryView | None:
        running = self._entries.find_running(user_id)
        return self._view(running, self._now()) if running is not None else None

    def list_in_period(self, user_id: int, start: datetime, end: datetime) -> list[TimeEntryView]:
        """``[start, end)``（naive な UTC）に掛かる打刻。日をまたぐ打刻は両方の日に出る。"""
        if end <= start:
            raise ValidationError("end must be after start")
        now = self._now()
        titles: dict[int, str | None] = {}
        return [
            self._view(e, now, titles)
            for e in self._entries.find_overlapping(user_id, start, end)
        ]

    def get(self, entry_id: int, user_id: int) -> TimeEntryView:
        return self._view(self._owned(entry_id, user_id), self._now())

    # ── 締めのための補正 ─────────────────────────────────────────────────

    def update(self, entry_id: int, user_id: int, command: UpdateTimeEntryCommand) -> TimeEntryView:
        now = self._now()
        entry = self._owned(entry_id, user_id)
        self._ensure_entry_open(entry)
        if not isinstance(command.started_at, UnsetType) or not isinstance(
            command.ended_at, UnsetType
        ):
            entry.reschedule(
                started_at=(
                    entry.started_at
                    if isinstance(command.started_at, UnsetType)
                    else command.started_at
                ),
                ended_at=(
                    entry.ended_at if isinstance(command.ended_at, UnsetType) else command.ended_at
                ),
                now=now,
            )
            self._ensure_entry_open(entry)
        if not isinstance(command.task_id, UnsetType):
            if command.task_id is not None:
                self._owned_task(command.task_id, user_id)
            entry.task_id = command.task_id
        if not isinstance(command.memo, UnsetType):
            entry.memo = command.memo
        saved = self._entries.save(entry)
        self._uow.commit()
        return self._view(saved, now)

    def delete(self, entry_id: int, user_id: int) -> None:
        self._ensure_entry_open(self._owned(entry_id, user_id))
        self._entries.delete(entry_id)
        self._uow.commit()

    def create(self, command: CreateTimeEntryCommand) -> TimeEntryView:
        """空き時間に打刻を足す（``source=manual``）。止まった打刻だけを作れる。"""
        now = self._now()
        if command.task_id is not None:
            self._owned_task(command.task_id, command.user_id)
        entry = TimeEntry(
            id=None,
            user_id=command.user_id,
            started_at=command.started_at,
            ended_at=command.ended_at,
            task_id=command.task_id,
            memo=command.memo,
            source=TimeEntrySource.MANUAL,
        )
        entry.reschedule(started_at=command.started_at, ended_at=command.ended_at, now=now)
        self._ensure_entry_open(entry)
        saved = self._entries.save(entry)
        self._uow.commit()
        return self._view(saved, now)

    def split(self, entry_id: int, user_id: int, at: datetime) -> SplitTimeEntryResult:
        """``at`` で 2 本に分ける。元の打刻は ``at`` で終わり、``at`` からの新しい打刻
        （``source=split``、タスク・メモは同じ）が続きを持つ。走っている打刻なら新しい方が走り続ける。
        """
        now = self._now()
        entry = self._owned(entry_id, user_id)
        self._ensure_entry_open(entry)
        end = entry.ended_at if entry.ended_at is not None else now
        if not entry.started_at < at < end:
            raise ValidationError("split time must be strictly inside the time entry")
        second = TimeEntry(
            id=None,
            user_id=user_id,
            started_at=at,
            ended_at=entry.ended_at,
            task_id=entry.task_id,
            memo=entry.memo,
            source=TimeEntrySource.SPLIT,
        )
        entry.ended_at = at
        # 走っている打刻を分けるときは、先に元を止めてから続きを入れる（1 人 1 本の索引）
        first_saved = self._entries.save(entry)
        second_saved = self._entries.save(second)
        self._uow.commit()
        return SplitTimeEntryResult(
            first=self._view(first_saved, now), second=self._view(second_saved, now)
        )

    def merge(self, command: MergeTimeEntriesCommand) -> TimeEntryView:
        """打刻をつなぐ。いちばん早い打刻を残して、始まりから最後の終わりまでの 1 本にする。

        間が空いていれば、その間も含めた 1 本になる（「つなぐ」）。走っている打刻はつなげない。
        メモは重ならないものを改行でつなぐ。ほかの打刻は消える。
        """
        now = self._now()
        user_id = command.user_id
        entries = self._owned_many(command.entry_ids, user_id)
        if len(entries) < 2:
            raise ValidationError("merge needs at least two time entries")
        if any(e.is_running for e in entries):
            raise ValidationError("a running time entry cannot be merged; stop it first")
        for e in entries:
            self._ensure_entry_open(e)
        entries.sort(key=lambda e: (e.started_at, e.id or 0))
        keeper, others = entries[0], entries[1:]
        end = max(e.ended_at for e in entries if e.ended_at is not None)
        self._ensure_open(user_id, keeper.started_at, end)

        if isinstance(command.task_id, UnsetType):
            task_id = next((e.task_id for e in entries if e.task_id is not None), None)
        else:
            task_id = command.task_id
            if task_id is not None:
                self._owned_task(task_id, user_id)
        memos: list[str] = []
        for e in entries:
            if e.memo and e.memo not in memos:
                memos.append(e.memo)

        for other in others:
            assert other.id is not None
            self._entries.delete(other.id)
        keeper.ended_at = end
        keeper.task_id = task_id
        keeper.memo = "\n".join(memos) if memos else None
        saved = self._entries.save(keeper)
        self._uow.commit()
        return self._view(saved, now)

    def assign_task(
        self, user_id: int, entry_ids: list[int], task_id: int | None
    ) -> list[TimeEntryView]:
        """まとめてタスクを振る（``None`` は未割当へ戻す）。"""
        now = self._now()
        if task_id is not None:
            self._owned_task(task_id, user_id)
        entries = self._owned_many(entry_ids, user_id)
        if not entries:
            raise ValidationError("entry_ids must not be empty")
        for e in entries:
            self._ensure_entry_open(e)
        saved = []
        for e in entries:
            e.task_id = task_id
            saved.append(self._entries.save(e))
        self._uow.commit()
        titles: dict[int, str | None] = {}
        return [self._view(e, now, titles) for e in sorted(saved, key=_entry_order)]

    def create_from_occurrence(self, command: EntryFromOccurrenceCommand) -> TimeEntryView:
        """予定の回をそのまま打刻にする（「予定どおりやった」を 1 操作で。``source=schedule``）。

        回は（予定の id, 始まりの瞬間）で指す。終日の回・まだ終わっていない回は打刻にできない。
        """
        now = self._now()
        user_id = command.user_id
        day = command.start.date()
        occurrence = next(
            (
                o
                for o in self._occurrences.list_occurrence_views(
                    user_id, day - timedelta(days=1), day + timedelta(days=1), "UTC"
                )
                if o.event_id == command.event_id and o.start_utc == command.start
            ),
            None,
        )
        if occurrence is None:
            raise NotFoundError("Occurrence", f"{command.event_id}@{command.start.isoformat()}")
        if occurrence.is_all_day:
            raise ValidationError("an all-day occurrence cannot be turned into a time entry")
        if isinstance(command.task_id, UnsetType):
            task_id = occurrence.task_id
            if task_id is not None and self._tasks.find_by_id_for_user(task_id, user_id) is None:
                task_id = None
        else:
            task_id = command.task_id
            if task_id is not None:
                self._owned_task(task_id, user_id)
        end = occurrence.start_utc + timedelta(minutes=occurrence.duration_minutes)
        entry = TimeEntry(
            id=None,
            user_id=user_id,
            started_at=occurrence.start_utc,
            ended_at=end,
            task_id=task_id,
            memo=None if task_id is not None else occurrence.title,
            source=TimeEntrySource.SCHEDULE,
        )
        entry.reschedule(started_at=entry.started_at, ended_at=end, now=now)
        self._ensure_entry_open(entry)
        saved = self._entries.save(entry)
        self._uow.commit()
        return self._view(saved, now)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _ensure_no_overlap(
        self, user_id: int, start: datetime, now: datetime, running: TimeEntry | None
    ) -> None:
        """過去の時刻から始める打刻が、ほかの打刻と重ならないか（走っている打刻は除く）。

        溜めた Start を送ったら、その間に締めの画面で手で足した打刻があった、という場合に
        重なった 2 本を作らない。
        """
        running_id = running.id if running is not None else None
        if any(e.id != running_id for e in self._entries.find_overlapping(user_id, start, now)):
            raise ConflictError("at overlaps another time entry")

    def _ensure_entry_open(self, entry: TimeEntry) -> None:
        self._ensure_open(entry.user_id, entry.started_at, entry.ended_at)

    def _ensure_open(self, user_id: int, start: datetime, end: datetime | None) -> None:
        """``[start, end)`` が確定済みの期間に掛かっていれば ``ConflictError``。

        ``end`` が None は走っている打刻（終わりが無い）。長さ 0 は始まりの瞬間で判定する。
        """
        if self._closing_periods is None:
            return
        if end is not None and end <= start:
            end = start + timedelta(microseconds=1)
        closed = self._closing_periods.find_overlapping(user_id, start, end)
        if closed:
            period = closed[0]
            raise ConflictError(
                f"The closing period {period.first_day}..{period.last_day} is closed;"
                " reopen it to change its time entries"
            )

    def _task_for_start(
        self, user_id: int, requested: int | None | UnsetType, now: datetime
    ) -> int | None:
        if requested is UNSET:
            return self._default_task(user_id, now)
        if requested is None:
            return None
        assert isinstance(requested, int)
        self._owned_task(requested, user_id)
        return requested

    def _default_task(self, user_id: int, now: datetime) -> int | None:
        """いまの予定のタスク → 直前の打刻のタスク → 未割当。

        候補のタスクが消されていた（または他人のものだった）ら、次の候補へ進む。
        """
        for candidate in (
            self._scheduled_tasks.task_scheduled_at(user_id, now),
            self._entries.find_latest_task_id(user_id),
        ):
            if (
                candidate is not None
                and self._tasks.find_by_id_for_user(candidate, user_id) is not None
            ):
                return candidate
        return None

    def _view(
        self, entry: TimeEntry, now: datetime, titles: dict[int, str | None] | None = None
    ) -> TimeEntryView:
        return build_time_entry_view(entry, now, self._tasks, titles)

    def _owned(self, entry_id: int, user_id: int) -> TimeEntry:
        return owned_by(
            self._entries.find_by_id(entry_id), user_id,
            resource="TimeEntry", resource_id=entry_id,
        )

    def _owned_many(self, entry_ids: Iterable[int], user_id: int) -> list[TimeEntry]:
        unique = list(dict.fromkeys(entry_ids))
        if len(unique) > MAX_ENTRIES_PER_OPERATION:
            raise ValidationError(
                f"too many time entries (at most {MAX_ENTRIES_PER_OPERATION} at once)"
            )
        return [self._owned(entry_id, user_id) for entry_id in unique]

    def _owned_task(self, task_id: int, user_id: int) -> None:
        if self._tasks.find_by_id_for_user(task_id, user_id) is None:
            raise NotFoundError("Task", task_id)


def build_time_entry_view(
    entry: TimeEntry,
    now: datetime,
    tasks: OwnedTaskLookup,
    titles: dict[int, str | None] | None = None,
) -> TimeEntryView:
    """画面へ返す形。``titles`` は一覧のときにタスク名を引き直さないための控え（task_id → 題名）。"""
    title: str | None = None
    if entry.task_id is not None:
        if titles is not None and entry.task_id in titles:
            title = titles[entry.task_id]
        else:
            task = tasks.find_by_id_for_user(entry.task_id, entry.user_id)
            title = task.title if task is not None else None
            if titles is not None:
                titles[entry.task_id] = title
    return TimeEntryView(
        entry=entry,
        task_title=title,
        duration_seconds=int(entry.duration(now).total_seconds()),
        is_long_running=entry.is_long_running(now),
    )


def _entry_order(entry: TimeEntry) -> tuple[datetime, int]:
    return (entry.started_at, entry.id or 0)
