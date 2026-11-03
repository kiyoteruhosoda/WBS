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
    #: いちばん上のプロジェクトを作れるか（ADR-0065）
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
    """プロジェクト（task #187 / ADR-0024）。``parent_project_id`` で何段でも入れ子にできる（隣接リスト）。

    ⚠ **環はアプリ側で断る**（DB の制約では守れない）。子孫は再帰 CTE で引く。
    ``status`` は ``ProjectStatus`` の値（active / archived）。ネイティブ ENUM にしない。
    消すのは空のプロジェクトだけで、行ごと消す（id は使い回さない）。
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
    # 任意の短いコード（表示だけ。一意ではない。前後の空白を落とし、空は NULL）
    code: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    status: Mapped[str] = mapped_column(sa.String(16), default="active", nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)

class ProjectMemberModel(Base):
    """プロジェクトのメンバー（task #544 / ADR-0055）。⚠ **行はいちばん上のプロジェクトにだけ置く**。
    その下のプロジェクト・タスク・マイルストーンは、根のメンバー全員に見える。

    ``role`` は ``ProjectRole`` の値（manager / member）。ネイティブ ENUM にしない。
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
    # 1 日の工数（時間）と従事率（%）。見込みの計算に使う（task #554 / ADR-0058）
    daily_hours: Mapped[Decimal] = mapped_column(
        sa.Numeric(4, 2), default=Decimal(8), server_default="8", nullable=False
    )
    engagement_percent: Mapped[int] = mapped_column(
        sa.Integer, default=100, server_default="100", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)

class TeamWorkweekModel(Base):
    """いちばん上のプロジェクトの稼働する曜日（task #554 / ADR-0058）。行が無ければ月〜金。

    ``workdays`` は MO〜SU をカンマで（休みの層の ``calendars.workdays`` と同じ綴り）。
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
    """プロジェクトの休日（task #554 / ADR-0058）。根のものはチームの休日、下のものはその木で足した休日（ADR-0059）。"""

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
    """各人の休み（人ごと・プロジェクトをまたいで同じ。日付と休む割合だけ。task #554 / ADR-0058・#557 / ADR-0059）。"""

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
    #: 休む割合（終日 100・半休 50）
    off_percent: Mapped[int] = mapped_column(sa.Integer, nullable=False, server_default="100", default=100)
    #: その日の稼働時間（入っていれば休む割合は見ない。残業・短い日・休日出勤。task #558 / ADR-0060）
    hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(4, 2), nullable=True)


class TeamExtraWorkdayModel(Base):
    """プロジェクトの稼働日＝稼働しない曜日に働く日（task #558 / ADR-0060）。下のプロジェクトは引き継ぐ。"""

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
    # 属するプロジェクト（空 = 未分類。task #187 / ADR-0024）
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
    # 手で入れた残（空なら「見積 − 実績」を既定に使う。ADR-0010）
    remaining_hours: Mapped[Decimal | None] = mapped_column(sa.Numeric(6, 2), nullable=True)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    parent_task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    milestone_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("milestones.id"), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    # アーカイブした時刻（打刻や実績のあるタスクは消さずにアーカイブする。ADR-0046）
    archived_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    # 属するプロジェクト（空 = 未分類。task #187 / ADR-0024）。⚠ 子タスクは親と同じ値を持つ
    # （アプリ側で揃える。親を移すと子孫も移る）
    project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_tasks_project_id"),
        nullable=True,
        index=True,
    )
    # 担当者（空可。task #544 / ADR-0055）。付けられるのは根のプロジェクトのメンバー（未分類なら作った人）
    assignee_user_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("users.id", name="fk_tasks_assignee_user_id"),
        nullable=True,
        index=True,
    )
    # アサイン比率（%、空可。task #554 / ADR-0058）。入れたタスクは担当者の 1 日の空きのうちこの割合で進む
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
    # WorkLogSource の値（manual / closing / tracker）。closing は Tracker へ移す前に WBS の締めで作った行（ADR-0012）
    source: Mapped[str] = mapped_column(sa.String(16), default="manual", server_default=sa.text("'manual'"), nullable=False)
    # 締め（WBS の締め・Tracker の締め）で作った行の正確な長さ（秒）。hours は小数 2 桁に収めた値
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    # Tracker から受け取った行（source=tracker）の、Tracker の締めの期間の初日（task #540 / ADR-0056）。
    # 利用者と組で期間を指す（置き換え・取り消しの単位）
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

# ── SSO（OIDC）─────────────────────────────────────────────────────────────
class FederatedIdentityModel(Base):
    """IdP 上の本人（iss + sub）と利用者の対応。

    利用者の突き合わせにメールを使わないのは、IdP 側で改姓・部署異動に伴う
    アドレス変更があると別人になってしまうため。1 人が複数 IdP に属せるよう
    users とは 1 対多にしている。
    """

    __tablename__ = "federated_identities"
    __table_args__ = (sa.UniqueConstraint("issuer", "subject", name="uq_federated_identity"),)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    issuer: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    subject: Mapped[str] = mapped_column(sa.String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)

class RefreshSessionModel(Base):
    """ログインごとの控え（ADR-0069）。行が無ければそのログインは終わっている。"""

    __tablename__ = "refresh_sessions"
    id: Mapped[str] = mapped_column(sa.String(32), primary_key=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    # リフレッシュトークンの ``jti``。トークンそのものは持たない（DB が漏れてもログインを再現できない）
    current_jti: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    previous_jti: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    rotated_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    # このログインを始めた IdP 側のログイン（ID トークンの ``sid``）。
    # ⚠ 出さない IdP があるので NULL 可。その IdP では**利用者単位でしか**止められない。
    idp_session_id: Mapped[str | None] = mapped_column(sa.String(255), nullable=True, index=True)


class BackchannelLogoutDeliveryModel(Base):
    """受け取った停止の通知（再送を弾くためだけの記録）。

    ⚠ **中身は持たない。** 誰を止めたかはセッションの行が消えたことで表れる。ここに
    残すのは「この ``jti`` はもう効かせた」という 1 点だけで、一定時間で片付ける。
    """

    __tablename__ = "auth_backchannel_logout_deliveries"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(sa.String(255), unique=True, nullable=False)
    received_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)

class LoginTransactionModel(Base):
    """認可コードフロー 1 往復ぶんの一時データ（state / nonce / PKCE）。"""

    __tablename__ = "auth_login_transactions"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    state: Mapped[str] = mapped_column(sa.String(128), unique=True, nullable=False)
    nonce: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    code_verifier: Mapped[str] = mapped_column(sa.String(128), nullable=False)
    redirect_path: Mapped[str] = mapped_column(sa.String(512), nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)
    #: 黙って確かめる往復か（``prompt=none``。ADR-0062）
    silent: Mapped[bool] = mapped_column(
        sa.Boolean, nullable=False, default=False, server_default=sa.false()
    )



class MachineOperationLogModel(Base):
    """機械が書いた操作の記録（どのアプリが・誰の分を・何を。task #802 / ADR-0068）。読むだけの口は残さない。

    書いた内容と同じトランザクションで入れるので、「書けたのに記録が無い」は起きない。断った操作はアプリログまで。
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
