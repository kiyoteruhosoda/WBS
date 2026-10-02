from __future__ import annotations

from sqlalchemy import exists, or_, select, update
from sqlalchemy.orm import Session

from src.domain.entities.project import Project
from src.domain.repositories.project_repository import ProjectRepository
from src.domain.value_objects.project_status import ProjectStatus
from src.infrastructure.database.models import MilestoneModel, ProjectModel, TaskModel
from src.shared.clock import utcnow


class SqlAlchemyProjectRepository(ProjectRepository):
    def __init__(self, session: Session) -> None:
        self._session = session

    def find_by_id(self, project_id: int) -> Project | None:
        model = self._session.get(ProjectModel, project_id)
        return self._to_entity(model) if model is not None else None

    def find_all(self, user_id: int) -> list[Project]:
        stmt = (
            select(ProjectModel)
            .where(ProjectModel.user_id == user_id)
            .order_by(ProjectModel.sort_order, ProjectModel.id)
        )
        return [self._to_entity(m) for m in self._session.scalars(stmt)]

    def subtree_ids(self, user_id: int, project_id: int) -> list[int]:
        # ⚠ 行ごとに子を引かない（多段なので深くなるほど N+1 が効く）。UNION（重複を落とす）なので、
        #   万一の環でも止まる。持ち主は根でも子でも確かめる（他人の行へ辿らない）
        base = (
            select(ProjectModel.id)
            .where(ProjectModel.id == project_id, ProjectModel.user_id == user_id)
            .cte("project_subtree", recursive=True)
        )
        child = select(ProjectModel.id).join(base, ProjectModel.parent_project_id == base.c.id).where(
            ProjectModel.user_id == user_id
        )
        tree = base.union(child)
        return [int(i) for i in self._session.scalars(select(tree.c.id))]

    def save(self, project: Project) -> Project:
        if project.id is None:
            model = ProjectModel(
                user_id=project.user_id,
                parent_project_id=project.parent_project_id,
                name=project.name,
                color=project.color,
                code=project.code,
                description=project.description,
                status=project.status.value,
                sort_order=project.sort_order,
            )
            self._session.add(model)
            self._session.flush()
            return self._to_entity(model)
        model = self._session.get(ProjectModel, project.id)
        if model is None:
            raise ValueError(f"Project {project.id} not found")
        model.parent_project_id = project.parent_project_id
        model.name = project.name
        model.color = project.color
        model.code = project.code
        model.description = project.description
        model.status = project.status.value
        model.sort_order = project.sort_order
        model.updated_at = utcnow()
        self._session.flush()
        return self._to_entity(model)

    def set_sort_orders(self, ordered_ids: list[int]) -> None:
        for order, project_id in enumerate(ordered_ids):
            self._session.execute(
                update(ProjectModel).where(ProjectModel.id == project_id).values(sort_order=order)
            )
        self._session.flush()

    def delete(self, project_id: int) -> None:
        # 消したタスク・マイルストーンが指したままだと外部キーが残るので、先に外す
        self._session.execute(
            update(TaskModel).where(TaskModel.project_id == project_id).values(project_id=None)
        )
        self._session.execute(
            update(MilestoneModel)
            .where(MilestoneModel.project_id == project_id)
            .values(project_id=None)
        )
        model = self._session.get(ProjectModel, project_id)
        if model is not None:
            self._session.delete(model)
        self._session.flush()

    def has_contents(self, project_id: int) -> bool:
        child = exists().where(ProjectModel.parent_project_id == project_id)
        task = exists().where(TaskModel.project_id == project_id, TaskModel.deleted_at.is_(None))
        milestone = exists().where(
            MilestoneModel.project_id == project_id, MilestoneModel.deleted_at.is_(None)
        )
        return bool(self._session.scalar(select(or_(child, task, milestone))))

    def _to_entity(self, model: ProjectModel) -> Project:
        return Project(
            id=model.id,
            user_id=model.user_id,
            name=model.name,
            parent_project_id=model.parent_project_id,
            color=model.color,
            code=model.code,
            description=model.description,
            status=ProjectStatus(model.status),
            sort_order=model.sort_order,
            created_at=model.created_at,
            updated_at=model.updated_at,
        )
