from __future__ import annotations

import re
import math
from time import perf_counter

from sqlalchemy import Select, or_, select
from sqlalchemy.orm import Session

from app.db.models import Chunk, Document
from app.models.schemas import Citation, RelatedSearchRequest, RelatedSearchResult, SearchRequest, SearchResult
from app.services.embedding_service import EmbeddingService
from app.services.rerank_service import RerankService
from app.services.vector_store_service import VectorStoreService


class RetrieverService:
    def __init__(
        self,
        session_factory,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
        reranker: RerankService,
    ) -> None:
        self.session_factory = session_factory
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.reranker = reranker

    def search(self, request: SearchRequest) -> SearchResult:
        start = perf_counter()
        recall_k = max(12, request.top_k * 4)
        tokens = self._tokenize(request.query)

        with self.session_factory() as session:
            base = self._apply_filters(select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id), request)

            keyword_rows = self._keyword_recall(session, base, request.query, tokens, recall_k)
            vector_scores = self._vector_recall(request, recall_k)
            vector_rows = self._vector_rows(session, base, list(vector_scores.keys()))

        merged: dict[str, dict[str, object]] = {}
        for chunk, doc in keyword_rows:
            merged[chunk.chunk_id] = {
                "chunk": chunk,
                "doc": doc,
                "keyword": 0.0,
                "vector": 0.0,
                "source": {"keyword"},
            }

        for chunk, doc in vector_rows:
            item = merged.get(chunk.chunk_id)
            vector_score = float(vector_scores.get(chunk.vector_id or "", 0.0))
            if item is None:
                merged[chunk.chunk_id] = {
                    "chunk": chunk,
                    "doc": doc,
                    "keyword": 0.0,
                    "vector": vector_score,
                    "source": {"vector"},
                }
            else:
                item["vector"] = max(float(item["vector"]), vector_score)
                item["source"].add("vector")

        self._assign_bm25_scores(merged, request.query, tokens)
        ranked = sorted(merged.values(), key=self._final_score, reverse=True)[: request.top_k]

        citations: list[Citation] = []
        for item in ranked:
            chunk: Chunk = item["chunk"]
            doc: Document = item["doc"]
            source_set: set[str] = item["source"]

            if source_set == {"keyword"}:
                source = "keyword"
            elif source_set == {"vector"}:
                source = "vector"
            elif source_set == {"keyword", "vector"}:
                source = "hybrid"
            else:
                source = ",".join(sorted(source_set))

            citations.append(
                Citation(
                    doc_id=doc.doc_id,
                    title=doc.title,
                    article_no=chunk.article_no,
                    chapter=chunk.chapter,
                    chunk_text=chunk.chunk_text,
                    retrieval_score=round(self._final_score(item), 4),
                    retrieval_source=source,
                )
            )

        latency_ms = int((perf_counter() - start) * 1000)
        return SearchResult(
            query=request.query,
            citations=citations,
            latency_ms=latency_ms,
            keyword_candidates=len(keyword_rows),
            vector_candidates=len(vector_rows),
            reranked_candidates=len(merged),
        )

    def search_related(self, request: RelatedSearchRequest) -> RelatedSearchResult:
        if not any([request.query, request.doc_id, request.article_no, request.chapter]):
            raise ValueError("related query requires at least one of query/doc_id/article_no/chapter")

        start = perf_counter()
        window = max(1, min(request.neighbor_window, 8))

        with self.session_factory() as session:
            base = self._apply_related_filters(select(Chunk, Document).join(Document, Chunk.doc_id == Document.doc_id), request)
            anchors = self._find_anchor_rows(session, base, request)
            if not anchors:
                return RelatedSearchResult(anchor_citations=[], related_citations=[], expanded_from=0, latency_ms=int((perf_counter() - start) * 1000))

            anchor_ids = {chunk.chunk_id for chunk, _ in anchors}
            related_pool = self._expand_related_rows(session, base, anchors, request, window)

        anchor_citations = [self._to_citation(chunk, doc, source="anchor", score=1.0) for chunk, doc in anchors[: request.top_k]]

        ranked_related = sorted(related_pool.values(), key=lambda x: float(x["score"]), reverse=True)
        related_citations: list[Citation] = []
        for item in ranked_related:
            chunk: Chunk = item["chunk"]
            doc: Document = item["doc"]
            if chunk.chunk_id in anchor_ids:
                continue
            related_citations.append(
                self._to_citation(
                    chunk,
                    doc,
                    source=str(item["source"]),
                    score=float(item["score"]),
                )
            )
            if len(related_citations) >= request.top_k:
                break

        latency_ms = int((perf_counter() - start) * 1000)
        return RelatedSearchResult(
            anchor_citations=anchor_citations,
            related_citations=related_citations,
            expanded_from=len(anchors),
            latency_ms=latency_ms,
        )

    def _apply_filters(self, statement: Select, request: SearchRequest) -> Select:
        if request.status != "all":
            statement = statement.where(Document.status == request.status)
        if request.region:
            statement = statement.where(Document.region == request.region)
        if request.source_org:
            statement = statement.where(Document.source_org == request.source_org)
        if request.category:
            statement = statement.where(Document.category == request.category)
        return statement

    def _apply_related_filters(self, statement: Select, request: RelatedSearchRequest) -> Select:
        if request.status != "all":
            statement = statement.where(Document.status == request.status)
        if request.doc_id:
            statement = statement.where(Document.doc_id == request.doc_id)
        return statement

    def _keyword_recall(
        self,
        session: Session,
        base: Select,
        query: str,
        tokens: list[str],
        recall_k: int,
    ) -> list[tuple[Chunk, Document]]:
        results: dict[str, tuple[Chunk, Document]] = {}

        exact_stmt = base.where(Chunk.chunk_text.contains(query)).limit(recall_k)
        for chunk, doc in session.execute(exact_stmt).all():
            results[chunk.chunk_id] = (chunk, doc)

        if len(results) < recall_k and tokens:
            token_conds = [Chunk.chunk_text.contains(token) for token in tokens[:6]]
            token_stmt = base.where(or_(*token_conds)).limit(recall_k * 2)
            for chunk, doc in session.execute(token_stmt).all():
                results.setdefault(chunk.chunk_id, (chunk, doc))

        return list(results.values())

    def _find_anchor_rows(self, session: Session, base: Select, request: RelatedSearchRequest) -> list[tuple[Chunk, Document]]:
        anchors: dict[str, tuple[Chunk, Document]] = {}
        limit = max(5, request.top_k * 3)

        if request.article_no:
            stmt = base.where(Chunk.article_no == request.article_no).limit(limit)
            for chunk, doc in session.execute(stmt).all():
                anchors[chunk.chunk_id] = (chunk, doc)

        if request.chapter and len(anchors) < limit:
            stmt = base.where(Chunk.chapter.contains(request.chapter)).limit(limit)
            for chunk, doc in session.execute(stmt).all():
                anchors.setdefault(chunk.chunk_id, (chunk, doc))

        if request.query and len(anchors) < limit:
            query_stmt = base.where(Chunk.chunk_text.contains(request.query)).limit(limit)
            for chunk, doc in session.execute(query_stmt).all():
                anchors.setdefault(chunk.chunk_id, (chunk, doc))

            tokens = self._tokenize(request.query)
            if len(anchors) < limit and tokens:
                token_stmt = base.where(or_(*[Chunk.chunk_text.contains(token) for token in tokens[:8]])).limit(limit * 2)
                for chunk, doc in session.execute(token_stmt).all():
                    anchors.setdefault(chunk.chunk_id, (chunk, doc))

        if not anchors and request.doc_id:
            fallback = session.execute(base.limit(limit)).all()
            for chunk, doc in fallback:
                anchors.setdefault(chunk.chunk_id, (chunk, doc))

        return list(anchors.values())

    def _expand_related_rows(
        self,
        session: Session,
        base: Select,
        anchors: list[tuple[Chunk, Document]],
        request: RelatedSearchRequest,
        window: int,
    ) -> dict[str, dict[str, object]]:
        related: dict[str, dict[str, object]] = {}

        # 1) 同文邻接扩展
        anchor_by_doc: dict[str, list[int]] = {}
        for chunk, doc in anchors:
            ordinal = self._chunk_ordinal(chunk.chunk_id)
            if ordinal is None:
                continue
            anchor_by_doc.setdefault(doc.doc_id, []).append(ordinal)

        for doc_id, ordinals in anchor_by_doc.items():
            rows = session.execute(base.where(Document.doc_id == doc_id).limit(2000)).all()
            for chunk, doc in rows:
                ordinal = self._chunk_ordinal(chunk.chunk_id)
                if ordinal is None:
                    continue
                min_dist = min(abs(ordinal - anchor_ord) for anchor_ord in ordinals)
                if min_dist == 0 or min_dist > window:
                    continue
                score = 0.9 / (1.0 + min_dist)
                self._upsert_related(related, chunk, doc, score=score, source="neighbor")

        # 2) 同条号跨文扩展
        article_set = {chunk.article_no for chunk, _ in anchors if chunk.article_no}
        if article_set:
            stmt = base.where(Chunk.article_no.in_(list(article_set))).limit(max(20, request.top_k * 8))
            for chunk, doc in session.execute(stmt).all():
                self._upsert_related(related, chunk, doc, score=0.55, source="same_article")

        # 3) 关键词扩展
        token_source = request.query or "\n".join(chunk.chunk_text[:120] for chunk, _ in anchors[:3])
        tokens = self._tokenize(token_source)
        if tokens:
            stmt = base.where(or_(*[Chunk.chunk_text.contains(token) for token in tokens[:8]])).limit(max(30, request.top_k * 12))
            for chunk, doc in session.execute(stmt).all():
                token_hit = sum(1 for token in tokens[:8] if token in chunk.chunk_text)
                score = min(0.5, token_hit / max(1, len(tokens[:8])) * 0.5)
                self._upsert_related(related, chunk, doc, score=score, source="keyword")

        return related

    def _upsert_related(self, related: dict[str, dict[str, object]], chunk: Chunk, doc: Document, score: float, source: str) -> None:
        existing = related.get(chunk.chunk_id)
        if existing is None:
            related[chunk.chunk_id] = {"chunk": chunk, "doc": doc, "score": score, "source": source}
            return
        if score > float(existing["score"]):
            existing["score"] = score
            existing["source"] = source

    def _vector_recall(self, request: SearchRequest, recall_k: int) -> dict[str, float]:
        vector = self.embedding_service.embed_query(request.query)
        if not vector:
            return {}

        hits = self.vector_store.search(
            vector,
            top_k=recall_k,
            filters={
                "region": request.region,
                "category": request.category,
                "status": request.status,
            },
        )
        return {hit.vector_id: hit.score for hit in hits}

    def _vector_rows(self, session: Session, base: Select, vector_ids: list[str]) -> list[tuple[Chunk, Document]]:
        if not vector_ids:
            return []

        limited_ids = vector_ids[:200]
        stmt = base.where(Chunk.vector_id.in_(limited_ids)).limit(len(limited_ids))
        rows = session.execute(stmt).all()
        row_map = {chunk.vector_id: (chunk, doc) for chunk, doc in rows if chunk.vector_id}

        ordered: list[tuple[Chunk, Document]] = []
        for vector_id in limited_ids:
            item = row_map.get(vector_id)
            if item is not None:
                ordered.append(item)
        return ordered

    def _tokenize(self, query: str, max_tokens: int = 18) -> list[str]:
        chunks = re.findall(r"[\u4e00-\u9fff]{2,}|[a-zA-Z0-9]{2,}", query)
        unique: list[str] = []
        seen: set[str] = set()

        for chunk in chunks:
            candidates: list[str] = []
            if re.fullmatch(r"[\u4e00-\u9fff]{2,}", chunk):
                # 中文连续文本拆成短片段，提升自然问句的关键词召回命中率。
                for size in (4, 3, 2):
                    if len(chunk) < size:
                        continue
                    for idx in range(0, len(chunk) - size + 1):
                        candidates.append(chunk[idx : idx + size])
            else:
                candidates.append(chunk.lower())

            for token in candidates:
                if token in seen:
                    continue
                seen.add(token)
                unique.append(token)
                if len(unique) >= max_tokens:
                    return unique
        return unique

    def _assign_bm25_scores(self, merged: dict[str, dict[str, object]], query: str, tokens: list[str]) -> None:
        if not merged or not tokens:
            return

        docs: list[tuple[str, str]] = []
        for chunk_id, item in merged.items():
            chunk: Chunk = item["chunk"]
            doc: Document = item["doc"]
            docs.append((chunk_id, f"{doc.title or ''}\n{chunk.chunk_text}"))

        avg_len = sum(len(self._tokenize(text, max_tokens=512)) for _, text in docs) / max(1, len(docs))
        df: dict[str, int] = {}
        tokenized_docs: dict[str, list[str]] = {}
        for chunk_id, text in docs:
            doc_tokens = self._tokenize(text, max_tokens=512)
            tokenized_docs[chunk_id] = doc_tokens
            unique = set(doc_tokens)
            for token in tokens:
                if token in unique:
                    df[token] = df.get(token, 0) + 1

        n_docs = len(docs)
        raw_scores: dict[str, float] = {}
        for chunk_id, text in docs:
            doc_tokens = tokenized_docs.get(chunk_id, [])
            doc_len = len(doc_tokens) or 1
            raw = 0.0
            for token in tokens:
                freq = doc_tokens.count(token)
                if freq <= 0:
                    continue
                idf = math.log(1 + (n_docs - df.get(token, 0) + 0.5) / (df.get(token, 0) + 0.5))
                raw += idf * (freq * 2.2) / (freq + 1.2 * (1 - 0.75 + 0.75 * doc_len / max(1.0, avg_len)))

            exact_bonus = 1.0 if query and query in text else 0.0
            raw_scores[chunk_id] = raw + exact_bonus

        max_score = max(raw_scores.values()) if raw_scores else 0.0
        if max_score <= 0:
            return
        for chunk_id, raw in raw_scores.items():
            merged[chunk_id]["keyword"] = min(1.0, raw / max_score)

    def _final_score(self, item: dict[str, object]) -> float:
        doc: Document = item["doc"]
        keyword_score = float(item["keyword"])
        vector_score = float(item["vector"])
        source_set: set[str] = item["source"]
        return self.reranker.final_score(keyword_score, vector_score, doc.status, len(source_set))

    def _chunk_ordinal(self, chunk_id: str) -> int | None:
        match = re.search(r"-c(\d+)$", chunk_id)
        if not match:
            return None
        return int(match.group(1))

    def _to_citation(self, chunk: Chunk, doc: Document, source: str, score: float) -> Citation:
        return Citation(
            doc_id=doc.doc_id,
            title=doc.title,
            article_no=chunk.article_no,
            chapter=chunk.chapter,
            chunk_text=chunk.chunk_text,
            retrieval_score=round(score, 4),
            retrieval_source=source,
        )
