from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.category_dto import CreateCategoryDTO, UpdateCategoryDTO
from src.application.use_cases.category_use_cases import CategoryUseCases
from src.presentation.api.dependencies import CurrentUserDep, DbDep
from src.presentation.api.schemas.category_schemas import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)

router = APIRouter(prefix="/categories", tags=["categories"])


@router.get("", response_model=list[CategoryResponse])
def list_categories(db: DbDep, current_user: CurrentUserDep) -> list[CategoryResponse]:
    uc = CategoryUseCases(db)
    return [CategoryResponse.model_validate(c, from_attributes=True) for c in uc.list_categories(current_user.user_id)]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreateRequest, db: DbDep, current_user: CurrentUserDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    dto = CreateCategoryDTO(user_id=current_user.user_id, name=body.name, color=body.color, sort_order=body.sort_order)
    return CategoryResponse.model_validate(uc.create_category(dto), from_attributes=True)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: DbDep, current_user: CurrentUserDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    return CategoryResponse.model_validate(uc.get_category(category_id, current_user.user_id), from_attributes=True)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, body: CategoryUpdateRequest, db: DbDep, current_user: CurrentUserDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    # 送信されたフィールドのみ DTO へ渡す（未指定は UNSET のまま＝変更しない）。
    # 明示的な null はクリアとして反映される。
    dto = UpdateCategoryDTO(**body.model_dump(exclude_unset=True))
    return CategoryResponse.model_validate(uc.update_category(category_id, current_user.user_id, dto), from_attributes=True)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: DbDep, current_user: CurrentUserDep) -> None:
    uc = CategoryUseCases(db)
    uc.delete_category(category_id, current_user.user_id)
