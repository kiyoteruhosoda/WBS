"""予定に結ぶタスクが、その利用者のものかを確かめる口。

``TaskRepository``（SQLAlchemy 版）はそのままこの形を満たす。予定のユースケースが
タスクのリポジトリ全体に依存しないよう、使う 1 つだけを切り出す。
"""

from __future__ import annotations

from typing import Protocol

from src.domain.entities.task import Task


class OwnedTaskLookup(Protocol):
    def find_by_id_for_user(self, task_id: int, user_id: int) -> Task | None: ...
