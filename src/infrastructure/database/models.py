from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass

BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(sa.String(64), default="Asia/Tokyo", nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class CategoryModel(Base):
    __tablename__ = "categories"
    __table_args__ = (sa.UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class MilestoneModel(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class TaskModel(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    category_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("categories.id"), nullable=True)
    priority: Mapped[int] = mapped_column(sa.SmallInteger, default=3, nullable=False)
    urgency: Mapped[int] = mapped_column(sa.SmallInteger, default=3, nullable=False)
    status: Mapped[str] = mapped_column(sa.String(20), default="TODO", nullable=False)
    start_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    estimated_hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    remaining_hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    milestone_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("milestones.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class WorkLogModel(Base):
    __tablename__ = "work_logs"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class TaskDependencyModel(Base):
    __tablename__ = "task_dependencies"
    predecessor_task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), primary_key=True)
    successor_task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), primary_key=True)
    dependency_type: Mapped[str] = mapped_column(sa.String(2), default="FS", nullable=False)
    lag_days: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)

class InboxItemModel(Base):
    __tablename__ = "inbox_items"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    converted_task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)
