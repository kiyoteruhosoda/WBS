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

# Color is #rrggbb (same format as categories)
COLOR_PATTERN = r"^#[0-9A-Fa-f]{6}$"


class ProjectCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    parent_project_id: int | None = None
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    # Optional. Leading/trailing whitespace is stripped, empty becomes null (the domain checks the max length)
    code: str | None = None
    description: str | None = None


class ProjectUpdateRequest(BaseModel):
    """Change only the fields sent (null clears). Parent and order are via ``POST /projects/{id}/move``."""

    name: str | None = Field(default=None, min_length=1, max_length=200)
    color: str | None = Field(default=None, pattern=COLOR_PATTERN)
    # Optional. Leading/trailing whitespace is stripped, empty becomes null (the domain checks the max length)
    code: str | None = None
    description: str | None = None
    status: ProjectStatus | None = None


class ProjectMoveRequest(BaseModel):
    """New parent (null = top level) and the position among the new siblings (0 = first; omitted or out of range = last)."""

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
    # active (in progress) / archived
    status: str
    sort_order: int
    # Display path ("parent / child")
    path: str
    # The top-level project that has the members, and the user's role there (manager / member. ADR-0055)
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
    """People selectable as members/assignees (anyone who has logged in to WBS at least once. ADR-0055)."""

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
    """Daily hours and allocation rate (ADR-0058). Time this person can spend on this project per day = daily hours x allocation rate."""

    daily_hours: Decimal = Field(ge=0, le=24, decimal_places=2)
    engagement_percent: int = Field(ge=0, le=100)


class ProjectMemberResponse(BaseModel):
    user_id: int
    display_name: str
    email: str
    role: ProjectRole
    # Whether this is the requesting user
    is_you: bool
    # Daily hours (hours) and allocation rate (%). ADR-0058
    daily_hours: float
    engagement_percent: int


class ProjectMembersResponse(BaseModel):
    # The top-level project that has the members (the same list is returned for an id at any level)
    root_project_id: int
    # Whether the user is an admin (can add/remove members and change roles)
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
    workdays: list[Weekday] = Field(min_length=1, description="Working weekdays (MO-SU)")


class TeamDayOffRequest(BaseModel):
    day: date
    name: str | None = Field(default=None, max_length=100)


class JapaneseHolidaysRequest(BaseModel):
    year: int = Field(ge=1980, le=2099)


class MemberLeaveRequest(BaseModel):
    day: date
    off_percent: int = Field(default=100, ge=1, le=100, description="Leave ratio (100 for a full day, 50 for half)")
    hours: float | None = Field(
        default=None, ge=0, le=24,
        description="Working hours for that day (if set, the leave ratio is ignored; overtime, a short day, or holiday work on a non-working day)",
    )


class TeamDayOffResponse(BaseModel):
    day: date
    name: str | None
    # The project the holiday belongs to
    project_id: int
    # Whether it is inherited from a parent (ancestor) (cannot be deleted from the opened project)
    inherited: bool


class TeamExtraWorkdayResponse(BaseModel):
    day: date
    name: str | None
    project_id: int
    inherited: bool


class MemberLeaveResponse(BaseModel):
    user_id: int
    day: date
    off_percent: int
    # Working hours for that day (if set, off_percent is ignored)
    hours: float | None


class TeamCalendarResponse(BaseModel):
    """The project calendar (working weekdays, holidays) and members' leave (ADR-0058 decision 2, ADR-0059)."""

    # The opened project (where holidays are added)
    project_id: int
    # The top-level project that has the weekdays
    root_project_id: int
    # Whether the user is an admin (can enter weekdays, holidays and anyone's leave; members only their own leave)
    can_manage: bool
    workdays: list[Weekday]
    days_off: list[TeamDayOffResponse]
    # Days worked on non-working weekdays (ADR-0060. Never overlaps a holiday on the same date; the nearest project's wins)
    extra_workdays: list[TeamExtraWorkdayResponse]
    leave: list[MemberLeaveResponse]

    @classmethod
    def from_view(cls, view: TeamCalendarView) -> TeamCalendarResponse:
        return cls(
            project_id=view.project_id,
            root_project_id=view.root_project_id,
            can_manage=view.can_manage,
            workdays=view.workdays,
            days_off=[
                TeamDayOffResponse(
                    day=d.day, name=d.name, project_id=d.project_id, inherited=d.project_id != view.project_id,
                )
                for d in view.days_off
            ],
            extra_workdays=[
                TeamExtraWorkdayResponse(
                    day=d.day, name=d.name, project_id=d.project_id, inherited=d.project_id != view.project_id,
                )
                for d in view.extra_workdays
            ],
            leave=[
                MemberLeaveResponse(user_id=d.user_id, day=d.day, off_percent=d.off_percent, hours=d.hours)
                for d in view.leave
            ],
        )
