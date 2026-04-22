from __future__ import annotations

import re

from app.models.schemas import Citation


class AnswerConsistencyChecker:
    def score(self, answer: str, citations: list[Citation]) -> float:
        answer_tokens = self._tokenize(answer)
        if not answer_tokens or not citations:
            return 0.0

        citation_tokens: set[str] = set()
        for item in citations[:6]:
            citation_tokens.update(self._tokenize(item.chunk_text))

        overlap = answer_tokens.intersection(citation_tokens)
        overlap_ratio = len(overlap) / max(1, len(answer_tokens))

        strong_hit = 0
        for token in overlap:
            if len(token) >= 3:
                strong_hit += 1
        strength_ratio = strong_hit / max(1, len(answer_tokens))

        score = 0.7 * overlap_ratio + 0.3 * strength_ratio
        return round(max(0.0, min(score, 1.0)), 2)

    def _tokenize(self, text: str) -> set[str]:
        tokens = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", text)
        result: set[str] = set()
        for token in tokens:
            result.add(token.lower())
            if len(result) >= 256:
                break
        return result
