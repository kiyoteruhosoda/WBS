from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

from src.shared.clock import utcnow


class Base(DeclarativeBase):
    pass

BigIntPK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")

class UserModel(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    display_name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    timezone: Mapped[str] = mapped_column(sa.String(64), default="Asia/Tokyo", nullable=False)
    language: Mapped[str] = mapped_column(sa.String(8), default="ja", nullable=False)
    is_active: Mapped[bool] = mapped_column(sa.Boolean, default=True, nullable=False)
    #: Whether the user can create top-level projects (ADR-0065)
    can_create_projects: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class CategoryModel(Base):
    __tablename__ = "categories"
    __table_args__ = (sa.UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(100), nullable=False)
    color: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class ProjectModel(Base):
    """Project (task #187 / ADR-0024). ``parent_project_id`` allows nesting to any depth (adjacency list).

    ⚠ **Cycles are rejected by the app** (DB constraints cannot prevent them). Descendants are fetched with a recursive CTE.
    ``status`` is a ``ProjectStatus`` value (active / archived). Not a native ENUM.
    Only empty projects are deleted, and the row is removed (ids are not reused).
    """

    __tablename__ = "projects"
    __table_args__ = (
        sa.Index("ix_projects_user_id_parent_project_id", "user_id", "parent_project_id"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    parent_project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_projects_parent_project_id"),
        nullable=True,
    )
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    color: Mapped[str | None] = mapped_column(sa.String(7), nullable=True)
    # Optional short code (display only. Not unique. Whitespace stripped, empty becomes NULL)
    code: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(16), default="active", nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class ProjectMemberModel(Base):
    """Project members (task #544 / ADR-0055). ⚠ **Rows exist only for top-level projects**.
    Projects, tasks and milestones below are visible to all members of the root.

    ``role`` is a ``ProjectRole`` value (manager / member). Not a native ENUM.
    """

    __tablename__ = "project_members"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "user_id", name="uq_project_members_project_user"),
        sa.Index("ix_project_members_user_id", "user_id"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_project_members_project_id"),
        nullable=False,
    )
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("users.id", name="fk_project_members_user_id"),
        nullable=False,
    )
    role: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    # Daily hours (hours) and allocation rate (%). Used for forecasting (task #554 / ADR-0058)
    daily_hours: Mapped[Decimal] = mapped_column(
        sa.Numeric(4, 2), default=Decimal(8), server_default="8", nullable=False
    )
    engagement_percent: Mapped[int] = mapped_column(
        sa.Integer, default=100, server_default="100", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)

class TeamWorkweekModel(Base):
    """Working weekdays of a top-level project (task #554 / ADR-0058). Mon-Fri if there is no row.

    ``workdays`` is MO-SU comma-separated (same spelling as ``calendars.workdays`` in the leave layer).
    """

    __tablename__ = "team_workweeks"
    __table_args__ = (
        sa.UniqueConstraint("project_id", name="uq_team_workweeks_project"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_team_workweeks_project_id"),
        nullable=False,
    )
    workdays: Mapped[str] = mapped_column(sa.String(32), nullable=False)

class TeamDayOffModel(Base):
    """Project holidays (task #554 / ADR-0058). The root's are team holidays; lower ones are holidays added for that subtree (ADR-0059)."""

    __tablename__ = "team_days_off"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "day", name="uq_team_days_off_project_day"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_team_days_off_project_id"),
        nullable=False,
    )
    day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

class MemberDayOffModel(Base):
    """Each person's leave (per person, shared across projects. Dates and leave ratio only. task #554 / ADR-0058, #557 / ADR-0059)."""

    __tablename__ = "member_days_off"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "day", name="uq_member_days_off_user_day"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("users.id", name="fk_member_days_off_user_id"),
        nullable=False,
    )
    day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    #: Leave ratio (100 for a full day, 50 for half)
    off_percent: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="100", default=100)
    #: Working hours for that day (if set, the leave ratio is ignored. Overtime, short days, holiday work. task #558 / ADR-0060)
    hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(4, 2), nullable=True)


class TeamExtraWorkdayModel(Base):
    """Project working days = days worked on non-working weekdays (task #558 / ADR-0060). Lower projects inherit them."""

    __tablename__ = "team_extra_workdays"
    __table_args__ = (
        sa.UniqueConstraint("project_id", "day", name="uq_team_extra_workdays_project_day"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    project_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_team_extra_workdays_project_id"),
        nullable=False,
    )
    day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(100), nullable=True)

