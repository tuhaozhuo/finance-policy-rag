from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.db.models import IngestTask
from app.models.schemas import DocumentIngestResponse, IngestTaskRunSummary
from app.services.ingest_task_service import IngestTaskService


class _Pipeline:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def ingest(self, doc_id: str, force_reindex: bool = False) -> DocumentIngestResponse:
        self.calls.append(doc_id)
        return DocumentIngestResponse(
            doc_id=doc_id,
            chunks_created=1,
            status="indexed",
            vector_status="indexed",
            stage_metrics={},
        )

    def last_stage_report(self) -> dict[str, dict[str, object]]:
        return {}


def _session_factory():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine, autocommit=False, autoflush=False, expire_on_commit=False)


def test_claim_task_prevents_duplicate_running_claim() -> None:
    session_factory = _session_factory()
    pipeline = _Pipeline()
    service = IngestTaskService(session_factory=session_factory, pipeline=pipeline)  # type: ignore[arg-type]

    with session_factory() as session:
        session.add(
            IngestTask(
                task_id="task-1",
                doc_id="doc-1",
                status="pending",
                force_reindex=True,
                attempts=0,
                max_attempts=3,
            )
        )
        session.commit()

    now = datetime.now(timezone.utc)
    first = service._claim_task("task-1", now=now, ignore_schedule=True)  # noqa: SLF001
    second = service._claim_task("task-1", now=now, ignore_schedule=True)  # noqa: SLF001

    assert first == ("doc-1", True)
    assert second is None

    with session_factory() as session:
        task = session.get(IngestTask, "task-1")
        assert task is not None
        assert task.status == "running"
        assert task.attempts == 1


def test_run_due_tasks_counts_only_claimed_tasks() -> None:
    session_factory = _session_factory()
    pipeline = _Pipeline()
    service = IngestTaskService(session_factory=session_factory, pipeline=pipeline)  # type: ignore[arg-type]

    with session_factory() as session:
        session.add(
            IngestTask(
                task_id="task-1",
                doc_id="doc-1",
                status="running",
                force_reindex=False,
                attempts=1,
                max_attempts=3,
            )
        )
        session.commit()

    summary = IngestTaskRunSummary()
    service._run_single_task("task-1", summary, ignore_schedule=True)  # noqa: SLF001

    assert summary.processed == 0
    assert pipeline.calls == []
