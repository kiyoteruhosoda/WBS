from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal

import sqlalchemy as sa
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

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
    # 属するプロジェクト（空 = 未分類。task #187 / ADR-0024）。⚠ 子タスクは親と同じ値を持つ
    # （アプリ側で揃える。親を移すと子孫も移る）
    project_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("projects.id", name="fk_tasks_project_id"),
        nullable=True,
        index=True,
    )

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
    # WorkLogSource の値（manual / closing）。締めで作った行は開け直しで消える（ADR-0012）
    source: Mapped[str] = mapped_column(sa.String(16), default="manual", server_default=sa.text("'manual'"), nullable=False)
    closing_period_id: Mapped[int | None] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("closing_periods.id", name="fk_work_logs_closing_period_id"),
        nullable=True,
        index=True,
    )
    # 締めで作った行の正確な長さ（秒）。hours は小数 2 桁に収めた値
    duration_seconds: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)

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

class AuthSessionModel(Base):
    """ログイン中のセッション。生のトークンは持たずハッシュだけを置く。"""

    __tablename__ = "auth_sessions"
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(sa.String(64), unique=True, nullable=False)
    issued_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False, index=True)
    last_seen_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    # このセッションを始めた IdP 側のログイン（ID トークンの ``sid``）。
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

class TimeEntryModel(Base):
    """打刻（下書き。締めで確定したものが ``work_logs`` になる。ADR-0008）。

    ⚠ **走っている打刻（``ended_at`` が空）は 1 人 1 本**を、部分一意索引
    ``uq_time_entries_running_per_user`` で DB でも守る（同時に 2 回 Start が来ても
    2 本目は IntegrityError になる）。
    """

    __tablename__ = "time_entries"
    __table_args__ = (
        sa.Index(
            "uq_time_entries_running_per_user",
            "user_id",
            unique=True,
            sqlite_where=sa.text("ended_at IS NULL"),
            postgresql_where=sa.text("ended_at IS NULL"),
        ),
        sa.Index("ix_time_entries_user_id_started_at", "user_id", "started_at"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True)
    started_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    ended_at: Mapped[datetime | None] = mapped_column(sa.DateTime, nullable=True)
    memo: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    # TimeEntrySource の値（timer / manual / split）。ネイティブ ENUM にしない
    source: Mapped[str] = mapped_column(sa.String(16), default="timer", nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, default=utcnow, onupdate=utcnow, nullable=False)


class ClosingPeriodModel(Base):
    """確定した締めの期間（行がある = 確定済み。task #161 / ADR-0012）。

    ``first_day`` / ``last_day`` は利用者のタイムゾーンの日付（1〜15 日 / 16 日〜末日）、
    ``starts_at`` / ``ends_at`` は確定したときのタイムゾーン（``time_zone``）で出した区切りの瞬間
    （naive な UTC の半開区間）。打刻を書き換えさせない判定はこの瞬間で行う。
    """

    __tablename__ = "closing_periods"
    __table_args__ = (
        sa.UniqueConstraint("user_id", "first_day", name="uq_closing_periods_user_first_day"),
        # 開け直すと行を消す。消した id を使い回さない
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    first_day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    last_day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    time_zone: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    starts_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    closed_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)


# ── 予定のカレンダー（task #191、ADR-0027）────────────────────────────────
class CalendarModel(Base):
    """予定のカレンダー。利用者ごとに複数。``is_default`` の 1 つは消せない（移行 0009 で作る）。

    ``kind`` は ``CalendarKind`` の値（いまは EVENTS だけ）。``color_key`` は予定と同じ色の名前。
    ``is_visible`` はカレンダーの画面に出すか（サーバーに覚える。端末をまたいで同じ）。
    """

    __tablename__ = "calendars"
    __table_args__ = ({"sqlite_autoincrement": True},)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    color_key: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    is_default: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    is_visible: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    # 休みの層（ADR-0029）。workdays は営業日の層の曜日（MO〜SU をカンマで）、day_off_reason は
    # 休みの日の一覧の層の理由（NATIONAL_HOLIDAY / COMPANY / PERSONAL）。ほかの種類は NULL。
    workdays: Mapped[str | None] = mapped_column(sa.String(32), nullable=True)
    day_off_reason: Mapped[str | None] = mapped_column(sa.String(16), nullable=True)
    counts_as_day_off: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())


