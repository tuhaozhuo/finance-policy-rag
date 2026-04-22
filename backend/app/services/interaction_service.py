from __future__ import annotations

from uuid import uuid4

from sqlalchemy import select

from app.db.models import Favorite, QACitation, QARecord
from app.models.schemas import Citation, FavoriteItem, HistoryItem


class InteractionService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def list_history(self, user_id: str | None = None, limit: int = 100) -> list[HistoryItem]:
        with self.session_factory() as session:
            statement = select(QARecord).order_by(QARecord.created_at.desc()).limit(max(1, min(limit, 500)))
            if user_id:
                statement = statement.where(QARecord.user_id == user_id)
            rows = session.execute(statement).scalars().all()

        return [
            HistoryItem(
                history_id=item.record_id,
                user_id=item.user_id or "",
                query_text=item.question,
                query_type=item.query_type,
                created_at=item.created_at,
            )
            for item in rows
        ]

    def add_history(self, user_id: str, query_text: str, query_type: str) -> HistoryItem:
        with self.session_factory() as session:
            row = QARecord(
                record_id=f"his-{uuid4().hex[:12]}",
                user_id=user_id,
                question=query_text,
                query_type=query_type,
                answer="",
                status="manual",
            )
            session.add(row)
            session.commit()
            session.refresh(row)

        return HistoryItem(
            history_id=row.record_id,
            user_id=row.user_id or "",
            query_text=row.question,
            query_type=row.query_type,
            created_at=row.created_at,
        )

    def record_qa(
        self,
        question: str,
        answer: str,
        citations: list[Citation],
        confidence_score: float,
        consistency_score: float,
        latency_ms: int,
        status: str = "success",
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> str:
        record_id = f"qa-{uuid4().hex[:12]}"
        with self.session_factory() as session:
            row = QARecord(
                record_id=record_id,
                session_id=session_id,
                user_id=user_id,
                question=question,
                query_type="qa",
                answer=answer,
                confidence_score=confidence_score,
                consistency_score=consistency_score,
                latency_ms=latency_ms,
                status=status,
            )
            session.add(row)

            for idx, item in enumerate(citations):
                session.add(
                    QACitation(
                        citation_id=f"cite-{uuid4().hex[:12]}",
                        qa_record_id=record_id,
                        doc_id=item.doc_id,
                        title=item.title,
                        article_no=item.article_no,
                        chapter=item.chapter,
                        quote_text=item.chunk_text,
                        rank_no=idx + 1,
                        score=float(item.retrieval_score or 0.0),
                    )
                )
            session.commit()
        return record_id

    def list_favorites(self, user_id: str | None = None, limit: int = 100) -> list[FavoriteItem]:
        with self.session_factory() as session:
            statement = select(Favorite).order_by(Favorite.created_at.desc()).limit(max(1, min(limit, 500)))
            if user_id:
                statement = statement.where(Favorite.user_id == user_id)
            rows = session.execute(statement).scalars().all()

        return [
            FavoriteItem(
                favorite_id=item.favorite_id,
                user_id=item.user_id,
                doc_id=item.doc_id,
                article_no=item.article_no,
                note=item.note,
                created_at=item.created_at,
            )
            for item in rows
        ]

    def add_favorite(self, user_id: str, doc_id: str, article_no: str | None = None, note: str | None = None) -> FavoriteItem:
        with self.session_factory() as session:
            row = Favorite(
                favorite_id=f"fav-{uuid4().hex[:12]}",
                user_id=user_id,
                doc_id=doc_id,
                article_no=article_no,
                note=note,
            )
            session.add(row)
            session.commit()
            session.refresh(row)

        return FavoriteItem(
            favorite_id=row.favorite_id,
            user_id=row.user_id,
            doc_id=row.doc_id,
            article_no=row.article_no,
            note=row.note,
            created_at=row.created_at,
        )
