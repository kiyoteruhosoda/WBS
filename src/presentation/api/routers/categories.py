from __future__ import annotations

from fastapi import APIRouter, status

from src.application.dto.category_dto import CreateCategoryDTO, UpdateCategoryDTO
from src.application.use_cases.category_use_cases import CategoryUseCases
from src.presentation.api.dependencies import DbDep
from src.presentation.api.schemas.category_schemas import (
    CategoryCreateRequest,
    CategoryResponse,
    CategoryUpdateRequest,
)

router = APIRouter(prefix="/categories", tags=["categories"])
USER_ID = 1


@router.get("", response_model=list[CategoryResponse])
def list_categories(db: DbDep) -> list[CategoryResponse]:
    uc = CategoryUseCases(db)
    return [CategoryResponse.model_validate(c, from_attributes=True) for c in uc.list_categories(USER_ID)]


@router.post("", response_model=CategoryResponse, status_code=status.HTTP_201_CREATED)
def create_category(body: CategoryCreateRequest, db: DbDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    dto = CreateCategoryDTO(user_id=USER_ID, name=body.name, color=body.color, sort_order=body.sort_order)
    return CategoryResponse.model_validate(uc.create_category(dto), from_attributes=True)


@router.get("/{category_id}", response_model=CategoryResponse)
def get_category(category_id: int, db: DbDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    return CategoryResponse.model_validate(uc.get_category(category_id), from_attributes=True)


@router.put("/{category_id}", response_model=CategoryResponse)
def update_category(category_id: int, body: CategoryUpdateRequest, db: DbDep) -> CategoryResponse:
    uc = CategoryUseCases(db)
    dto = UpdateCategoryDTO(name=body.name, color=body.color, sort_order=body.sort_order)
    return CategoryResponse.model_validate(uc.update_category(category_id, dto), from_attributes=True)


@router.delete("/{category_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_category(category_id: int, db: DbDep) -> None:
    uc = CategoryUseCases(db)
    uc.delete_category(category_id)
