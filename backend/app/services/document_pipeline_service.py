from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter
from typing import Callable, TypeVar

from sqlalchemy import delete

from app.core.config import get_settings
from app.db.models import Chunk, Document
from app.models.schemas import DocumentIngestResponse
from app.services.chunker_service import Chunker
from app.services.cleaner_service import TextCleaner
from app.services.embedding_service import EmbeddingService
from app.services.metadata_service import MetadataExtractor
from app.services.parser_service import DocumentParser
from app.services.vector_store_service import VectorRecord, VectorStoreService

T = TypeVar("T")


class DocumentPipelineService:
    def __init__(
        self,
        session_factory,
        parser: DocumentParser,
        cleaner: TextCleaner,
        chunker: Chunker,
        metadata_extractor: MetadataExtractor,
        embedding_service: EmbeddingService,
        vector_store: VectorStoreService,
    ) -> None:
        self.session_factory = session_factory
        self.parser = parser
        self.cleaner = cleaner
        self.chunker = chunker
        self.metadata_extractor = metadata_extractor
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        self.settings = get_settings()
        self._last_stage_report: dict[str, dict[str, object]] = {}

    def ingest(self, doc_id: str, force_reindex: bool = False) -> DocumentIngestResponse:
        stage_metrics: dict[str, dict[str, object]] = {}
        self._last_stage_report = stage_metrics

        def run_stage(name: str, func: Callable[[], T]) -> T:
            started = perf_counter()
            try:
                result = func()
                stage_metrics[name] = {
                    "status": "success",
                    "duration_ms": int((perf_counter() - started) * 1000),
                }
                self._last_stage_report = stage_metrics
                return result
            except Exception as exc:
                stage_metrics[name] = {
                    "status": "failed",
                    "duration_ms": int((perf_counter() - started) * 1000),
                    "error": str(exc)[:500],
                }
                self._last_stage_report = stage_metrics
                raise

        with self.session_factory() as session:
            document = session.get(Document, doc_id)
            if not document:
                raise ValueError(f"document not found: {doc_id}")

            if not document.source_path:
                raise ValueError(f"document source_path is empty: {doc_id}")

            source_path = Path(document.source_path)
            if not source_path.exists():
                raise FileNotFoundError(f"source file not found: {source_path}")

            source_hash = run_stage("hash", lambda: self._md5(source_path))
            if (
                not force_reindex
                and document.source_hash == source_hash
                and document.ingest_status in {"indexed", "indexed_vector_failed"}
            ):
                return DocumentIngestResponse(
                    doc_id=doc_id,
                    chunks_created=document.chunks_count,
                    status="skipped",
                    vector_status="skipped",
                    stage_metrics=stage_metrics,
                )

            parsed = run_stage("parse", lambda: self.parser.parse(source_path))
            cleaned = run_stage("clean", lambda: self.cleaner.clean(parsed.text))
            if not cleaned.strip():
                raise ValueError(f"parsed content is empty: {doc_id}")

            meta = run_stage("metadata", lambda: self.metadata_extractor.extract(source_path, title=document.title, text=cleaned))
            run_stage("apply_metadata", lambda: self._apply_metadata(document, meta, parsed.ocr_used))

            if force_reindex or document.chunks_count > 0:
                session.execute(delete(Chunk).where(Chunk.doc_id == doc_id))
                run_stage("vector_delete", lambda: self.vector_store.delete_by_doc_id(doc_id))

            pieces = run_stage("chunk", lambda: self.chunker.chunk(cleaned))
            embeddings = run_stage("embedding", lambda: self.embedding_service.embed_texts([item.chunk_text for item in pieces]))

            vector_records: list[VectorRecord] = []
            for idx, piece in enumerate(pieces):
                chunk_id = f"{doc_id}-c{idx:04d}"
                vector_id = f"{doc_id}::{idx:04d}"
                embedding = embeddings[idx]

                session.add(
                    Chunk(
                        chunk_id=chunk_id,
                        doc_id=doc_id,
                        chapter=piece.chapter,
                        article_no=piece.article_no,
                        chunk_text=piece.chunk_text,
                        keywords_json=json.dumps(piece.keywords, ensure_ascii=False),
                        status=document.status,
                        embedding_model=self.embedding_service.current_embedding_model(),
                        vector_id=vector_id,
                    )
                )
                vector_records.append(
                    VectorRecord(
                        vector_id=vector_id,
                        doc_id=doc_id,
                        chunk_text=piece.chunk_text[:6000],
                        embedding=embedding,
                        region=document.region,
                        category=document.category,
                        status=document.status,
                        article_no=piece.article_no,
                    )
                )

            vector_status = "skipped"
            try:
                run_stage("vector_upsert", lambda: self.vector_store.upsert(vector_records))
                if vector_records:
                    vector_status = "indexed"
            except Exception:
                vector_status = "failed"

            document.source_hash = source_hash
            document.ingest_status = "indexed" if vector_status != "failed" else "indexed_vector_failed"
            document.chunks_count = len(pieces)
            document.last_ingested_at = datetime.now(timezone.utc)

            run_stage("database_commit", session.commit)

            return DocumentIngestResponse(
                doc_id=doc_id,
                chunks_created=len(pieces),
                status=document.ingest_status,
                vector_status=vector_status,
                stage_metrics=stage_metrics,
            )

    def _apply_metadata(self, document: Document, meta: dict[str, object], ocr_used: bool) -> None:
        document.source_org = str(meta.get("source_org") or document.source_org or "") or None
        document.document_number = str(meta.get("document_number") or document.document_number or "") or None
        document.region = str(meta.get("region") or document.region or "") or None
        document.category = str(meta.get("category") or document.category or "") or None
        document.status = str(meta.get("status") or document.status or "effective")
        document.status_evidence = str(meta.get("status_evidence") or "") or None
        publish_date = meta.get("publish_date")
        if publish_date and getattr(publish_date, "date", None):
            document.publish_date = publish_date.date()
        effective_date = meta.get("effective_date")
        if effective_date and getattr(effective_date, "date", None):
            document.effective_date = effective_date.date()
        expire_date = meta.get("expire_date")
        if expire_date and getattr(expire_date, "date", None):
            document.expire_date = expire_date.date()
        tags = meta.get("tags") or []
        document.tags_json = json.dumps(tags, ensure_ascii=False)
        document.metadata_evidence_json = str(meta.get("metadata_evidence_json") or "{}")
        document.ocr_needed = ocr_used

    def _md5(self, file_path: Path) -> str:
        md5 = hashlib.md5()
        with file_path.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                md5.update(chunk)
        return md5.hexdigest()

    def last_stage_report(self) -> dict[str, dict[str, object]]:
        return self._last_stage_report
