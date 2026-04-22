from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.dependencies import get_embedding_service, get_rag_engine, get_vector_store
from app.models.schemas import APIResponse
from app.services.embedding_service import EmbeddingService
from app.services.rag_service import RAGService
from app.services.vector_store_service import VectorStoreService

router = APIRouter(tags=["ops"])


@router.get("/health", response_model=APIResponse)
def health(
    db: Session = Depends(get_db),
    embedding_service: EmbeddingService = Depends(get_embedding_service),
    vector_store: VectorStoreService = Depends(get_vector_store),
    rag_engine: RAGService = Depends(get_rag_engine),
) -> APIResponse:
    checks: dict[str, dict[str, object]] = {}

    try:
        db.execute(text("SELECT 1"))
        checks["database"] = {"status": "ok"}
    except Exception as exc:
        checks["database"] = {"status": "degraded", "error": str(exc)[:200]}

    checks["embedding"] = embedding_service.health_check()
    checks["vector_store"] = vector_store.health_check()
    checks["llm"] = rag_engine.llm_service.health_check()

    status = "ok" if all(item.get("status") in {"ok", "disabled"} for item in checks.values()) else "degraded"
    return APIResponse(data={"status": status, "time": datetime.now(timezone.utc).isoformat(), "checks": checks})
