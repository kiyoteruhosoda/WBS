from __future__ import annotations
from datetime import datetime
from pydantic import BaseModel
from src.domain.value_objects.dependency_type import DependencyType


class DependencyCreateRequest(BaseModel):
    predecessor_task_id: int
    dependency_type: DependencyType = DependencyType.FS
    lag_days: int = 0


class DependencyResponse(BaseModel):
    predecessor_task_id: int
    successor_task_id: int
    dependency_type: str
    lag_days: int
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class TaskDependenciesResponse(BaseModel):
    task_id: int
    predecessors: list[DependencyResponse]
    successors: list[DependencyResponse]
