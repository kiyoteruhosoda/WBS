"""打刻のユースケース（task #154 / ADR-0008）。

普段の操作は 2 つだけ: **Start**（走っていれば切り替え）と **Stop**（冪等）。
ほかは画面の上部の表示（いま走っている打刻）と、締め（#161）のための期間の一覧・1 件の修正・削除。

どの操作も ``user_id`` で持ち主を確かめる（他人の打刻は「無い」として扱う）。
「今」は ``now``（既定は ``src.shared.clock.utcnow``）で取り、1 つの操作の中では 1 度だけ読む
（切り替えで、止めた時刻と始めた時刻を同じにするため）。
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from src.application.dto.time_entry_dto import (
    StartTimerCommand,
    StartTimerResult,
    TimeEntryView,
    UpdateTimeEntryCommand,
)
from src.application.dto.unset import UNSET, UnsetType
from src.application.ports.scheduled_task_lookup import NoScheduledTask, ScheduledTaskLookup
from src.application.ports.task_lookup import OwnedTaskLookup
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.time_entry import TimeEntry
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.repositories.time_entry_repository import TimeEntryRepository
from src.shared.clock import utcnow


class TimeEntryUseCases:
    def __init__(
        self,
        entries: TimeEntryRepository,
        tasks: OwnedTaskLookup,
        unit_of_work: UnitOfWork,
        *,
        scheduled_tasks: ScheduledTaskLookup | None = None,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._entries = entries
        self._tasks = tasks
        self._uow = unit_of_work
        self._scheduled_tasks = scheduled_tasks or NoScheduledTask()
        self._now = now

    # ── 普段の 2 つ ────────────────────────────────────────────────────

    def start(self, command: StartTimerCommand) -> StartTimerResult:
        """始める。走っている打刻があれば、それを同じ時刻で止めてから始める（切り替え）。"""
        now = self._now()
        user_id = command.user_id
        task_id = self._task_for_start(user_id, command.task_id, now)

        stopped: TimeEntry | None = None
        running = self._entries.find_running(user_id)
        if running is not None:
            running.stop(now)
            stopped = self._entries.save(running)

        started = self._entries.save(
            TimeEntry.start(user_id=user_id, at=now, task_id=task_id, memo=command.memo)
        )
        self._uow.commit()
        return StartTimerResult(
            started=self._view(started, now),
            stopped=self._view(stopped, now) if stopped is not None else None,
        )

    def stop(self, user_id: int) -> TimeEntryView | None:
        """止める。走っていなければ何もせず None（2 度押しても同じ結果になる）。"""
        now = self._now()
        running = self._entries.find_running(user_id)
        if running is None:
            return None
        running.stop(now)
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

    # ── 締めのための修正・削除（確定済み期間の保護は締めの段 #161 で足す） ──

    def update(self, entry_id: int, user_id: int, command: UpdateTimeEntryCommand) -> TimeEntryView:
        now = self._now()
        entry = self._owned(entry_id, user_id)
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
        self._owned(entry_id, user_id)
        self._entries.delete(entry_id)
        self._uow.commit()

    # ── 内側 ────────────────────────────────────────────────────────────

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
        """``titles`` は一覧のときにタスク名を引き直さないための控え（task_id → 題名）。"""
        title: str | None = None
        if entry.task_id is not None:
            if titles is not None and entry.task_id in titles:
                title = titles[entry.task_id]
            else:
                task = self._tasks.find_by_id_for_user(entry.task_id, entry.user_id)
                title = task.title if task is not None else None
                if titles is not None:
                    titles[entry.task_id] = title
        return TimeEntryView(
            entry=entry,
            task_title=title,
            duration_seconds=int(entry.duration(now).total_seconds()),
            is_long_running=entry.is_long_running(now),
        )

    def _owned(self, entry_id: int, user_id: int) -> TimeEntry:
        return owned_by(
            self._entries.find_by_id(entry_id), user_id,
            resource="TimeEntry", resource_id=entry_id,
        )

    def _owned_task(self, task_id: int, user_id: int) -> None:
        if self._tasks.find_by_id_for_user(task_id, user_id) is None:
            raise NotFoundError("Task", task_id)
