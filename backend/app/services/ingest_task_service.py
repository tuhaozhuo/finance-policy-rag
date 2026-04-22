from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from sqlalchemy import Select, and_, or_, select, update

from app.db.models import IngestTask
from app.models.schemas import IngestTaskItem, IngestTaskRunSummary
from app.services.document_pipeline_service import DocumentPipelineService


class IngestTaskService:
    def __init__(self, session_factory, pipeline: DocumentPipelineService) -> None:
        self.session_factory = session_factory
        self.pipeline = pipeline

    def enqueue_tasks(self, doc_ids: list[str], force_reindex: bool = False, max_attempts: int = 3) -> list[IngestTaskItem]:
        if max_attempts < 1:
            max_attempts = 1

        created: list[IngestTaskItem] = []
        with self.session_factory() as session:
            for doc_id in doc_ids:
                task = IngestTask(
                    task_id=f"task-{uuid4().hex[:12]}",
                    doc_id=doc_id,
                    status="pending",
                    force_reindex=force_reindex,
                    attempts=0,
                    max_attempts=max_attempts,
                    next_retry_at=None,
                )
                session.add(task)
                session.flush()
                created.append(self._to_schema(task))
            session.commit()

        return created

    def list_tasks(self, status: str | None = None, limit: int = 100) -> list[IngestTaskItem]:
        with self.session_factory() as session:
            statement: Select = select(IngestTask).order_by(IngestTask.created_at.desc()).limit(max(1, min(limit, 500)))
            if status:
                statement = statement.where(IngestTask.status == status)

            rows = session.execute(statement).scalars().all()
            return [self._to_schema(item) for item in rows]

    def run_due_tasks(self, limit: int = 20, ignore_schedule: bool = False) -> IngestTaskRunSummary:
        now = datetime.now(timezone.utc)
        summary = IngestTaskRunSummary()

        with self.session_factory() as session:
            status_filter = IngestTask.status.in_(["pending", "retrying"])
            if ignore_schedule:
                ready_filter = status_filter
            else:
                ready_filter = and_(status_filter, or_(IngestTask.next_retry_at.is_(None), IngestTask.next_retry_at <= now))

            statement = (
                select(IngestTask)
                .where(ready_filter)
                .order_by(IngestTask.created_at.asc())
                .limit(max(1, min(limit, 500)))
            )
            tasks = session.execute(statement).scalars().all()

        for task in tasks:
            self._run_single_task(task.task_id, summary, ignore_schedule=ignore_schedule)

        return summary

    def _run_single_task(self, task_id: str, summary: IngestTaskRunSummary, ignore_schedule: bool = False) -> None:
        now = datetime.now(timezone.utc)
        claimed = self._claim_task(task_id=task_id, now=now, ignore_schedule=ignore_schedule)
        if claimed is None:
            return
        doc_id, force_reindex = claimed
        summary.processed += 1

        try:
            result = self.pipeline.ingest(doc_id=doc_id, force_reindex=force_reindex)
            with self.session_factory() as session:
                task = session.get(IngestTask, task_id)
                if task is None:
                    return
                task.status = "success"
                task.current_stage = "completed"
                task.stage_metrics_json = json.dumps(result.stage_metrics, ensure_ascii=False)
                task.last_result_status = result.status
                task.last_chunks_created = result.chunks_created
                task.last_finished_at = datetime.now(timezone.utc)
                task.next_retry_at = None
                task.last_error = None
                session.commit()
            summary.success += 1
            return
        except Exception as exc:
            with self.session_factory() as session:
                task = session.get(IngestTask, task_id)
                if task is None:
                    return

                task.last_error = str(exc)[:1000]
                task.stage_metrics_json = json.dumps(self.pipeline.last_stage_report(), ensure_ascii=False)
                task.current_stage = self._last_stage_name()
                task.last_finished_at = datetime.now(timezone.utc)
                if task.attempts >= task.max_attempts:
                    task.status = "dead"
                    task.next_retry_at = None
                    summary.dead += 1
                else:
                    task.status = "retrying"
                    backoff_seconds = min(300, 5 * (2 ** (task.attempts - 1)))
                    task.next_retry_at = datetime.now(timezone.utc) + timedelta(seconds=backoff_seconds)
                    summary.retrying += 1
                session.commit()

    def _claim_task(self, task_id: str, now: datetime, ignore_schedule: bool = False) -> tuple[str, bool] | None:
        with self.session_factory() as session:
            ready_filter = IngestTask.status.in_(["pending", "retrying"])
            if not ignore_schedule:
                ready_filter = and_(ready_filter, or_(IngestTask.next_retry_at.is_(None), IngestTask.next_retry_at <= now))

            result = session.execute(
                update(IngestTask)
                .where(IngestTask.task_id == task_id, ready_filter)
                .values(
                    status="running",
                    current_stage="running",
                    attempts=IngestTask.attempts + 1,
                    last_started_at=now,
                    last_error=None,
                )
            )
            if result.rowcount != 1:
                session.rollback()
                return None

            task = session.get(IngestTask, task_id)
            if task is None:
                session.rollback()
                return None
            doc_id = task.doc_id
            force_reindex = task.force_reindex
            session.commit()
            return doc_id, force_reindex

    def _to_schema(self, row: IngestTask) -> IngestTaskItem:
        return IngestTaskItem(
            task_id=row.task_id,
            doc_id=row.doc_id,
            status=row.status,
            force_reindex=row.force_reindex,
            attempts=row.attempts,
            max_attempts=row.max_attempts,
            next_retry_at=row.next_retry_at,
            current_stage=row.current_stage,
            stage_metrics=self._load_stage_metrics(row.stage_metrics_json),
            last_error=row.last_error,
            last_started_at=row.last_started_at,
            last_finished_at=row.last_finished_at,
            last_result_status=row.last_result_status,
            last_chunks_created=row.last_chunks_created,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _load_stage_metrics(self, raw: str | None) -> dict[str, object]:
        if not raw:
            return {}
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            return {}
        return data if isinstance(data, dict) else {}

    def _last_stage_name(self) -> str | None:
        report = self.pipeline.last_stage_report()
        if not report:
            return None
        return next(reversed(report.keys()))
