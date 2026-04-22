from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

from sqlalchemy import select

from app.db.models import Document
from app.models.schemas import DocumentItem, TagSummaryItem


class DocumentService:
    def __init__(self, session_factory) -> None:
        self.session_factory = session_factory

    def create_uploaded_document(self, file_path: Path, filename: str, file_type: str, doc_id: str | None = None) -> DocumentItem:
        doc_id = doc_id or f"doc-{uuid4().hex[:10]}"

        with self.session_factory() as session:
            record = Document(
                doc_id=doc_id,
                title=filename,
                file_type=file_type,
                source_path=file_path.as_posix(),
                status="effective",
                tags_json="[]",
                ingest_status="uploaded",
                chunks_count=0,
            )
            session.add(record)
            session.commit()
            session.refresh(record)
            return self._to_schema(record)

    def list_documents(self) -> list[DocumentItem]:
        with self.session_factory() as session:
            rows = session.execute(select(Document).order_by(Document.created_at.desc())).scalars().all()
            return [self._to_schema(item) for item in rows]

    def get_document(self, doc_id: str) -> DocumentItem | None:
        with self.session_factory() as session:
            record = session.get(Document, doc_id)
            return self._to_schema(record) if record else None

    def update_document_tags(self, doc_id: str, tags: list[str]) -> DocumentItem:
        normalized = self._normalize_tags(tags)

        with self.session_factory() as session:
            record = session.get(Document, doc_id)
            if record is None:
                raise ValueError(f"document not found: {doc_id}")

            record.tags_json = json.dumps(normalized, ensure_ascii=False)
            session.commit()
            session.refresh(record)
            return self._to_schema(record)

    def list_tags(self) -> list[TagSummaryItem]:
        counter: dict[str, int] = {}
        with self.session_factory() as session:
            rows = session.execute(select(Document.tags_json)).scalars().all()

        for raw in rows:
            if not raw:
                continue
            try:
                tags = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if not isinstance(tags, list):
                continue

            for item in tags:
                if not isinstance(item, str):
                    continue
                tag = item.strip()
                if not tag:
                    continue
                counter[tag] = counter.get(tag, 0) + 1

        ordered = sorted(counter.items(), key=lambda x: (-x[1], x[0]))
        return [TagSummaryItem(tag=tag, count=count) for tag, count in ordered]

    def _to_schema(self, row: Document) -> DocumentItem:
        tags = []
        try:
            tags = json.loads(row.tags_json or "[]")
        except json.JSONDecodeError:
            tags = []

        return DocumentItem(
            doc_id=row.doc_id,
            title=row.title,
            source_org=row.source_org,
            document_number=row.document_number,
            region=row.region,
            category=row.category,
            publish_date=row.publish_date,
            effective_date=row.effective_date,
            expire_date=row.expire_date,
            status=row.status,
            status_evidence=row.status_evidence,
            file_type=row.file_type,
            source_path=row.source_path,
            source_url=row.source_url,
            ocr_needed=row.ocr_needed,
            tags=tags,
            metadata_evidence=self._load_metadata_evidence(row.metadata_evidence_json),
            ingest_status=row.ingest_status,
            chunks_count=row.chunks_count,
            last_ingested_at=row.last_ingested_at,
            created_at=row.created_at,
        )

    def _normalize_tags(self, tags: list[str]) -> list[str]:
        clean: list[str] = []
        seen: set[str] = set()
        for item in tags:
            tag = item.strip()
            if not tag or tag in seen:
                continue
            seen.add(tag)
            clean.append(tag)
            if len(clean) >= 30:
                break
        return clean

    def _load_metadata_evidence(self, raw: str | None) -> dict[str, object]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}
