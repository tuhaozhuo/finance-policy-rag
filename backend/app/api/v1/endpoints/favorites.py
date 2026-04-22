from fastapi import APIRouter, Depends

from app.dependencies import get_interaction_service
from app.models.schemas import APIResponse, FavoriteCreateRequest, FavoriteItem
from app.services.interaction_service import InteractionService

router = APIRouter(prefix="/favorites", tags=["favorites"])


@router.get("", response_model=APIResponse)
def get_favorites(
    user_id: str | None = None,
    interaction_service: InteractionService = Depends(get_interaction_service),
) -> APIResponse:
    return APIResponse(data=interaction_service.list_favorites(user_id=user_id))


@router.post("", response_model=APIResponse)
def add_favorite(
    request: FavoriteCreateRequest,
    interaction_service: InteractionService = Depends(get_interaction_service),
) -> APIResponse:
    item: FavoriteItem = interaction_service.add_favorite(
        user_id=request.user_id,
        doc_id=request.doc_id,
        article_no=request.article_no,
        note=request.note,
    )
    return APIResponse(data=item)
