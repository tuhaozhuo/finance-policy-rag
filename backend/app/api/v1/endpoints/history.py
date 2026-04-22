from fastapi import APIRouter, Depends

from app.dependencies import get_interaction_service
from app.models.schemas import APIResponse, HistoryCreateRequest, HistoryItem
from app.services.interaction_service import InteractionService

router = APIRouter(prefix="/history", tags=["history"])


@router.get("", response_model=APIResponse)
def get_history(
    user_id: str | None = None,
    interaction_service: InteractionService = Depends(get_interaction_service),
) -> APIResponse:
    return APIResponse(data=interaction_service.list_history(user_id=user_id))


@router.post("", response_model=APIResponse)
def add_history(
    request: HistoryCreateRequest,
    interaction_service: InteractionService = Depends(get_interaction_service),
) -> APIResponse:
    item: HistoryItem = interaction_service.add_history(
        user_id=request.user_id,
        query_text=request.query_text,
        query_type=request.query_type,
    )
    return APIResponse(data=item)
