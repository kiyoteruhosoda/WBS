"""プロジェクト（入れ子。task #187 / ADR-0024）。

- ``GET /projects``: 全部（保管したものも）を木の順（親の直後に子）で
- ``POST /projects/{id}/move``: 親を替える・兄弟の中で並べ替える（自分の下へは 409）
- ``DELETE /projects/{id}``: 空のものだけ（中身があれば 409。保管は ``PUT`` で ``status``）。いちばん上は管理者だけ
- ``/projects/{id}/members``: いちばん上のプロジェクトのメンバー（task #544 / ADR-0055）。どの段の id でも根の名簿
- ``GET /projects/people``: メンバー・担当者に選べる人
"""

from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.project_dto import CreateProjectDTO, MoveProjectDTO, UpdateProjectDTO
from src.application.use_cases.project_use_cases import ProjectUseCases
from src.presentation.api.dependencies import (
    CurrentUserDep,
    DbDep,
    ProjectMemberUseCasesDep,
)
from src.presentation.api.schemas.project_schemas import (
    PersonResponse,
    ProjectCreateRequest,
    ProjectMemberRequest,
    ProjectMemberRoleRequest,
    ProjectMembersResponse,
    ProjectMoveRequest,
    ProjectResponse,
    ProjectUpdateRequest,
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
