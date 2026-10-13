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
    AutoTimeEntryItem,
    AutoTimeEntryOutcome,
    AutoTimeEntryStatus,
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
from src.domain.entities.closing_period import ClosingPeriod
from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import ConflictError, NotFoundError, ValidationError
from src.domain.repositories.closing_period_repository import ClosingPeriodRepository
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.domain.value_objects.press_time import (
    CLOCK_SKEW_ALLOWANCE,
    MAX_PRESS_AGE,
    effective_press_time,
)
from src.domain.value_objects.time_entry_source import TimeEntrySource
from src.shared.clock import utcnow

MAX_ENTRIES_PER_OPERATION = 500
"""まとめて扱う打刻の上限（結合・まとめてタスクを振る）。"""

MAX_AUTO_ENTRIES_PER_REQUEST = 200
"""自動の打刻を 1 回に受け取る上限（WinTrack、ADR-0042）。"""


class _AutoEntryRejected(Exception):
    """自動の打刻の 1 区間を作らない理由（``record_automatic`` の中だけで使う）。"""

    def __init__(self, status: AutoTimeEntryStatus, error: str) -> None:
        super().__init__(error)
        self.status = status
        self.error = error


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

    # ── PC の自動記録（WinTrack、task #379 / ADR-0042） ──────────────────────

    def record_automatic(
        self, user_id: int, items: list[AutoTimeEntryItem]
    ) -> list[AutoTimeEntryOutcome]:
        """PC が記録した区間をまとめて打刻にする（``source=auto``）。**1 区間ずつ**結果を返す。

        1 区間を断っても残りは作る（1 件ずつ確定する）。同じ ``client_ref`` が既にあれば送り直しと
        みなし、中身が違っても上書きせずに既にある打刻を返す。重なり・締めた期間・範囲の外は作らない。
        判定の順は「送り直し → 範囲とタスク → 締め → 重なり」。同じ回の中で先に作った区間とも重ならない。
        """
        if len(items) > MAX_AUTO_ENTRIES_PER_REQUEST:
            raise ValidationError(
                f"too many entries (at most {MAX_AUTO_ENTRIES_PER_REQUEST} at once)"
            )
        now = self._now()
        titles: dict[int, str | None] = {}
        return [self._record_one_automatic(user_id, item, now, titles) for item in items]

    def _record_one_automatic(
        self,
        user_id: int,
        item: AutoTimeEntryItem,
        now: datetime,
        titles: dict[int, str | None],
    ) -> AutoTimeEntryOutcome:
        existing = self._entries.find_by_client_ref(user_id, item.client_ref)
        if existing is not None:
            return self._duplicate(existing, item, now, titles)
        try:
            started_at, ended_at = _automatic_window(item, now)
            if self._tasks.find_by_id_for_user(item.task_id, user_id) is None:
                raise _AutoEntryRejected(AutoTimeEntryStatus.INVALID, "task_not_found")
            if self._closed_period(user_id, started_at, ended_at) is not None:
                raise _AutoEntryRejected(AutoTimeEntryStatus.CLOSED, "period_closed")
            if self._entries.find_overlapping(user_id, started_at, ended_at):
                raise _AutoEntryRejected(AutoTimeEntryStatus.OVERLAP, "overlaps_time_entry")
        except _AutoEntryRejected as rejected:
            return AutoTimeEntryOutcome(
                client_ref=item.client_ref, status=rejected.status, error=rejected.error
            )
        entry = TimeEntry(
            id=None,
            user_id=user_id,
            started_at=started_at,
            ended_at=ended_at,
            task_id=item.task_id,
            source=TimeEntrySource.AUTO,
            client_ref=item.client_ref,
        )
        try:
            saved = self._entries.save(entry)
        except ConflictError:
            # 同じ区間を同時に送り直した（一意索引に当たった）。先に入った方を返す
            existing = self._entries.find_by_client_ref(user_id, item.client_ref)
            if existing is None:
                raise
            return self._duplicate(existing, item, now, titles)
        self._uow.commit()
        return AutoTimeEntryOutcome(
            client_ref=item.client_ref,
            status=AutoTimeEntryStatus.CREATED,
            view=self._view(saved, now, titles),
        )

    def _duplicate(
        self,
        existing: TimeEntry,
        item: AutoTimeEntryItem,
        now: datetime,
        titles: dict[int, str | None],
    ) -> AutoTimeEntryOutcome:
        return AutoTimeEntryOutcome(
            client_ref=item.client_ref,
            status=AutoTimeEntryStatus.DUPLICATE,
            view=self._view(existing, now, titles),
        )

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
        period = self._closed_period(user_id, start, end)
        if period is not None:
            raise ConflictError(
                f"The closing period {period.first_day}..{period.last_day} is closed;"
                " reopen it to change its time entries"
            )

    def _closed_period(
        self, user_id: int, start: datetime, end: datetime | None
    ) -> ClosingPeriod | None:
        """``[start, end)`` が掛かる確定済みの期間（無ければ None）。判定は ``_ensure_open`` と同じ。"""
        if self._closing_periods is None:
            return None
        if end is not None and end <= start:
            end = start + timedelta(microseconds=1)
        closed = self._closing_periods.find_overlapping(user_id, start, end)
        return closed[0] if closed else None

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


def _automatic_window(item: AutoTimeEntryItem, now: datetime) -> tuple[datetime, datetime]:
    """自動の区間の始まりと終わり（naive な UTC）。範囲の外は ``_AutoEntryRejected``（invalid）。

    範囲は押した時刻（ADR-0018）と同じ: 未来は ``CLOCK_SKEW_ALLOWANCE`` まで「今」に寄せ、
    それより先は断る。``MAX_PRESS_AGE`` より前に始まる区間も断る。秒未満は落とす。
    """
    started_at = item.started_at.replace(microsecond=0)
    ended_at = item.ended_at.replace(microsecond=0)
    if ended_at <= started_at:
        raise _AutoEntryRejected(AutoTimeEntryStatus.INVALID, "ended_not_after_started")
    if started_at > now + CLOCK_SKEW_ALLOWANCE or ended_at > now + CLOCK_SKEW_ALLOWANCE:
        raise _AutoEntryRejected(AutoTimeEntryStatus.INVALID, "in_future")
    if started_at < now - MAX_PRESS_AGE:
        raise _AutoEntryRejected(AutoTimeEntryStatus.INVALID, "too_old")
    started_at, ended_at = min(started_at, now), min(ended_at, now)
    if ended_at <= started_at:
        # 寄せたら長さが無くなった（ほぼ今に始まって、時計のずれの分だけ先で終わる区間）
        raise _AutoEntryRejected(AutoTimeEntryStatus.INVALID, "ended_not_after_started")
    return started_at, ended_at


def _entry_order(entry: TimeEntry) -> tuple[datetime, int]:
    return (entry.started_at, entry.id or 0)
