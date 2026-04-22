from fastapi import APIRouter, Depends

from app.dependencies import get_interaction_service, get_rag_engine, get_retriever
from app.models.schemas import APIResponse, QARequest, SearchRequest
from app.services.rag_service import RAGService
from app.services.retriever_service import RetrieverService
from app.services.interaction_service import InteractionService

router = APIRouter(prefix="/qa", tags=["qa"])


@router.post("", response_model=APIResponse)
def qa(
    request: QARequest,
    retriever: RetrieverService = Depends(get_retriever),
    rag_engine: RAGService = Depends(get_rag_engine),
    interaction_service: InteractionService = Depends(get_interaction_service),
) -> APIResponse:
    primary_result = retriever.search(
        SearchRequest(
            query=request.question,
            region=request.region,
            source_org=request.source_org,
            category=request.category,
            status="all" if request.include_expired else "effective",
            top_k=request.top_k,
        )
    )

    search_result = primary_result
    status_summary = "优先返回现行有效制度"

    if request.include_expired:
        status_summary = "已按请求包含历史/失效制度"
    elif not primary_result.citations:
        fallback_result = retriever.search(
            SearchRequest(
                query=request.question,
                region=request.region,
                source_org=request.source_org,
                category=request.category,
                status="all",
                top_k=request.top_k,
            )
        )
        search_result = fallback_result
        if fallback_result.citations:
            status_summary = "未命中现行有效制度，已返回历史/失效条文（请重点核对时效）"
        else:
            status_summary = "未检索到可用条文"

    answer = rag_engine.answer(
        question=request.question,
        citations=search_result.citations,
        include_expired=request.include_expired,
        effective_status_summary=status_summary,
    )
    answer.latency_ms = search_result.latency_ms
    answer.qa_record_id = interaction_service.record_qa(
        question=request.question,
        answer=answer.answer,
        citations=answer.citations,
        confidence_score=answer.confidence_score,
        consistency_score=answer.consistency_score,
        latency_ms=answer.latency_ms,
        status=answer.generation_status,
        user_id=request.user_id,
        session_id=request.session_id,
    )
    return APIResponse(data=answer)
