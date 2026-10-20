from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, Field

from src.application.ports.person_directory import Person
from src.application.use_cases.project_member_use_cases import ProjectMembersView
from src.application.use_cases.project_use_cases import ProjectView
from src.application.use_cases.team_calendar_use_cases import TeamCalendarView
from src.domain.value_objects.project_role import ProjectRole
from src.domain.value_objects.project_status import ProjectStatus
from src.domain.value_objects.recurrence import Weekday
from src.presentation.api.schemas.types import UtcDatetime

# 色は #rrggbb（カテゴリと同じ形）
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_project_id: int | None = None
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    # 任意。前後の空白を落とし、空は null（長さの上限はドメインで見る）
    code: str | None = None
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    """送った欄だけ変える（null は空へ戻す）。親と並びは ``POST /projects/{id}/move``。"""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    # 任意。前後の空白を落とし、空は null（長さの上限はドメインで見る）
    code: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectMoveRequest(BaseModel):
    """新しい親（null = 最上位）と、新しい兄弟の中の位置（0 = 先頭。省く・範囲外は末尾）。"""

    parent_project_id: int | None = None
    position: int | None = Field(default=None, ge=0)


class ProjectResponse(BaseModel):
    id: int
    user_id: int
    name: str
    parent_project_id: int | None = None
    color: str | None = None
    code: str | None = None
    description: str | None = None
    # active（進行中）/ archived（保管）
    status: str
    sort_order: int
    # 表示用の道筋（「親 / 子」）
    path: str
    # メンバーが付いているいちばん上のプロジェクトと、そこでの自分の役割（manager / member。ADR-0055）
    root_project_id: int
    my_role: ProjectRole | None = None
    created_at: UtcDatetime | None = None
    updated_at: UtcDatetime | None = None

    @classmethod
    def from_view(cls, view: ProjectView) -> ProjectResponse:
        p = view.project
        return cls(
            id=p.id or 0,
            user_id=p.user_id,
            name=p.name,
            parent_project_id=p.parent_project_id,
            color=p.color,
            code=p.code,
            description=p.description,
            status=p.status.value,
            sort_order=p.sort_order,
            path=view.path,
            root_project_id=view.root_project_id,
            my_role=view.my_role,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class PersonResponse(BaseModel):
    """メンバー・担当者に選べる人（WBS に 1 度でもログインした人。ADR-0055）。"""

    id: int
    display_name: str
    email: str

    @classmethod
    def from_person(cls, person: Person) -> PersonResponse:
        return cls(id=person.id, display_name=person.display_name, email=person.email)


class ProjectMemberRequest(BaseModel):
    user_id: int
    role: ProjectRole = ProjectRole.MEMBER


class ProjectMemberRoleRequest(BaseModel):
    role: ProjectRole


class ProjectMemberCapacityRequest(BaseModel):
    """1 日の工数と従事率（ADR-0058）。この人がこのプロジェクトに 1 日に使える時間 = 1 日の工数 × 従事率。"""

    daily_hours: Decimal = Field(ge=0, le=24, decimal_places=2)
    engagement_percent: int = Field(ge=0, le=100)


class ProjectMemberResponse(BaseModel):
    user_id: int
    display_name: str
    email: str
    role: ProjectRole
    # 聞いた本人か
    is_you: bool
    # 1 日の工数（時間）と従事率（%）。ADR-0058
    daily_hours: float
    engagement_percent: int


class ProjectMembersResponse(BaseModel):
    # メンバーが付いているいちばん上のプロジェクト（どの段の id で聞いてもここの名簿が返る）
    root_project_id: int
    # 自分が管理者か（メンバーの出し入れ・役割の変更ができるか）
    can_manage: bool
    members: list[ProjectMemberResponse]

    @classmethod
    def from_view(cls, view: ProjectMembersView) -> ProjectMembersResponse:
        return cls(
            root_project_id=view.root_project_id,
            can_manage=view.can_manage,
            members=[
                ProjectMemberResponse(
                    user_id=m.user_id,
                    display_name=m.display_name,
                    email=m.email,
                    role=m.role,
                    is_you=m.is_you,
                    daily_hours=float(m.daily_hours),
                    engagement_percent=m.engagement_percent,
                )
                for m in view.members
            ],
        )


class TeamWorkdaysRequest(BaseModel):
    workdays: list[Weekday] = Field(min_length=1, description="稼働する曜日（MO〜SU）")


class TeamDayOffRequest(BaseModel):
    day: date
    name: str | None = Field(default=None, max_length=100)


class JapaneseHolidaysRequest(BaseModel):
    year: int = Field(ge=1980, le=2099)


class MemberLeaveRequest(BaseModel):
    day: date


class TeamDayOffResponse(BaseModel):
    day: date
    name: str | None


class MemberLeaveResponse(BaseModel):
    user_id: int
    day: date


class TeamCalendarResponse(BaseModel):
    """チームの稼働する曜日・休日と、メンバーの休み（ADR-0058 決定 2）。"""

    # 曜日と休日が付いているいちばん上のプロジェクト
    root_project_id: int
    # 自分が管理者か（チームの休日と、だれの休みでも入れられる。メンバーは自分の休みだけ）
    can_manage: bool
    workdays: list[Weekday]
    days_off: list[TeamDayOffResponse]
    leave: list[MemberLeaveResponse]

    @classmethod
    def from_view(cls, view: TeamCalendarView) -> TeamCalendarResponse:
        return cls(
            root_project_id=view.root_project_id,
            can_manage=view.can_manage,
            workdays=view.workdays,
            days_off=[TeamDayOffResponse(day=d.day, name=d.name) for d in view.days_off],
            leave=[MemberLeaveResponse(user_id=d.user_id, day=d.day) for d in view.leave],
        )
