from datetime import datetime
from time import perf_counter

from app.models.schemas import Citation, DocumentIngestResponse, QAResponseData, SearchRequest, SearchResult


class StubDocumentPipeline:
    def ingest(self, doc_id: str, force_reindex: bool = False) -> DocumentIngestResponse:
        chunks = 20 if force_reindex else 12
        return DocumentIngestResponse(doc_id=doc_id, chunks_created=chunks, status="indexed")


class StubRetriever:
    def search(self, request: SearchRequest) -> SearchResult:
        start = perf_counter()
        sample = Citation(
            doc_id="doc-sample-001",
            title="示例监管制度",
            article_no="第十二条",
            chapter="第二章",
            chunk_text=f"与‘{request.query}’相关的示例条文片段。",
        )
        latency = int((perf_counter() - start) * 1000)
        return SearchResult(query=request.query, citations=[sample], latency_ms=latency)


class StubConfidenceScorer:
    def score(self, citations: list[Citation], answer: str) -> float:
        if not citations:
            return 0.2
        return 0.9 if len(answer) > 20 else 0.75


class StubRAGEngine:
    def __init__(self, scorer: StubConfidenceScorer) -> None:
        self.scorer = scorer

    def answer(self, question: str, citations: list[Citation], include_expired: bool = False) -> QAResponseData:
        status_summary = "优先返回现行有效制度"
        if include_expired:
            status_summary = "已按请求包含历史/失效制度"

        answer = f"基于当前检索结果，问题‘{question}’可参考已命中的监管条文进行合规判断。"
        confidence = self.scorer.score(citations, answer)

        return QAResponseData(
            answer=answer,
            citations=citations,
            related_articles=[c.article_no for c in citations if c.article_no],
            confidence_score=confidence,
            effective_status_summary=status_summary,
            latency_ms=120,
        )
