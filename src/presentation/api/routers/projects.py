"""プロジェクト（入れ子。task #187 / ADR-0024）。

- ``GET /projects``: 全部（保管したものも）を木の順（親の直後に子）で
- ``POST /projects/{id}/move``: 親を替える・兄弟の中で並べ替える（自分の下へは 409）
- ``DELETE /projects/{id}``: 空のものだけ（中身があれば 409。保管は ``PUT`` で ``status``）。いちばん上は管理者だけ
- ``/projects/{id}/members``: いちばん上のプロジェクトのメンバー（task #544 / ADR-0055）。どの段の id でも根の名簿
- ``GET /projects/people``: メンバー・担当者に選べる人
- ``PUT /projects/{id}/members/{user_id}/capacity``: 1 日の工数と従事率（task #554 / ADR-0058）
- ``/projects/{id}/calendar``: プロジェクトのカレンダー（根の稼働する曜日・自分と先祖の休日）と、メンバーの休み（ADR-0059）
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
    """メンバー・担当者に選べる人（WBS に 1 度でもログインし、止まっていない人。ADR-0055 決定 5）。"""
    return [PersonResponse.from_person(p) for p in uc.candidates()]


@router.get("/{project_id}", response_model=ProjectResponse)
def get_project(project_id: int, db: DbDep, current_user: CurrentUserDep) -> ProjectResponse:
    return ProjectResponse.from_view(ProjectUseCases(db).get_project(project_id, current_user.user_id))


@router.put("/{project_id}", response_model=ProjectResponse)
def update_project(
    project_id: int, body: ProjectUpdateRequest, db: DbDep, current_user: CurrentUserDep
) -> ProjectResponse:
    fields = body.model_dump(exclude_unset=True)
    # 名前と状態は空にできない（null は「変えない」と読む）
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
    """加える（もう居れば役割を書き換える）。管理者だけ（403）。WBS に入ったことのない人は 422。"""
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
    """役割を変える。管理者だけ（403）。最後の管理者を下げると 409。"""
    return ProjectMembersResponse.from_view(
        uc.change_role(current_user.user_id, project_id, user_id, body.role)
    )


@router.delete("/{project_id}/members/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_member(
    project_id: int, user_id: int, uc: ProjectMemberUseCasesDep, current_user: CurrentUserDep
) -> None:
    """外す。管理者は誰でも、メンバーは自分だけ（抜ける）。最後の管理者は 409。担当は残る。"""
    uc.remove_member(current_user.user_id, project_id, user_id)


@router.put("/{project_id}/members/{user_id}/capacity", response_model=ProjectMembersResponse)
def change_member_capacity(
    project_id: int,
    user_id: int,
    body: ProjectMemberCapacityRequest,
    uc: ProjectMemberUseCasesDep,
    current_user: CurrentUserDep,
) -> ProjectMembersResponse:
    """1 日の工数と従事率。管理者は誰のでも、メンバーは自分のだけ（ほかは 403）。"""
    return ProjectMembersResponse.from_view(
        uc.change_capacity(current_user.user_id, project_id, user_id, body.daily_hours, body.engagement_percent)
    )


@router.get("/{project_id}/calendar", response_model=TeamCalendarResponse)
def get_team_calendar(
    project_id: int,
    db: DbDep,
    current_user: CurrentUserDep,
    from_date: Annotated[date | None, Query(alias="from", description="この日から（省くと全部）")] = None,
    to_date: Annotated[date | None, Query(alias="to", description="この日まで（省くと全部）")] = None,
) -> TeamCalendarResponse:
    """根の稼働する曜日、このプロジェクトと先祖の休日、この木のメンバーの休み（日付と休む割合だけ）。"""
    view = TeamCalendarUseCases(db).view(current_user.user_id, project_id, from_date, to_date)
    return TeamCalendarResponse.from_view(view)


@router.put("/{project_id}/calendar/workdays", response_model=TeamCalendarResponse)
def set_team_workdays(
    project_id: int, body: TeamWorkdaysRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """稼働する曜日（管理者だけ）。"""
    view = TeamCalendarUseCases(db).set_workdays(current_user.user_id, project_id, body.workdays)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/calendar/days-off", response_model=TeamCalendarResponse)
def add_team_day_off(
    project_id: int, body: TeamDayOffRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """このプロジェクトに休日を足す（同じ日なら名前を書き換える。下のプロジェクトにも足せる。管理者だけ）。"""
    view = TeamCalendarUseCases(db).add_day_off(current_user.user_id, project_id, body.day, body.name)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/calendar/days-off/japan", response_model=TeamCalendarResponse)
def import_japanese_holidays(
    project_id: int, body: JapaneseHolidaysRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """その年の日本の祝日をこのプロジェクトの休日に足す（自分か先祖にある日はそのまま。管理者だけ）。"""
    view = TeamCalendarUseCases(db).import_japanese_holidays(current_user.user_id, project_id, body.year)
    return TeamCalendarResponse.from_view(view)


@router.delete("/{project_id}/calendar/days-off/{day}", response_model=TeamCalendarResponse)
def remove_team_day_off(
    project_id: int, day: date, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    view = TeamCalendarUseCases(db).remove_day_off(current_user.user_id, project_id, day)
    return TeamCalendarResponse.from_view(view)


@router.post("/{project_id}/members/{user_id}/leave", response_model=TeamCalendarResponse)
def add_member_leave(
    project_id: int, user_id: int, body: MemberLeaveRequest, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    """その人の休みを足す（同じ日なら休む割合を書き換える。本人か管理者だけ。休みはプロジェクトをまたいで同じ）。"""
    view = TeamCalendarUseCases(db).add_leave(current_user.user_id, project_id, user_id, body.day, body.off_percent)
    return TeamCalendarResponse.from_view(view)


@router.delete("/{project_id}/members/{user_id}/leave/{day}", response_model=TeamCalendarResponse)
def remove_member_leave(
    project_id: int, user_id: int, day: date, db: DbDep, current_user: CurrentUserDep
) -> TeamCalendarResponse:
    view = TeamCalendarUseCases(db).remove_leave(current_user.user_id, project_id, user_id, day)
    return TeamCalendarResponse.from_view(view)
