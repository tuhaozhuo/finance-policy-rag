#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
sys.path.insert(0, str(BACKEND_DIR))

from app.db.models import Document, IngestTask  # noqa: E402
from app.db.session import get_session_factory, init_db  # noqa: E402
from app.dependencies import get_ingest_task_service  # noqa: E402


def stable_doc_id(file_path: Path) -> str:
    digest = hashlib.md5(file_path.as_posix().encode("utf-8")).hexdigest()[:12]
    return f"doc-{digest}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Batch ingest finance policy files")
    parser.add_argument("--root", default="金融监督管理局", help="root folder for source files")
    parser.add_argument("--limit", type=int, default=0, help="max files, 0 means no limit")
    parser.add_argument("--force", action="store_true", help="force reindex")
    parser.add_argument("--max-attempts", type=int, default=3, help="max retry attempts for each task")
    args = parser.parse_args()

    source_root = (ROOT / args.root).resolve()
    if not source_root.exists():
        raise SystemExit(f"source root not found: {source_root}")

    init_db()
    session_factory = get_session_factory()

    suffixes = {".doc", ".docx", ".pdf", ".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff"}
    files = [p for p in source_root.rglob("*") if p.is_file() and p.suffix.lower() in suffixes]
    files.sort()
    if args.limit > 0:
        files = files[: args.limit]

    with session_factory() as session:
        for file_path in files:
            doc_id = stable_doc_id(file_path)
            item = session.get(Document, doc_id)
            if item is None:
                item = Document(
                    doc_id=doc_id,
                    title=file_path.name,
                    file_type=file_path.suffix.lower().lstrip("."),
                    source_path=file_path.as_posix(),
                    status="effective",
                    tags_json="[]",
                    ingest_status="uploaded",
                    chunks_count=0,
                )
                session.add(item)
            else:
                item.title = file_path.name
                item.file_type = file_path.suffix.lower().lstrip(".")
                item.source_path = file_path.as_posix()
            session.flush()

        session.commit()

    task_service = get_ingest_task_service()
    doc_ids = [stable_doc_id(item) for item in files]
    created = task_service.enqueue_tasks(
        doc_ids=doc_ids,
        force_reindex=args.force,
        max_attempts=args.max_attempts,
    )
    created_ids = {item.task_id for item in created}
    print(f"enqueued: {len(created)}")

    rounds = 0
    while True:
        rounds += 1
        summary = task_service.run_due_tasks(limit=200, ignore_schedule=True)
        if summary.processed == 0:
            break
        print(
            f"round={rounds} processed={summary.processed} "
            f"success={summary.success} retrying={summary.retrying} dead={summary.dead}"
        )

    with session_factory() as session:
        tasks = session.query(IngestTask).filter(IngestTask.task_id.in_(created_ids)).all()

    success = [item for item in tasks if item.status == "success"]
    retrying = [item for item in tasks if item.status == "retrying"]
    pending = [item for item in tasks if item.status == "pending"]
    dead = [item for item in tasks if item.status == "dead"]

    for item in dead:
        print(f"[DEAD] {item.doc_id} attempts={item.attempts}/{item.max_attempts} error={item.last_error}")

    print(
        f"done: total={len(files)} success={len(success)} "
        f"retrying={len(retrying)} pending={len(pending)} dead={len(dead)}"
    )


if __name__ == "__main__":
    main()
