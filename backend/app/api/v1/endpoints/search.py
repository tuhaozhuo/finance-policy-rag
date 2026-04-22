from fastapi import APIRouter, Depends, HTTPException

from app.dependencies import get_retriever
from app.models.schemas import APIResponse, RelatedSearchRequest, SearchRequest
from app.services.retriever_service import RetrieverService

router = APIRouter(prefix="/search", tags=["search"])


@router.post("", response_model=APIResponse)
def search(request: SearchRequest, retriever: RetrieverService = Depends(get_retriever)) -> APIResponse:
    result = retriever.search(request)
    return APIResponse(data=result)


@router.post("/related", response_model=APIResponse)
def search_related(request: RelatedSearchRequest, retriever: RetrieverService = Depends(get_retriever)) -> APIResponse:
    try:
        result = retriever.search_related(request)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return APIResponse(data=result)
