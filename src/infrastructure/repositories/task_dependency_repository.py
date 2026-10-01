from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.orm import Session, aliased

from src.domain.entities.task_dependency import TaskDependency
from src.domain.repositories.task_dependency_repository import TaskDependencyRepository
from src.domain.value_objects.dependency_type import DependencyType
from src.infrastructure.database.models import TaskDependencyModel, TaskModel


class SqlAlchemyTaskDependencyRepository(TaskDependencyRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_task_for_user(self, task_id: int, user_id: int) -> list[TaskDependency]:
        stmt = self._owned_by(user_id).where(
            (TaskDependencyModel.predecessor_task_id == task_id)
            | (TaskDependencyModel.successor_task_id == task_id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def find_all_for_user(self, user_id: int) -> list[TaskDependency]:
        return [self._to_entity(m) for m in self._session.scalars(self._owned_by(user_id))]

    def save(self, dep: TaskDependency) -> TaskDependency:
        dependency_type = (
            dep.dependency_type.value
            if isinstance(dep.dependency_type, DependencyType)
            else dep.dependency_type
        )
        model = self._session.get(
            TaskDependencyModel, (dep.predecessor_task_id, dep.successor_task_id)
        )
        if model is None:
            model = TaskDependencyModel(
                predecessor_task_id=dep.predecessor_task_id,
                successor_task_id=dep.successor_task_id,
                dependency_type=dependency_type,
                lag_days=dep.lag_days,
            )
            self._session.add(model)
        else:
            model.dependency_type = dependency_type
            model.lag_days = dep.lag_days
        self._session.commit()
        return self._to_entity(model)

    def delete(self, predecessor_id: int, successor_id: int) -> None:
        model = self._session.get(TaskDependencyModel, (predecessor_id, successor_id))
        if model:
            self._session.delete(model)
            self._session.commit()

    @staticmethod
    def _owned_by(user_id: int) -> Select[tuple[TaskDependencyModel]]:
        # 依存の行には持ち主が無いので、両端のタスクを辿って持ち主を見る。
        # 片端だけ見ると、他人のタスクへ伸びた依存（入口で弾いているが、古いデータに
        # 残りうる）が混ざる。削除済みのタスクは絞らない（従来どおり。表示側で落とす）。
        predecessor = aliased(TaskModel)
        successor = aliased(TaskModel)
        return (
            select(TaskDependencyModel)
            .join(predecessor, predecessor.id == TaskDependencyModel.predecessor_task_id)
            .join(successor, successor.id == TaskDependencyModel.successor_task_id)
            .where(predecessor.user_id == user_id, successor.user_id == user_id)
        )

    def _to_entity(self, model: TaskDependencyModel) -> TaskDependency:
        return TaskDependency(
            predecessor_task_id=model.predecessor_task_id,
            successor_task_id=model.successor_task_id,
            dependency_type=DependencyType(model.dependency_type),
            lag_days=model.lag_days,
            created_at=model.created_at,
        )
