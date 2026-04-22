from datetime import date, datetime
from typing import Any

from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    code: int = 0
    message: str = "ok"
    data: Any | None = None


class DocumentBase(BaseModel):
    title: str
    source_org: str | None = None
    document_number: str | None = None
    region: str | None = None
    category: str | None = None
    publish_date: date | None = None
    effective_date: date | None = None
    expire_date: date | None = None
    status: str = "effective"
    status_evidence: str | None = None
    file_type: str
    source_path: str | None = None
    source_url: str | None = None
    ocr_needed: bool = False
    tags: list[str] = Field(default_factory=list)
    metadata_evidence: dict[str, Any] = Field(default_factory=dict)


class DocumentUploadResponse(BaseModel):
    doc_id: str
    filename: str
    stored_path: str


class DocumentIngestRequest(BaseModel):
    doc_id: str
    force_reindex: bool = False


class DocumentIngestResponse(BaseModel):
    doc_id: str
    chunks_created: int
    status: str
    vector_status: str | None = None
    stage_metrics: dict[str, Any] = Field(default_factory=dict)


class DocumentItem(DocumentBase):
    doc_id: str
    ingest_status: str = "uploaded"
    chunks_count: int = 0
    last_ingested_at: datetime | None = None
    created_at: datetime


class DocumentTagsUpdateRequest(BaseModel):
    tags: list[str] = Field(default_factory=list)


class TagSummaryItem(BaseModel):
    tag: str
    count: int


class SearchRequest(BaseModel):
    query: str
    region: str | None = None
    source_org: str | None = None
    category: str | None = None
    status: str = "effective"
    top_k: int = 5


class Citation(BaseModel):
    doc_id: str
    title: str
    article_no: str | None = None
    chapter: str | None = None
    chunk_text: str
    retrieval_score: float | None = None
    retrieval_source: str | None = None


class SearchResult(BaseModel):
    query: str
    citations: list[Citation] = Field(default_factory=list)
    latency_ms: int
    keyword_candidates: int = 0
    vector_candidates: int = 0
    reranked_candidates: int = 0


class RelatedSearchRequest(BaseModel):
    query: str | None = None
    doc_id: str | None = None
    article_no: str | None = None
    chapter: str | None = None
    status: str = "effective"
    top_k: int = 5
    neighbor_window: int = 2


class RelatedSearchResult(BaseModel):
    anchor_citations: list[Citation] = Field(default_factory=list)
    related_citations: list[Citation] = Field(default_factory=list)
    expanded_from: int = 0
    latency_ms: int


class QARequest(BaseModel):
    question: str
    user_id: str | None = None
    session_id: str | None = None
    region: str | None = None
    source_org: str | None = None
    category: str | None = None
    include_expired: bool = False
    top_k: int = 5


class QAResponseData(BaseModel):
    qa_record_id: str | None = None
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    related_articles: list[str] = Field(default_factory=list)
    confidence_score: float
    consistency_score: float = 0.0
    evidence_coverage: float = 0.0
    generation_status: str = "success"
    degraded_reason: str | None = None
    effective_status_summary: str
    latency_ms: int


class HistoryCreateRequest(BaseModel):
    user_id: str
    query_text: str
    query_type: str


class HistoryItem(BaseModel):
    history_id: str
    user_id: str
    query_text: str
    query_type: str
    created_at: datetime


class FavoriteCreateRequest(BaseModel):
    user_id: str
    doc_id: str
    article_no: str | None = None
    note: str | None = None


class FavoriteItem(BaseModel):
    favorite_id: str
    user_id: str
    doc_id: str
    article_no: str | None = None
    note: str | None = None
    created_at: datetime


class IngestTaskCreateRequest(BaseModel):
    doc_ids: list[str] = Field(default_factory=list)
    force_reindex: bool = False
    max_attempts: int = 3


class IngestTaskItem(BaseModel):
    task_id: str
    doc_id: str
    status: str
    force_reindex: bool
    attempts: int
    max_attempts: int
    next_retry_at: datetime | None = None
    current_stage: str | None = None
    stage_metrics: dict[str, Any] = Field(default_factory=dict)
    last_error: str | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    last_result_status: str | None = None
    last_chunks_created: int = 0
    created_at: datetime
    updated_at: datetime


class IngestTaskRunRequest(BaseModel):
    limit: int = 20
    ignore_schedule: bool = False


class IngestTaskRunSummary(BaseModel):
    processed: int = 0
    success: int = 0
    retrying: int = 0
    dead: int = 0
    running: int = 0
