from __future__ import annotations


class RerankService:
    def final_score(self, keyword_score: float, vector_score: float, status: str | None, source_count: int) -> float:
        status_bonus = 1.0 if status == "effective" else 0.82
        hybrid_bonus = 0.05 if source_count >= 2 else 0.0
        score = 0.62 * keyword_score + 0.30 * vector_score + 0.08 * status_bonus + hybrid_bonus
        return max(0.0, min(score, 1.0))