class CalendarDayOffModel(Base):
    """休みの日の一覧の層の 1 日（ADR-0029）。カレンダーを消すと一緒に消える。"""

    __tablename__ = "calendar_days_off"
    __table_args__ = (
        sa.UniqueConstraint("calendar_id", "day", name="uq_calendar_days_off_day"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("calendars.id", ondelete="CASCADE"), nullable=False)
    day: Mapped[date] = mapped_column(sa.Date, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)


class CalendarViewPresetModel(Base):
    """表示の組み合わせ。``calendar_ids`` は表示にするカレンダーの id の JSON の配列。"""

    __tablename__ = "calendar_view_presets"
    __table_args__ = ({"sqlite_autoincrement": True},)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    calendar_ids: Mapped[str] = mapped_column(sa.Text, nullable=False)
    sort_order: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)


# ── 予定（task #156、ADR-0009）──────────────────────────────────────────────
class CalendarEventModel(Base):
    """予定（集約 ``CalendarEvent``）。単発も繰り返しもこの 1 表。

    ``start_utc`` は単発の開始、繰り返しの先頭の回（アンカー）の UTC の瞬間（naive）。
    繰り返しの規則は値オブジェクトなので JSON の文字列で持つ（``recurrence_rule``）。
    ``span_start_day`` / ``span_end_day`` は ``CalendarEvent.indexed_day_span()``
    （``date.toordinal()``）で、期間で粗く絞るための索引付きの列。
    ``version`` は楽観ロック（リポジトリが「読んだ版なら書き換える」UPDATE で確かめる）。
    """

    __tablename__ = "calendar_events"
    __table_args__ = (
        sa.Index("ix_calendar_events_user_span", "user_id", "span_start_day", "span_end_day"),
        # 消した予定の id を使い回さない（古い画面が、同じ id の別の予定を直してしまわないように）
        {"sqlite_autoincrement": True},
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False)
    kind: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    title: Mapped[str] = mapped_column(sa.String(500), nullable=False)
    time_zone: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    start_utc: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    recurrence_rule: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    location: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    description: Mapped[str | None] = mapped_column(sa.Text, nullable=True)
    color_key: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    task_id: Mapped[int | None] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("tasks.id"), nullable=True, index=True)
    span_start_day: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    span_end_day: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    version: Mapped[int] = mapped_column(sa.Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    # 通知（ADR-0021）。alarm_enabled が NULL = 通知を持たない（このとき 4 つの列は false）。
    alarm_enabled: Mapped[bool | None] = mapped_column(sa.Boolean, nullable=True)
    alarm_15_min: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    alarm_5_min: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    alarm_1_min: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    alarm_at_start: Mapped[bool] = mapped_column(sa.Boolean, nullable=False, server_default=sa.false())
    # 分類（ADR-0025）。EVENT = 予定 / TASK = タスク（回ごとに済みを付ける）。ネイティブ ENUM にしない。
    event_type: Mapped[str] = mapped_column(sa.String(16), nullable=False, server_default="EVENT")
    # 属するカレンダー（ADR-0027）。既存の予定は移行 0009 で利用者の既定のカレンダーへ入れた。
    calendar_id: Mapped[int] = mapped_column(
        sa.BigInteger().with_variant(sa.Integer(), "sqlite"),
        sa.ForeignKey("calendars.id", name="fk_calendar_events_calendar_id"),
        nullable=False,
        index=True,
    )

    exceptions: Mapped[list[CalendarEventExceptionModel]] = relationship(
        cascade="all, delete-orphan", order_by="CalendarEventExceptionModel.id", lazy="selectin"
    )
    moves: Mapped[list[CalendarEventMoveModel]] = relationship(
        cascade="all, delete-orphan", order_by="CalendarEventMoveModel.id", lazy="selectin"
    )


class CalendarEventExceptionModel(Base):
    """繰り返しの 1 回への例外（飛ばす・古いデータの上書き）。回は（候補日, 系列の開始時刻）で指す。"""

    __tablename__ = "calendar_event_exceptions"
    __table_args__ = (
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_exceptions_occurrence",
        ),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False)
    occurrence_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    occurrence_time: Mapped[time | None] = mapped_column(sa.Time, nullable=True)
    type: Mapped[str] = mapped_column(sa.String(16), nullable=False)
    override_title: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    override_location: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    override_start_time: Mapped[time | None] = mapped_column(sa.Time, nullable=True)
    override_duration_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)


