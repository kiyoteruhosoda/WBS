"""PC の自動記録の規則（WinTrack、task #381 / ADR-0043）。

編集（作る・直す・消す・並べ替え）は WBS の画面から。PC の係は使える規則を上からの順に取っていき、
自分の中で照合する（WBS は表題を受け取らない）。

両方空の規則は「それ以外すべて」（ADR-0045）: 利用者ごとに 1 つまで、いつも最後に当てる。

**タスクを消した・完了や中止にしたときも規則は消さない。** PC へ渡す一覧から外し（その区間は未分類に
なる）、画面では「タスクが使えない」と出して付け替えられるようにする。タスクを開き直せば戻る。
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import datetime

from src.application.dto.tracking_rule_dto import (
    CreateTrackingRuleCommand,
    TrackableTask,
    TrackingRuleFeed,
    TrackingRuleView,
    UpdateTrackingRuleCommand,
)
from src.application.dto.unset import UnsetType
from src.application.ports.unit_of_work import UnitOfWork
from src.application.use_cases.ownership import owned_by
from src.domain.entities.task import Task
from src.domain.entities.tracking_rule import TrackingRule, in_matching_order
from src.domain.exceptions import NotFoundError, ValidationError
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.repositories.task_repository import TaskRepository
from src.domain.repositories.tracking_rule_repository import TrackingRuleRepository
from src.shared.clock import utcnow

MAX_RULES_PER_USER = 500
"""1 人が持てる規則の上限（PC は全部を毎回取ってくる）。"""

NEVER_CHANGED = datetime(1970, 1, 1)
"""規則を一度も変えていない利用者の ``updated_at``（naive な UTC）。"""


class TrackingRuleUseCases:
    def __init__(
        self,
        rules: TrackingRuleRepository,
        tasks: TaskRepository,
        projects: ProjectRepository,
        unit_of_work: UnitOfWork,
        *,
        now: Callable[[], datetime] = utcnow,
    ) -> None:
        self._rules = rules
        self._tasks = tasks
        self._projects = projects
        self._uow = unit_of_work
        self._now = now

    # ── 引く ────────────────────────────────────────────────────────────

    def list_rules(self, user_id: int) -> list[TrackingRuleView]:
        """編集の画面の一覧（使えない規則も含めて、上からの順）。"""
        tasks = self._tasks_by_id(user_id)
        return [_view(rule, tasks) for rule in in_matching_order(self._rules.find_all(user_id))]

    def feed(self, user_id: int) -> TrackingRuleFeed:
        """PC の係へ渡す規則。使えるものだけを上からの順に。

        ``updated_at`` は規則を最後に変えた時刻と、規則の行き先のタスクを最後に変えた時刻
        （名前が変わった・完了にした・消した）の遅いほう。PC はこれが変わったら取り直せばよい。
        """
        tasks = self._tasks_by_id(user_id)
        rules = in_matching_order(self._rules.find_all(user_id))
        stamps = [
            self._rules.last_changed_at(user_id) or NEVER_CHANGED,
            self._rules.last_task_change_at(user_id) or NEVER_CHANGED,
        ]
        views = [_view(rule, tasks) for rule in rules]
        return TrackingRuleFeed(
            rules=[v for v in views if v.task_available], updated_at=max(stamps)
        )

    def trackable_tasks(self, user_id: int) -> list[TrackableTask]:
        """打刻を付けられる開いているタスク（プロジェクト名 → 題名の順）。"""
        project_names = {p.id: p.name for p in self._projects.find_all(user_id)}
        found = [
            TrackableTask(
                id=task.id,
                title=task.title,
                project_title=(
                    project_names.get(task.project_id) if task.project_id is not None else None
                ),
            )
            for task in self._tasks.find_all(user_id, {})
            if task.id is not None and task.is_open
        ]
        return sorted(found, key=lambda t: (t.project_title is None, t.project_title or "", t.title, t.id))

    # ── 編集 ────────────────────────────────────────────────────────────

    def create(self, command: CreateTrackingRuleCommand) -> TrackingRuleView:
        """いちばん下に足す。タスクは自分の開いているもの。"""
        user_id = command.user_id
        task = self._open_task(command.task_id, user_id)
        existing = self._rules.find_all(user_id)
        if len(existing) >= MAX_RULES_PER_USER:
            raise ValidationError(f"too many rules (at most {MAX_RULES_PER_USER})")
        rule = TrackingRule.create(
            user_id=user_id,
            position=max((r.position for r in existing), default=-1) + 1,
            task_id=task.id or command.task_id,
            app=command.app,
            title_contains=command.title_contains,
        )
        _ensure_one_everything_else(rule, existing)
        saved = self._rules.save(rule)
        self._changed(user_id)
        return _view(saved, {command.task_id: task})

    def update(
        self, rule_id: int, user_id: int, command: UpdateTrackingRuleCommand
    ) -> TrackingRuleView:
        rule = self._owned(rule_id, user_id)
        if not isinstance(command.task_id, UnsetType):
            self._open_task(command.task_id, user_id)
            rule.task_id = command.task_id
        if not isinstance(command.app, UnsetType) or not isinstance(
            command.title_contains, UnsetType
        ):
            rule.change_condition(
                app=rule.app if isinstance(command.app, UnsetType) else command.app,
                title_contains=(
                    rule.title_contains
                    if isinstance(command.title_contains, UnsetType)
                    else command.title_contains
                ),
            )
            _ensure_one_everything_else(rule, self._rules.find_all(user_id))
        saved = self._rules.save(rule)
        self._changed(user_id)
        return _view(saved, self._tasks_by_id(user_id))

    def delete(self, rule_id: int, user_id: int) -> None:
        self._owned(rule_id, user_id)
        self._rules.delete(rule_id)
        self._changed(user_id)

    def reorder(self, user_id: int, rule_ids: Sequence[int]) -> list[TrackingRuleView]:
        """渡した順に並べる。渡さなかったものはその後ろに、今の順のまま。「それ以外すべて」はいつも最後。"""
        current = in_matching_order(self._rules.find_all(user_id))
        by_id = {r.id: r for r in current}
        ordered = list(dict.fromkeys(rule_ids))
        for rule_id in ordered:
            if rule_id not in by_id:
                raise NotFoundError("TrackingRule", rule_id)
        rest = [r.id for r in current if r.id not in set(ordered)]
        last = [r.id for r in current if r.is_everything_else]
        sequence = [i for i in [*ordered, *rest] if i not in last] + last
        for position, rule_id in enumerate(sequence):
            rule = by_id[rule_id]
            if rule.position != position:
                rule.position = position
                self._rules.save(rule)
        self._changed(user_id)
        return self.list_rules(user_id)

    # ── 内側 ────────────────────────────────────────────────────────────

    def _changed(self, user_id: int) -> None:
        self._rules.mark_changed(user_id, self._now())
        self._uow.commit()

    def _owned(self, rule_id: int, user_id: int) -> TrackingRule:
        return owned_by(
            self._rules.find_by_id(rule_id), user_id, resource="TrackingRule", resource_id=rule_id
        )

    def _open_task(self, task_id: int, user_id: int) -> Task:
        task = self._tasks.find_by_id_for_user(task_id, user_id)
        if task is None:
            raise NotFoundError("Task", task_id)
        if not task.is_open:
            raise ValidationError("a rule cannot point to a done or cancelled task")
        return task

    def _tasks_by_id(self, user_id: int) -> dict[int, Task]:
        return {t.id: t for t in self._tasks.find_all(user_id, {}) if t.id is not None}


def _ensure_one_everything_else(rule: TrackingRule, existing: list[TrackingRule]) -> None:
    """「それ以外すべて」（両方空）は利用者ごとに 1 つまで。"""
    if rule.is_everything_else and any(
        r.is_everything_else and r.id != rule.id for r in existing
    ):
        raise ValidationError(
            "there is already an 'everything else' rule (both app and title_contains empty)"
        )


def _view(rule: TrackingRule, tasks: dict[int, Task]) -> TrackingRuleView:
    task = tasks.get(rule.task_id)
    return TrackingRuleView(
        rule=rule,
        task_title=task.title if task is not None else None,
        task_available=task is not None and task.is_open,
    )
