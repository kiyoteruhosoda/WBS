from __future__ import annotations
from fastapi import APIRouter, status
from src.application.dto.inbox_dto import CreateInboxItemDTO, ConvertInboxItemDTO
from src.application.use_cases.inbox_use_cases import InboxUseCases
from src.presentation.api.dependencies import DbDep
from src.presentation.api.schemas.inbox_schemas import InboxItemCreateRequest, InboxItemConvertRequest, InboxItemResponse
from src.presentation.api.schemas.task_schemas import TaskResponse

router = APIRouter(prefix="/inbox", tags=["inbox"])
USER_ID = 1


@router.get("", response_model=list[InboxItemResponse])
def list_inbox(db: DbDep) -> list[InboxItemResponse]:
    uc = InboxUseCases(db)
    return [InboxItemResponse.model_validate(i, from_attributes=True) for i in uc.list_items(USER_ID)]


@router.post("", response_model=InboxItemResponse, status_code=status.HTTP_201_CREATED)
def create_inbox_item(body: InboxItemCreateRequest, db: DbDep) -> InboxItemResponse:
    uc = InboxUseCases(db)
    dto = CreateInboxItemDTO(user_id=USER_ID, title=body.title, memo=body.memo)
    return InboxItemResponse.model_validate(uc.create_item(dto), from_attributes=True)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_inbox_item(item_id: int, db: DbDep) -> None:
    uc = InboxUseCases(db)
    uc.delete_item(item_id)


@router.post("/{item_id}/convert", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def convert_inbox_item(item_id: int, body: InboxItemConvertRequest, db: DbDep) -> TaskResponse:
    uc = InboxUseCases(db)
    dto = ConvertInboxItemDTO(
        title=body.title,
        category_id=body.category_id,
        priority=body.priority,
        urgency=body.urgency,
        start_date=body.start_date,
        due_date=body.due_date,
        estimated_hours=body.estimated_hours,
        memo=body.memo,
    )
    return TaskResponse(**uc.convert_to_task(item_id, dto))
