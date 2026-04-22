from __future__ import annotations

from app.models.schemas import Citation, QAResponseData
from app.services.consistency_service import AnswerConsistencyChecker
from app.services.llm_service import LLMService


class ConfidenceScorer:
    def score(
        self,
        citations: list[Citation],
        answer: str,
        consistency_score: float,
        evidence_coverage: float,
        generation_status: str,
        effective_hit: bool,
    ) -> float:
        if not citations:
            return 0.2
        retrieval_avg = 0.0
        scored = [item.retrieval_score for item in citations if item.retrieval_score is not None]
        if scored:
            retrieval_avg = sum(scored) / len(scored)

        base = (
            0.25
            + min(0.22, len(citations) * 0.045)
            + min(0.22, retrieval_avg * 0.32)
            + 0.18 * consistency_score
            + 0.10 * evidence_coverage
            + (0.06 if effective_hit else -0.08)
        )
        if generation_status != "success":
            base -= 0.22
        if "无法" in answer or "不确定" in answer:
            base -= 0.08
        if len(answer.strip()) < 20:
            base -= 0.08
        return round(max(0.05, min(base, 0.95)), 2)


class RAGService:
    def __init__(self, llm_service: LLMService, scorer: ConfidenceScorer, consistency_checker: AnswerConsistencyChecker) -> None:
        self.llm_service = llm_service
        self.scorer = scorer
        self.consistency_checker = consistency_checker

    def answer(
        self,
        question: str,
        citations: list[Citation],
        include_expired: bool = False,
        effective_status_summary: str | None = None,
    ) -> QAResponseData:
        status_summary = effective_status_summary or "优先返回现行有效制度"
        if include_expired and effective_status_summary is None:
            status_summary = "已按请求包含历史/失效制度"

        # 空证据场景直接返回，避免调用远端 LLM 造成额外超时。
        if not citations:
            return QAResponseData(
                answer=f"未检索到足够条文，暂无法对“{question}”给出高置信度结论。",
                citations=[],
                related_articles=[],
                confidence_score=0.2,
                consistency_score=0.0,
                evidence_coverage=0.0,
                generation_status="no_evidence",
                degraded_reason="no citations",
                effective_status_summary=status_summary,
                latency_ms=0,
            )

        contexts = [item.chunk_text for item in citations]
        generation = self.llm_service.generate(question=question, contexts=contexts)
        answer = generation.text

        consistency_score = self.consistency_checker.score(answer, citations)
        evidence_coverage = self._evidence_coverage(answer, citations)
        effective_hit = "历史/失效" not in status_summary and "未命中现行有效" not in status_summary
        confidence = self.scorer.score(
            citations=citations,
            answer=answer,
            consistency_score=consistency_score,
            evidence_coverage=evidence_coverage,
            generation_status=generation.status,
            effective_hit=effective_hit,
        )
        if confidence < 0.55:
            answer = f"{answer}\n\n提示：当前证据较弱，请优先核对原文条款后再决策。"
        return QAResponseData(
            answer=answer,
            citations=citations,
            related_articles=[item.article_no for item in citations if item.article_no],
            confidence_score=confidence,
            consistency_score=consistency_score,
            evidence_coverage=evidence_coverage,
            generation_status=generation.status,
            degraded_reason=generation.degraded_reason,
            effective_status_summary=status_summary,
            latency_ms=0,
        )

    def _evidence_coverage(self, answer: str, citations: list[Citation]) -> float:
        if not answer or not citations:
            return 0.0
        answer_terms = self.consistency_checker._tokenize(answer)  # noqa: SLF001
        if not answer_terms:
            return 0.0
        cited_terms: set[str] = set()
        for item in citations[:6]:
            cited_terms.update(self.consistency_checker._tokenize(item.chunk_text))  # noqa: SLF001
        return round(len(answer_terms.intersection(cited_terms)) / max(1, len(answer_terms)), 2)