class MilestoneModel(Base):
    __tablename__ = "milestones"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    due_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # The project it belongs to (empty = uncategorized. task #187 / ADR-0024)
    project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_milestones_project_id"),
        nullable=True,
        index=True,
    )

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
    # Manually entered remaining time (empty uses "estimate - actual" as the default. ADR-0010)
    remaining_hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    milestone_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("milestones.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # When it was archived (tasks with time punches or actuals are archived instead of deleted. ADR-0046)
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    # The project it belongs to (empty = uncategorized. task #187 / ADR-0024). ⚠ Child tasks hold the same value as their parent
    # (kept in sync by the app; moving a parent moves its descendants)
    project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_tasks_project_id"),
        nullable=True,
        index=True,
    )
    # Assignee (nullable. task #544 / ADR-0055). Must be a member of the root project (the creator if uncategorized)
    assignee_user_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("users.id", name="fk_tasks_assignee_user_id"),
        nullable=True,
        index=True,
    )
    # Allocation rate (%, nullable. task #554 / ADR-0058). A task with it progresses at this share of the assignee's free daily time
    allocation_percent: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

class WorkLogModel(Base):
    __tablename__ = "work_logs"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=False)
    work_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    hours: Mapped[Decimal] = mapped_column(sa.Numeric(5, 2), nullable=False)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # A WorkLogSource value (manual / closing / tracker). closing marks rows created by WBS's own closing before the move to Tracker (ADR-0012)
    source: Mapped[str] = mapped_column(sa.String(16), default="manual", server_default=sa.text("'manual'"), nullable=False)
    # Exact length (seconds) of rows created by a closing (WBS or Tracker). hours is the value rounded to 2 decimals
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # For rows received from Tracker (source=tracker), the first day of the Tracker closing period (task #540 / ADR-0056).
    # Together with the user it identifies the period (the unit of replacement and cancellation)
    tracker_first_day: Mapped[date | None] = mapped_column(sa.Date, nullable=True)

class TaskDependencyModel(Base):
    __tablename__ = "task_dependencies"
    predecessor_task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), primary_key=True)
    successor_task_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), primary_key=True)
    dependency_type: Mapped[str] = mapped_column(sa.String(2), default="FS", nullable=False)
    lag_days: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)

class InboxItemModel(Base):
    __tablename__ = "inbox_items"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    converted_task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    converted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

# ── SSO (OIDC) ─────────────────────────────────────────────────────────────
class FederatedIdentityModel(Base):
    """Mapping between an identity on the IdP (iss + sub) and a user.

    Email is not used to match users, because an address change on the IdP side
    (name change, department transfer) would turn them into a different person. Users are
    one-to-many with this so one person can belong to several IdPs.
    """

    __tablename__ = "federated_identities"
    __table_args__ = (sa.UniqueConstraint("issuer", "subject", name="uq_federated_identity"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)

class RefreshSessionModel(Base):
    """A record per login (ADR-0069, ADR-0071). No row means that login has ended.

    ⚠ The table name is still the one from ADR-0069. Refresh tokens are no longer issued (ADR-0071).
    """

    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    # The IdP-side login that started this login (the ID token's ``sid``).
    # ⚠ Nullable, as some IdPs do not send it. For such IdPs sessions can be stopped **only per user**.
    idp_session_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)


class BackchannelLogoutDeliveryModel(Base):
    """Received deactivation notices (kept only to reject resends).

    ⚠ **No content is kept.** Who was stopped shows in the session rows being gone. All that
    is kept is "this ``jti`` has already been applied", and it is cleaned up after a while.
    """

    __tablename__ = "auth_backchannel_logout_deliveries"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)

class LoginTransactionModel(Base):
    """Temporary data for one authorization code flow round trip (state / nonce / PKCE)."""

    __tablename__ = "auth_login_transactions"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(sa.String(128), unique=True, nullable=False)
    nonce: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    redirect_path: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)
    #: Whether this is a silent check round trip (``prompt=none``. ADR-0062)
    silent: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )
    #: What the round trip is for (``login`` / ``renew``. ADR-0071). ⚠ Not a native ENUM
    purpose: Mapped[str] = mapped_column(sa.String(16), nullable=False, default="login", server_default="login")
    #: For a continuation round trip, the user and record of the login being continued (ADR-0071). No foreign keys (round trips vanish after 10 minutes)
    continued_user_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), nullable=True)
    continued_session_id: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)



class MachineOperationLogModel(Base):
    """Record of operations written by machines (which app, on whose behalf, what. task #802 / ADR-0068). Read-only endpoints are not recorded.

    It is inserted in the same transaction as the written content, so "written but not recorded" cannot happen. Refused operations go to the app log only.
    """

    __tablename__ = "machine_operation_logs"
    __table_args__ = (
        sa.Index("ix_machine_operation_logs_occurred_at", "occurred_at"),
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    occurred_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    client_id: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    operation: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    detail: Mapped[str | None] = mapped_column(sa.String(255), nullable=True)