class CalendarEventMoveModel(Base):
    """繰り返しの 1 回を移した先（予定のタイムゾーンの壁時計）。"""

    __tablename__ = "calendar_event_moves"
    __table_args__ = (
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_moves_occurrence",
        ),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False)
    occurrence_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    occurrence_time: Mapped[time | None] = mapped_column(sa.Time, nullable=True)
    new_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    new_start_time: Mapped[time | None] = mapped_column(sa.Time, nullable=True)
    new_duration_minutes: Mapped[int | None] = mapped_column(sa.Integer, nullable=True)
    title: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)
    location: Mapped[str | None] = mapped_column(sa.String(500), nullable=True)


class CalendarEventCompletionModel(Base):
    """タスクの分類の予定の回の「済み」（ADR-0025）。行がある = 済み。

    回は（候補日, 系列の開始時刻）で指す（例外・移動と同じ鍵）。単発は両方 NULL。
    予定の集約の外に置く（済みを付けても予定の版を進めない）。
    """

    __tablename__ = "calendar_event_completions"
    __table_args__ = (
        sa.UniqueConstraint(
            "event_id", "occurrence_date", "occurrence_time",
            name="uq_calendar_event_completions_occurrence",
        ),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    event_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("calendar_events.id", ondelete="CASCADE"), nullable=False)
    occurrence_date: Mapped[date | None] = mapped_column(sa.Date, nullable=True)
    occurrence_time: Mapped[time | None] = mapped_column(sa.Time, nullable=True)
    completed_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)


class BusinessCalendarModel(Base):
    """営業日カレンダー。``workdays`` は曜日の略号（``MO``〜``SU``）をカンマでつないだもの。"""

    __tablename__ = "business_calendars"
    __table_args__ = ({"sqlite_autoincrement": True},)
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("users.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(sa.String(200), nullable=False)
    time_zone: Mapped[str] = mapped_column(sa.String(64), nullable=False)
    workdays: Mapped[str] = mapped_column(sa.String(32), nullable=False)
    shift_on_holidays_only: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    is_enabled: Mapped[bool] = mapped_column(sa.Boolean, nullable=False)
    created_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(sa.DateTime, nullable=False)

    holidays: Mapped[list[BusinessCalendarHolidayModel]] = relationship(
        cascade="all, delete-orphan", order_by="BusinessCalendarHolidayModel.holiday_date", lazy="selectin"
    )


class BusinessCalendarHolidayModel(Base):
    __tablename__ = "business_calendar_holidays"
    __table_args__ = (
        sa.UniqueConstraint("calendar_id", "holiday_date", name="uq_business_calendar_holidays_date"),
    )
    id: Mapped[int] = mapped_column(BigIntPK, primary_key=True, autoincrement=True)
    calendar_id: Mapped[int] = mapped_column(sa.BigInteger().with_variant(sa.Integer(), "sqlite"), sa.ForeignKey("business_calendars.id", ondelete="CASCADE"), nullable=False)
    holiday_date: Mapped[date] = mapped_column(sa.Date, nullable=False)
    name: Mapped[str | None] = mapped_column(sa.String(200), nullable=True)
