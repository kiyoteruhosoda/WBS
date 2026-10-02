"""予定のカレンダー・表示の選択・表示の組み合わせのユースケース（task #191 / ADR-0027）。

- 一覧（並び順）。既定のカレンダーが無ければここで作る
- 作る（最初から表示）・名前と色を変える・並べ替える・消す（既定は消せない。予定は既定へ移る）
- 仕事 / プライベート（ADR-0033）。タスクを結んだ予定のあるカレンダーはプライベートにできない（409）
- 取り込んだカレンダー（ADR-0037）を消すと、読み込んだ回と読み込みの状態（購読の URL）も消える
- 表示の選択（どれを出すか）はサーバーに覚える。全部をまとめて置き換える
- 表示の組み合わせ: 名前付きで覚え、当てると入っているカレンダーだけが表示になる

どの操作も ``user_id`` で持ち主を確かめる（他人のカレンダー・組み合わせは「無い」= 404）。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Sequence
from datetime import datetime

from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.calendar import Calendar, CalendarScope
from src.domain.entities.calendar_view_preset import CalendarViewPreset
from src.domain.exceptions import ConflictError, NotFoundError
from src.domain.repositories.calendar_event_repository import CalendarEventRepository
from src.domain.repositories.calendar_import_repository import (
    CalendarImportRepository,
    ImportedOccurrenceRepository,
)
from src.domain.repositories.calendar_repository import (
    CalendarRepository,
    CalendarViewPresetRepository,
)
from src.domain.services.default_calendar import ensure_day_off_layers, ensure_default_calendar
from src.domain.value_objects.event_color import EventColorKey
from src.domain.value_objects.recurrence import Weekday
from src.shared.clock import utcnow


class CalendarUseCases:
    def __init__(
        self,
        calendars: CalendarRepository,
        presets: CalendarViewPresetRepository,
        events: CalendarEventRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
        imports: CalendarImportRepository | None = None,
        imported_occurrences: ImportedOccurrenceRepository | None = None,
    ) -> None:
        self._calendars = calendars
        # 取り込んだカレンダー（ADR-0037）を消すときに、回と読み込みの状態も消す。
        self._imports = imports
        self._imported_occurrences = imported_occurrences
        self._presets = presets
        self._events = events
        self._uow = unit_of_work
        self._now = now

    # ── カレンダー ──────────────────────────────────────────────────────

    def list_calendars(self, user_id: int) -> list[Calendar]:
        """並び順で。既定のカレンダーと休みの 4 層（ADR-0029）が無ければ作ってから返す。"""
        now = self._now()
        created = False
        if not any(c.is_default and c.holds_events for c in self._calendars.find_all(user_id)):
            ensure_default_calendar(self._calendars, user_id, now)
            created = True
        created = ensure_day_off_layers(self._calendars, user_id, now) or created
        if created:
            self._uow.commit()
        return self._calendars.find_all(user_id)

    def create_calendar(
        self,
        user_id: int,
        name: str,
        color_key: EventColorKey,
        scope: CalendarScope = CalendarScope.WORK,
    ) -> Calendar:
        """末尾に足す。最初から表示（新しく作ったものを選び直させない）。"""
        existing = self.list_calendars(user_id)
        calendar = Calendar.create(
            user_id=user_id, name=name, color_key=color_key,
            sort_order=max((c.sort_order for c in existing), default=-1) + 1,
            created_at=self._now(), scope=scope,
        )
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def update_calendar(
        self,
        calendar_id: int,
        user_id: int,
        name: str,
        color_key: EventColorKey,
        *,
        counts_as_day_off: bool | None = None,
        workdays: Iterable[Weekday] | None = None,
        scope: CalendarScope | None = None,
    ) -> Calendar:
        """名前と色。休みの層なら「休みとして数える」・稼働する曜日も、予定のカレンダーなら仕事 / プライベートも
        （``None`` は今のまま）。"""
        calendar = self._owned(calendar_id, user_id)
        now = self._now()
        calendar.change(name=name, color_key=color_key, updated_at=now)
        if scope is not None and scope != calendar.scope:
            if scope == CalendarScope.PRIVATE and self._events.count_linked_to_tasks(user_id, calendar_id):
                raise ConflictError(
                    "a calendar holding events linked to tasks cannot be private"
                )
            calendar.change_scope(scope, now)
        if counts_as_day_off is not None or workdays is not None:
            calendar.change_layer(
                counts_as_day_off=counts_as_day_off, workdays=workdays, updated_at=now
            )
        saved = self._calendars.save(calendar)
        self._uow.commit()
        return saved

    def reorder_calendars(self, user_id: int, calendar_ids: Sequence[int]) -> list[Calendar]:
        """渡した順に並べる。渡さなかったものはその後ろに、今の順のまま。"""
        current = self.list_calendars(user_id)
        by_id = {c.id: c for c in current}
        ordered_ids = list(dict.fromkeys(calendar_ids))
        for calendar_id in ordered_ids:
            if calendar_id not in by_id:
                raise NotFoundError("Calendar", calendar_id)
        rest = [c.id for c in current if c.id not in set(ordered_ids)]
        now = self._now()
        for index, calendar_id in enumerate([*ordered_ids, *rest]):
            calendar = by_id[calendar_id]
            calendar.place_at(index, now)
            self._calendars.save(calendar)
        self._uow.commit()
        return self._calendars.find_all(user_id)

    def delete_calendar(self, calendar_id: int, user_id: int) -> int:
        """消す。中の予定は既定のカレンダーへ移す（移した件数を返す）。既定は消せない（409）。

        取り込んだカレンダーは、読み込んだ回と読み込みの状態（購読の URL）も消す（移す予定は無い）。
        """
        calendar = self._owned(calendar_id, user_id)
        if calendar.is_default:
            raise ConflictError("the default calendar cannot be deleted")
        if calendar.is_day_off_layer:
            raise ConflictError("a day-off layer cannot be deleted (hide it or stop counting it)")
        moved = 0
        if calendar.is_imported:
            if self._imported_occurrences is not None:
                self._imported_occurrences.delete_all(calendar_id)
            if self._imports is not None:
                self._imports.delete(calendar_id)
        else:
            default = ensure_default_calendar(self._calendars, user_id, self._now())
            assert default.id is not None
            moved = self._events.reassign_calendar(user_id, calendar_id, default.id)
        now = self._now()
        for preset in self._presets.find_all(user_id):
            if preset.forget_calendar(calendar_id, now):
                self._presets.save(preset)
        self._calendars.delete(calendar_id)
        self._uow.commit()
        return moved

    # ── 表示の選択 ──────────────────────────────────────────────────────

    def set_visible_calendars(self, user_id: int, visible_ids: Iterable[int]) -> list[Calendar]:
        """表示するカレンダーを、渡したものだけにする（ほかは隠す）。他人・無い id は 404。"""
        current = self.list_calendars(user_id)
        visible = set(visible_ids)
        known = {c.id for c in current}
        for calendar_id in visible:
            if calendar_id not in known:
                raise NotFoundError("Calendar", calendar_id)
        self._show_only(current, visible)
        self._uow.commit()
        return self._calendars.find_all(user_id)

    def _show_only(self, calendars: Iterable[Calendar], visible: set[int]) -> None:
        now = self._now()
        for calendar in calendars:
            before = calendar.is_visible
            calendar.show(calendar.id in visible, now)
            if calendar.is_visible != before:
                self._calendars.save(calendar)

    # ── 表示の組み合わせ ────────────────────────────────────────────────

    def list_presets(self, user_id: int) -> list[CalendarViewPreset]:
        return self._presets.find_all(user_id)

    def create_preset(
        self, user_id: int, name: str, calendar_ids: Iterable[int]
    ) -> CalendarViewPreset:
        ids = self._owned_ids(user_id, calendar_ids)
        existing = self._presets.find_all(user_id)
        now = self._now()
        preset = CalendarViewPreset(
            id=None, user_id=user_id, name=name, calendar_ids=ids,
            sort_order=max((p.sort_order for p in existing), default=-1) + 1,
            created_at=now, updated_at=now,
        )
        saved = self._presets.save(preset)
        self._uow.commit()
        return saved

    def update_preset(
        self, preset_id: int, user_id: int, name: str, calendar_ids: Iterable[int]
    ) -> CalendarViewPreset:
        preset = self._owned_preset(preset_id, user_id)
        preset.change(
            name=name, calendar_ids=self._owned_ids(user_id, calendar_ids), updated_at=self._now()
        )
        saved = self._presets.save(preset)
        self._uow.commit()
        return saved

    def delete_preset(self, preset_id: int, user_id: int) -> None:
        self._owned_preset(preset_id, user_id)
        self._presets.delete(preset_id)
        self._uow.commit()

    def apply_preset(self, preset_id: int, user_id: int) -> list[Calendar]:
        """組み合わせを当てる: 入っているカレンダーだけを表示にする（消えたカレンダーは飛ばす）。"""
        preset = self._owned_preset(preset_id, user_id)
        self._show_only(self.list_calendars(user_id), set(preset.calendar_ids))
        self._uow.commit()
        return self._calendars.find_all(user_id)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _owned(self, calendar_id: int, user_id: int) -> Calendar:
        return owned_by(
            self._calendars.find_by_id(calendar_id), user_id,
            resource="Calendar", resource_id=calendar_id,
        )

    def _owned_preset(self, preset_id: int, user_id: int) -> CalendarViewPreset:
        return owned_by(
            self._presets.find_by_id(preset_id), user_id,
            resource="CalendarViewPreset", resource_id=preset_id,
        )

    def _owned_ids(self, user_id: int, calendar_ids: Iterable[int]) -> tuple[int, ...]:
        known = {c.id for c in self.list_calendars(user_id)}
        ids = tuple(dict.fromkeys(calendar_ids))
        for calendar_id in ids:
            if calendar_id not in known:
                raise NotFoundError("Calendar", calendar_id)
        return ids


__all__ = ["CalendarUseCases"]
