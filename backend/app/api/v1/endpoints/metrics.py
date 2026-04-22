from fastapi import APIRouter

from app.core.metrics import metrics_store
from app.models.schemas import APIResponse

router = APIRouter(tags=["ops"])


@router.get("/metrics", response_model=APIResponse)
def metrics() -> APIResponse:
    return APIResponse(data=metrics_store.snapshot())
