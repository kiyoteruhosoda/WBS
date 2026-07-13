from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from src.domain.value_objects.dependency_type import DependencyType


@dataclass
class TaskDependency:
    predecessor_task_id: int
    successor_task_id: int
    dependency_type: DependencyType = DependencyType.FS
    lag_days: int = 0
    created_at: datetime | None = None
