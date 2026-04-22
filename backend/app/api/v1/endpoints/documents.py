from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile

from app.dependencies import get_document_pipeline, get_document_service, get_ingest_task_service
from app.models.schemas import (
    APIResponse,
    DocumentIngestRequest,
    DocumentTagsUpdateRequest,
    DocumentUploadResponse,
    IngestTaskCreateRequest,
    IngestTaskRunRequest,
)
from app.services.document_pipeline_service import DocumentPipelineService
from app.services.document_service import DocumentService
from app.services.ingest_task_service import IngestTaskService

router = APIRouter(prefix="/documents", tags=["documents"])

RAW_DATA_DIR = Path("data/raw")


@router.post("/upload", response_model=APIResponse)
async def upload_document(
    file: UploadFile = File(...),
    document_service: DocumentService = Depends(get_document_service),
) -> APIResponse:
    RAW_DATA_DIR.mkdir(parents=True, exist_ok=True)
    suffix = file.filename.split(".")[-1].lower() if file.filename else "unknown"
    safe_name = Path(file.filename or f"unknown.{suffix}").name
    doc_id = f"doc-{uuid4().hex[:10]}"
    output_path = RAW_DATA_DIR / f"{doc_id}_{safe_name}"

    content = await file.read()
    output_path.write_bytes(content)

    doc = document_service.create_uploaded_document(file_path=output_path, filename=safe_name, file_type=suffix, doc_id=doc_id)
    return APIResponse(data=DocumentUploadResponse(doc_id=doc.doc_id, filename=safe_name, stored_path=output_path.as_posix()))


@router.post("/ingest", response_model=APIResponse)
def ingest_document(
    request: DocumentIngestRequest,
    pipeline: DocumentPipelineService = Depends(get_document_pipeline),
) -> APIResponse:
    try:
        result = pipeline.ingest(doc_id=request.doc_id, force_reindex=request.force_reindex)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return APIResponse(data=result)


@router.get("", response_model=APIResponse)
def list_documents(document_service: DocumentService = Depends(get_document_service)) -> APIResponse:
    return APIResponse(data=document_service.list_documents())


@router.get("/tags", response_model=APIResponse)
def list_tags(document_service: DocumentService = Depends(get_document_service)) -> APIResponse:
    return APIResponse(data=document_service.list_tags())

@router.post("/ingest/tasks", response_model=APIResponse)
def create_ingest_tasks(
    request: IngestTaskCreateRequest,
    task_service: IngestTaskService = Depends(get_ingest_task_service),
) -> APIResponse:
    if not request.doc_ids:
        raise HTTPException(status_code=400, detail="doc_ids cannot be empty")

    tasks = task_service.enqueue_tasks(
        doc_ids=request.doc_ids,
        force_reindex=request.force_reindex,
        max_attempts=request.max_attempts,
    )
    return APIResponse(data={"created_count": len(tasks), "tasks": tasks})


@router.get("/ingest/tasks", response_model=APIResponse)
def list_ingest_tasks(
    status: str | None = None,
    limit: int = 100,
    task_service: IngestTaskService = Depends(get_ingest_task_service),
) -> APIResponse:
    return APIResponse(data=task_service.list_tasks(status=status, limit=limit))


@router.post("/ingest/tasks/run", response_model=APIResponse)
def run_ingest_tasks(
    request: IngestTaskRunRequest,
    task_service: IngestTaskService = Depends(get_ingest_task_service),
) -> APIResponse:
    summary = task_service.run_due_tasks(limit=request.limit, ignore_schedule=request.ignore_schedule)
    return APIResponse(data=summary)


@router.patch("/{doc_id}/tags", response_model=APIResponse)
def update_document_tags(
    doc_id: str,
    request: DocumentTagsUpdateRequest,
    document_service: DocumentService = Depends(get_document_service),
) -> APIResponse:
    try:
        data = document_service.update_document_tags(doc_id=doc_id, tags=request.tags)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return APIResponse(data=data)


@router.get("/{doc_id}", response_model=APIResponse)
def get_document(doc_id: str, document_service: DocumentService = Depends(get_document_service)) -> APIResponse:
    item = document_service.get_document(doc_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"document not found: {doc_id}")
    return APIResponse(data=item)
