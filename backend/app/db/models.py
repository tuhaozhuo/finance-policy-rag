from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    doc_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    source_org: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    document_number: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    region: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    publish_date: Mapped[date] = mapped_column(Date, nullable=True)
    effective_date: Mapped[date] = mapped_column(Date, nullable=True)
    expire_date: Mapped[date] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="effective", index=True)
    status_evidence: Mapped[str] = mapped_column(Text, nullable=True)
    file_type: Mapped[str] = mapped_column(String(16), nullable=False)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=True)
    source_url: Mapped[str] = mapped_column(String(1024), nullable=True)
    ocr_needed: Mapped[bool] = mapped_column(Boolean, default=False)
    tags_json: Mapped[str] = mapped_column(Text, default="[]")
    metadata_evidence_json: Mapped[str] = mapped_column(Text, default="{}")

    source_hash: Mapped[str] = mapped_column(String(64), nullable=True)
    ingest_status: Mapped[str] = mapped_column(String(32), default="uploaded", index=True)
    chunks_count: Mapped[int] = mapped_column(Integer, default=0)
    last_ingested_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    chunks: Mapped[list["Chunk"]] = relationship("Chunk", back_populates="document", cascade="all, delete-orphan")


class Chunk(Base):
    __tablename__ = "chunks"

    chunk_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    doc_id: Mapped[str] = mapped_column(ForeignKey("documents.doc_id", ondelete="CASCADE"), index=True)
    chapter: Mapped[str] = mapped_column(String(128), nullable=True, index=True)
    article_no: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    keywords_json: Mapped[str] = mapped_column(Text, default="[]")
    status: Mapped[str] = mapped_column(String(32), default="effective", index=True)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=True)
    vector_id: Mapped[str] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    document: Mapped["Document"] = relationship("Document", back_populates="chunks")


class IngestTask(Base):
    __tablename__ = "ingest_tasks"

    task_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    force_reindex: Mapped[bool] = mapped_column(Boolean, default=False)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    next_retry_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    current_stage: Mapped[str] = mapped_column(String(64), nullable=True)
    stage_metrics_json: Mapped[str] = mapped_column(Text, default="{}")
    last_error: Mapped[str] = mapped_column(Text, nullable=True)
    last_started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_finished_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=True)
    last_result_status: Mapped[str] = mapped_column(String(32), nullable=True)
    last_chunks_created: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class QARecord(Base):
    __tablename__ = "qa_records"

    record_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    user_id: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    query_type: Mapped[str] = mapped_column(String(32), default="qa", index=True)
    answer: Mapped[str] = mapped_column(Text, default="")
    confidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    consistency_score: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="success", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)

    citations: Mapped[list["QACitation"]] = relationship("QACitation", back_populates="qa_record", cascade="all, delete-orphan")


class QACitation(Base):
    __tablename__ = "qa_citations"

    citation_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    qa_record_id: Mapped[str] = mapped_column(ForeignKey("qa_records.record_id", ondelete="CASCADE"), index=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(512), nullable=True)
    article_no: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    chapter: Mapped[str] = mapped_column(String(128), nullable=True)
    quote_text: Mapped[str] = mapped_column(Text, nullable=True)
    rank_no: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)

    qa_record: Mapped["QARecord"] = relationship("QARecord", back_populates="citations")


class Favorite(Base):
    __tablename__ = "favorites"

    favorite_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(64), index=True)
    doc_id: Mapped[str] = mapped_column(String(64), index=True)
    article_no: Mapped[str] = mapped_column(String(64), nullable=True, index=True)
    note: Mapped[str] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
