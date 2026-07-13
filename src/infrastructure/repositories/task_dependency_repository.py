from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from sqlalchemy import select
from src.domain.entities.task_dependency import TaskDependency
from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.value_objects.dependency_type import DependencyType
from src.infrastructure.database.models import TaskDependencyModel


class SqlAlchemyTaskDependencyRepository(TaskDependencyRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_task(self, task_id: int) -> list[TaskDependency]:
        stmt = select(TaskDependencyModel).where(
            (TaskDependencyModel.predecessor_task_id == task_id) |
            (TaskDependencyModel.successor_task_id == task_id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def find_all_successors(self, predecessor_id: int) -> list[TaskDependency]:
        stmt = select(TaskDependencyModel).where(
            TaskDependencyModel.predecessor_task_id == predecessor_id
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def save(self, dep: TaskDependency) -> TaskDependency:
        model = self._session.get(
            TaskDependencyModel,
            (dep.predecessor_task_id, dep.successor_task_id)
        )
        if model is None:
            model = TaskDependencyModel(
                predecessor_task_id=dep.predecessor_task_id,
                successor_task_id=dep.successor_task_id,
                dependency_type=dep.dependency_type.value if isinstance(dep.dependency_type, DependencyType) else dep.dependency_type,
                lag_days=dep.lag_days,
            )
            self._session.add(model)
        else:
            model.dependency_type = dep.dependency_type.value if isinstance(dep.dependency_type, DependencyType) else dep.dependency_type
            model.lag_days = dep.lag_days
        self._session.flush()
        return self._to_entity(model)

    def delete(self, predecessor_id: int, successor_id: int) -> None:
        model = self._session.get(TaskDependencyModel, (predecessor_id, successor_id))
        if model:
            self._session.delete(model)
            self._session.flush()

    def get_all_dependencies(self) -> list[TaskDependency]:
        stmt = select(TaskDependencyModel)
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def _to_entity(self, model: TaskDependencyModel) -> TaskDependency:
        return TaskDependency(
            predecessor_task_id=model.predecessor_task_id,
            successor_task_id=model.successor_task_id,
            dependency_type=DependencyType(model.dependency_type),
            lag_days=model.lag_days,
            created_at=model.created_at,
        )
