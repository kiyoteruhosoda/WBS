"""Projects (nested. task #187 / ADR-0024).

- ``GET /projects``: all of them (archived too) in tree order (children right after their parent)
- ``POST /projects/{id}/move``: change the parent / reorder among siblings (409 when moving under itself)
- ``DELETE /projects/{id}``: empty ones only (409 if it has contents; archive via ``PUT`` with ``status``). Top-level ones are admins only
- ``/projects/{id}/members``: members of the top-level project (task #544 / ADR-0055). The root's list for an id at any level
- ``GET /projects/people``: people selectable as members/assignees
- ``PUT /projects/{id}/members/{user_id}/capacity``: daily hours and allocation rate (task #554 / ADR-0058)
- ``/projects/{id}/calendar``: the project calendar (the root's working weekdays, holidays of itself and its ancestors) and members' leave (ADR-0059)
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Query, status

from src.application.dto.project_dto import CreateProjectDTO, MoveProjectDTO, UpdateProjectDTO
from src.application.use_cases.project_use_cases import ProjectUseCases
from src.application.use_cases.team_calendar_use_cases import TeamCalendarUseCases
from src.presentation.api.dependencies import (
    CurrentUserDep,
    DbDep,
    ProjectMemberUseCasesDep,
)
from src.presentation.api.schemas.project_schemas import (
    JapaneseHolidaysRequest,
    MemberLeaveRequest,
    PersonResponse,
    ProjectCreateRequest,
    ProjectMemberCapacityRequest,
    ProjectMemberRequest,
    ProjectMemberRoleRequest,
    ProjectMembersResponse,
    ProjectMoveRequest,
    ProjectResponse,
    ProjectUpdateRequest,
    TeamCalendarResponse,
    TeamDayOffRequest,
    TeamWorkdaysRequest,
)

router = APIRouter(prefix="/projects", tags=["projects"])


@router.get("", response_model=list[ProjectResponse])
def list_projects(db: DbDep, current_user: CurrentUserDep) -> list[ProjectResponse]:
    return [ProjectResponse.from_view(v) for v in ProjectUseCases(db).list_projects(current_user.user_id)]


@router.post("", response_model=ProjectResponse, status_code=status.HTTP_201_CREATED)
def create_project(body: ProjectCreateRequest, db: DbDep, current_user: CurrentUserDep) -> ProjectResponse:
    dto = CreateProjectDTO(
        user_id=current_user.user_id,
        name=body.name,
        parent_project_id=body.parent_project_id,
        color=body.color,
        code=body.code,
        description=body.description,
    )
    return ProjectResponse.from_view(ProjectUseCases(db).create_project(dto))


@router.get("/people", response_model=list[PersonResponse])
def list_people(uc: ProjectMemberUseCasesDep, current_user: CurrentUserDep) -> list[PersonResponse]:
    """People selectable as members/assignees (anyone who has logged in to WBS at least once and is not disabled. ADR-0055 decision 5).

    Admins and marked users see everyone; others see only people in the same tree (ADR-0067).
    """
    return [PersonResponse.from_person(p) for p in uc.candidates(current_user.user_id)]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: DbDep, current_user: CurrentUserDep) -> ProjectResponse:
    return ProjectResponse.from_view(ProjectUseCases(db).get_project(project_id, current_user.user_id))


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int, body: ProjectUpdateRequest, db: DbDep, current_user: CurrentUserDep
) -> ProjectResponse:
    fields = body.model_dump(exclude_unset=True)
    # Name and status cannot be emptied (null is read as "unchanged")
    for key in ("name", "status"):
        if fields.get(key) is None:
            fields.pop(key, None)
    dto = UpdateProjectDTO(**fields)
    return ProjectResponse.from_view(
        ProjectUseCases(db).update_project(project_id, current_user.user_id, dto)
    )


@router.post("/{project_id}/move", response_model=ProjectResponse)
def move_project(
    project_id: int, body: ProjectMoveRequest, db: DbDep, current_user: CurrentUserDep
) -> ProjectResponse:
    dto = MoveProjectDTO(parent_project_id=body.parent_project_id, position=body.position)
    return ProjectResponse.from_view(
        ProjectUseCases(db).move_project(project_id, current_user.user_id, dto)
    )


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(project_id: int, db: DbDep, current_user: CurrentUserDep) -> None:
    ProjectUseCases(db).delete_project(project_id, current_user.user_id)


@router.get("/{project_id}/members", response_model=ProjectMembersResponse)
def list_members(
    project_id: int, uc: ProjectMemberUseCasesDep, current_user: CurrentUserDep
) -> ProjectMembersResponse:
    return ProjectMembersResponse.from_view(uc.list_members(current_user.user_id, project_id))


@router.post("/{project_id}/members", response_model=ProjectMembersResponse)
def add_member(
    project_id: int,
    body: ProjectMemberRequest,
    uc: ProjectMemberUseCasesDep,
    current_user: CurrentUserDep,
) -> ProjectMembersResponse:
    """Add (or overwrite the role if already a member). Admins only (403). 422 for someone who has never signed in to WBS."""
    return ProjectMembersResponse.from_view(
        uc.add_member(current_user.user_id, project_id, body.user_id, body.role)
    )


@router.put("/{project_id}/members/{user_id}", response_model=ProjectMembersResponse)
def change_member_role(
    project_id: int,
    user_id: int,
    body: ProjectMemberRoleRequest,
    uc: ProjectMemberUseCasesDep,
    current_user: CurrentUserDep,
) -> ProjectMembersResponse:
    """Change the role. Admins only (403). 409 when demoting the last admin."""
    return ProjectMembersResponse.from_view(
        uc.change_role(current_user.user_id, project_id, user_id, body.role)
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: int, user_id: int, uc: ProjectMemberUseCasesDep, current_user: CurrentUserDep
) -> None:
    """Remove. Admins can remove anyone, members only themselves (leave). 409 for the last admin. Assignments remain."""
    uc.remove_member(current_user.user_id, project_id, user_id)


@router.put("/{project_id}/members/{user_id}/capacity", response_model=ProjectMembersResponse)
def change_member_capacity(
    project_id: int,
    user_id: int,
    body: ProjectMemberCapacityRequest,
    uc: ProjectMemberUseCasesDep,
    current_user: CurrentUserDep,
) -> ProjectMembersResponse:
    """Daily hours and allocation rate. Admins for anyone, members only their own (403 otherwise)."""
    return ProjectMembersResponse.from_view(
        uc.change_capacity(current_user.user_id, project_id, user_id, body.daily_hours, body.engagement_percent)
    )


@router.get("/{project_id}/calendar", response_model=TeamCalendarResponse)
def get_team_calendar(
    project_id: int,
    db: DbDep,
    current_user: CurrentUserDep,
    from_date: Annotated[date | None, Query(alias="from", description="From this date (omit for all)")] = None,
    to_date: Annotated[date | None, Query(alias="to", description="Up to this date (omit for all)")] = None,
) -> TeamCalendarResponse:
    """The root's working weekdays, holidays of this project and its ancestors, and leave of this tree's members (dates and leave ratio only)."""
    view = TeamCalendarUseCases(db).view(current_user.user_id, project_id, from_date, to_date)
    return TeamCalendarResponse.from_view(view)


@router.put("/{project_id}/calendar/workdays", response_model=TeamCalendarResponse)
def set_team_workdays(
    project_id: int, body: TeamWorkdaysRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """Working weekdays (admins only)."""
    view = TeamCalendarUseCases(db).set_workdays(current_user.user_id, project_id, body.workdays)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/calendar/days-off", response_model=TeamCalendarResponse)
def add_team_day_off(
    project_id: int, body: TeamDayOffRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """Add a holiday to this project (overwrites the name on the same date; can also be added to lower projects; admins only)."""
    view = TeamCalendarUseCases(db).add_day_off(current_user.user_id, project_id, body.day, body.name)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/calendar/days-off/japan", response_model=TeamCalendarResponse)
def import_japanese_holidays(
    project_id: int, body: JapaneseHolidaysRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """Add that year's Japanese public holidays to this project's holidays (dates already on itself or an ancestor are left alone; admins only)."""
    view = TeamCalendarUseCases(db).import_japanese_holidays(current_user.user_id, project_id, body.year)
    return TeamCalendarResponse.from_view(view)


@router.delete("/{project_id}/calendar/days-off/{day}", response_model=TeamCalendarResponse)
def remove_team_day_off(
    project_id: int, day: date, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    view = TeamCalendarUseCases(db).remove_day_off(current_user.user_id, project_id, day)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/calendar/extra-workdays", response_model=TeamCalendarResponse)
def add_extra_workday(
    project_id: int, body: TeamDayOffRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """Add a working day (a day worked on a non-working weekday) to this project. Removes a holiday on the same date (admins only. ADR-0060)."""
    view = TeamCalendarUseCases(db).add_extra_workday(current_user.user_id, project_id, body.day, body.name)
    return TeamCalendarResponse.from_view(view)


@router.delete("/{project_id}/calendar/extra-workdays/{day}", response_model=TeamCalendarResponse)
def remove_extra_workday(
    project_id: int, day: date, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    view = TeamCalendarUseCases(db).remove_extra_workday(current_user.user_id, project_id, day)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/members/{user_id}/leave", response_model=TeamCalendarResponse)
def add_member_leave(
    project_id: int, user_id: int, body: MemberLeaveRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """Enter that person's leave, or their working hours for the day (hours: overtime, short days, holiday work) (overwrites the same date.
    The person themself or admins only. Shared across projects)."""
    view = TeamCalendarUseCases(db).add_leave(
        current_user.user_id, project_id, user_id, body.day, body.off_percent, body.hours
    )
    return TeamCalendarResponse.from_view(view)


@router.delete("/{project_id}/members/{user_id}/leave/{day}", response_model=TeamCalendarResponse)
def remove_member_leave(
    project_id: int, user_id: int, day: date, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    view = TeamCalendarUseCases(db).remove_leave(current_user.user_id, project_id, user_id, day)
    return TeamCalendarResponse.from_view(view)
