"""「今日」の画面の要約（task #160 / ADR-0015）。

1 回の問い合わせで、朝に開いた画面が要るものを返す:

- 今日（利用者のタイムゾーン）の区切りと、そこに掛かる打刻（予定のグリッドに重ねる帯）
- いま走っている打刻
- 今日の実績（打刻の長さをタスクごとに足したもの。日をまたぐ打刻は今日の分だけ、走っている打刻は今まで）
- 今日やるべきタスクのうち、まだ予定を取っていないもの

予定の回そのものは返さない（``/api/calendar/occurrences`` に ``date`` の 1 日を問う）。
回の形を 2 か所で持たないため。
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from datetime import date, datetime, timedelta

from src.application.dto.today_dto import TaskActual, TodaySummary
from src.application.use_cases.task_use_cases import TaskUseCases
from src.application.use_cases.time_entry_use_cases import TimeEntryUseCases
from src.application.user_clock import UserClock
from src.domain.services.daily_time_allocation import allocate_by_local_day, whole_seconds
from src.domain.value_objects.task_status import TaskStatus
from src.shared.clock import utcnow

ACTIONABLE_STATUSES = frozenset({TaskStatus.TODO.value, TaskStatus.DOING.value})
"""今日やるべきタスクに数える状態。待機中（WAITING）は自分では進められないので外す。"""

DUE_LOOKAHEAD_DAYS = 1
"""期限がこの日数先（明日）までのタスクを「今日やるべき」に数える。明日締切は今日のうちに時間を取る。"""


def needs_time_today(task: dict, today: date) -> bool:
    """今日やるべきタスクか（期限切れ・今日か明日が期限・開始日を過ぎた・進行中）。"""
    if task["status"] not in ACTIONABLE_STATUSES:
        return False
    due: date | None = task["due_date"]
    start: date | None = task["start_date"]
    if due is not None and due <= today + timedelta(days=DUE_LOOKAHEAD_DAYS):
        return True
    if start is not None and start <= today:
        return True
    return task["status"] == TaskStatus.DOING.value


def lacks_schedule(task: dict) -> bool:
    """まだ予定を取っていないか。

    残があって予定で埋まっていない（``unscheduled_hours`` > 0）もの。残が決まらない
    （見積も残も無い）タスクは、予定を 1 つも取っていなければ数える——数えないと、期限が
    今日なのに見積の無いタスクが画面から消える。
    """
    unscheduled: float | None = task["unscheduled_hours"]
    if unscheduled is not None:
        return unscheduled > 0
    return task["remaining_hours"] is None and not task["scheduled_hours"]


def _schedule_order(task: dict) -> tuple:
    # 優先度の点の高い順 → 期限の近い順（期限なしは後ろ）→ id
    due: date | None = task["due_date"]
    return (-task["priority_score"], due is None, due or date.max, task["id"])


def pick_tasks_to_schedule(tasks: Iterable[dict], today: date) -> list[dict]:
    return sorted(
        (t for t in tasks if needs_time_today(t, today) and lacks_schedule(t)),
        key=_schedule_order,
    )


class TodayUseCases:
    def __init__(
        self,
        clock: UserClock,
        time_entries: TimeEntryUseCases,
        tasks: TaskUseCases,
        *,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._clock = clock
        self._time_entries = time_entries
        self._tasks = tasks
        # 既定は作るときに引く（試験でモジュールの utcnow を差し替えられるように）
        self._now = now or utcnow

    def summary(self, user_id: int) -> TodaySummary:
        today = self._clock.today(user_id)
        zone = self._clock.zone(user_id)
        day_start, day_end = self._clock.utc_window(user_id, today, today)
        now = self._now()

        entries = self._time_entries.list_in_period(user_id, day_start, day_end)
        running = next((v for v in entries if v.entry.is_running), None)

        titles = {v.entry.task_id: v.task_title for v in entries}
        allocated = allocate_by_local_day((v.entry for v in entries), day_start, day_end, zone, now)
        by_task: dict[int | None, timedelta] = {}
        for (task_id, _day), length in allocated.items():
            by_task[task_id] = by_task.get(task_id, timedelta(0)) + length
        actuals = sorted(
            (
                TaskActual(
                    task_id=task_id, task_title=titles.get(task_id), seconds=whole_seconds(length)
                )
                for task_id, length in by_task.items()
            ),
            # 長い順。同じ長さなら未割当を後ろ、あとは id の順
            key=lambda a: (-a.seconds, a.task_id is None, a.task_id or 0),
        )

        return TodaySummary(
            date=today,
            time_zone=self._clock.zone_name(user_id),
            day_start=day_start,
            day_end=day_end,
            server_now=now,
            running=running,
            entries=entries,
            total_seconds=sum(a.seconds for a in actuals),
            actuals=actuals,
            tasks_to_schedule=pick_tasks_to_schedule(self._tasks.list_tasks(user_id, {}), today),
        )


__all__ = [
    "ACTIONABLE_STATUSES",
    "DUE_LOOKAHEAD_DAYS",
    "TodayUseCases",
    "lacks_schedule",
    "needs_time_today",
    "pick_tasks_to_schedule",
]
