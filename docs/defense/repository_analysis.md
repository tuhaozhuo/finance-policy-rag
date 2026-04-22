# Repository Analysis for Defense

This document extracts factual information from the repository. It separates confirmed facts from reasonable inference and cites file paths for every major claim.

## A. Concise Project Summary

### Confirmed facts

This project implements a backend-first RAG system for financial regulation and policy documents. The repository states that it supports document parsing, metadata extraction, chunking, vector indexing, hybrid retrieval, RAG-based question answering, persistent QA history, favorites, health checks, metrics, and acceptance evaluation. Evidence: [README.md](../../README.md), [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py), [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py), [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py), [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py).

The backend is implemented with FastAPI. API routes are mounted under `/api/v1`. Evidence: [backend/app/main.py](../../backend/app/main.py), [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py).

The system uses MySQL-compatible SQL storage for documents, chunks, ingest tasks, QA records, QA citations, and favorites, and uses Milvus for vector storage when `VECTOR_BACKEND=milvus`. Evidence: [backend/app/db/models.py](../../backend/app/db/models.py), [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py), [deploy/docker-compose.yml](../../deploy/docker-compose.yml).

The code supports both hash embedding and API-based embedding. In API mode, it calls an OpenAI-compatible `/embeddings` endpoint and normalizes vectors. Evidence: [backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py), [backend/app/core/config.py](../../backend/app/core/config.py).

The generation component uses LangChain when available and falls back to raw HTTP calls to an OpenAI-compatible `/chat/completions` endpoint. Evidence: [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py).

### Reasonable inference

The practical problem is to make financial regulation documents searchable and answerable with citations, while preserving traceability to source articles. This is inferred from the implemented APIs, data models, and README descriptions. Evidence: [README.md](../../README.md), [backend/app/models/schemas.py](../../backend/app/models/schemas.py).

## B. Module-by-Module Breakdown

### 1. Application entrypoint

- [backend/app/main.py](../../backend/app/main.py): creates the FastAPI app, includes `api_router` under `/api/v1`, records request metrics through middleware, and initializes database tables on startup.
- [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py): registers endpoint modules for documents, search, QA, history, favorites, health, and metrics.

### 2. Configuration

- [backend/app/core/config.py](../../backend/app/core/config.py): defines runtime settings with Pydantic `BaseSettings`. It covers database, MySQL, Milvus, vector backend, embedding backend, Qwen and dev API profiles, LLM timeout, RAG context limits, vector index parameters, and OCR language.
- The config supports `runtime_profile` values `dev_api` and `prod_qwen`, and `embedding_backend` values `hash` and `api`. Evidence: [backend/app/core/config.py](../../backend/app/core/config.py).

### 3. Database models

- [backend/app/db/models.py](../../backend/app/db/models.py): defines SQLAlchemy models:
  - `Document`
  - `Chunk`
  - `IngestTask`
  - `QARecord`
  - `QACitation`
  - `Favorite`
- [backend/app/db/session.py](../../backend/app/db/session.py): creates SQLAlchemy engine/session and initializes tables.

### 4. Document ingestion

- [backend/app/api/v1/endpoints/documents.py](../../backend/app/api/v1/endpoints/documents.py): exposes document upload, direct ingest, document listing, tag management, and ingest task APIs.
- [backend/app/services/document_service.py](../../backend/app/services/document_service.py): creates uploaded document records and handles document/tag listing.
- [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py): orchestrates ingestion stages: hash, parse, clean, metadata extraction, metadata application, vector deletion, chunking, embedding, vector upsert, database commit.
- [backend/app/services/ingest_task_service.py](../../backend/app/services/ingest_task_service.py): manages ingest task queue, retries, dead state, atomic task claim, and stage metrics.

### 5. Parsing, OCR, cleaning, chunking, metadata

- [backend/app/services/parser_service.py](../../backend/app/services/parser_service.py): parses `.docx`, `.pdf`, `.doc`, image files, and plain text. `.doc` uses `antiword`, `catdoc`, and `textutil` fallback.
- [backend/app/services/ocr_service.py](../../backend/app/services/ocr_service.py): uses `pytesseract` and Pillow for image OCR.
- [backend/app/services/cleaner_service.py](../../backend/app/services/cleaner_service.py): normalizes text whitespace and repeated blank lines.
- [backend/app/services/chunker_service.py](../../backend/app/services/chunker_service.py): chunks documents by Chinese legal article patterns like `第X条`; if no article chunks exist, it falls back to fixed character windows with overlap.
- [backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py): extracts metadata such as source organization, document number, dates, status, region, category, and status evidence.

### 6. Embedding and vector database

- [backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py): supports API embedding and hash embedding. API embedding deduplicates input texts, batches requests, sorts returned vectors by index, normalizes dimensions and vector norms, and raises error if API embedding fails in API mode.
- [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py): creates and uses a Milvus collection with fields `vector_id`, `doc_id`, `chunk_text`, `region`, `category`, `status`, `article_no`, and `embedding`.
- The Milvus index is `IVF_FLAT` with `COSINE` metric. Evidence: [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py).
- ANN appears in the repository as Milvus vector search over the `embedding` field, using `nprobe` search parameters. Evidence: [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py), [backend/app/core/config.py](../../backend/app/core/config.py).

### 7. Retrieval and reranking

- [backend/app/api/v1/endpoints/search.py](../../backend/app/api/v1/endpoints/search.py): exposes `/search` and `/search/related`.
- [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py): implements hybrid retrieval:
  - structured filtering by status, region, source organization, and category;
  - keyword recall with exact query matching and token matching;
  - BM25-like keyword scoring;
  - vector recall through `EmbeddingService` and `VectorStoreService`;
  - merging keyword and vector candidates by chunk ID;
  - final reranking.
- [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py): combines keyword score, vector score, status bonus, and hybrid bonus into final score.
- `/search/related` expands from anchors using same-document neighbors, same article numbers, and keyword expansion. Evidence: [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py).

### 8. Generation and confidence scoring

- [backend/app/api/v1/endpoints/qa.py](../../backend/app/api/v1/endpoints/qa.py): searches evidence first, handles effective vs expired fallback, calls `RAGService`, and records QA history.
- [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py): generates answers from citations, handles no-evidence cases, computes consistency score, evidence coverage, and confidence score.
- [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py): constructs prompt context from retrieved chunks, limits context size, calls LangChain or raw HTTP, and returns explicit degraded status when LLM is unavailable.
- [backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py): scores answer-citation token overlap.
- [backend/app/services/interaction_service.py](../../backend/app/services/interaction_service.py): persists QA records, citations, history, and favorites.

### 9. Evaluation, reports, and tests

- [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py): evaluates `/search`, `/qa`, `/search/related`, timeliness questions, and OCR questions using expected keyword hits, latency, success rate, accuracy, and recall.
- [data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json): contains fixed evaluation cases.
- [docs/reports/acceptance_eval.md](../../docs/reports/acceptance_eval.md) and [docs/reports/acceptance_eval.json](../../docs/reports/acceptance_eval.json): contain a recorded acceptance evaluation output.
- [scripts/benchmark_api.py](../../scripts/benchmark_api.py): benchmarks API latency for search, QA, and related search.
- [backend/tests](../../backend/tests): contains unit and contract tests for API routes, config profiles, embedding service, health endpoint, LLM service, ingest task service, and vector store service.

## C. Evidence List with File Paths

- Problem and scope: [README.md](../../README.md)
- FastAPI app and middleware: [backend/app/main.py](../../backend/app/main.py)
- API registration: [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py)
- Document APIs: [backend/app/api/v1/endpoints/documents.py](../../backend/app/api/v1/endpoints/documents.py)
- Search APIs: [backend/app/api/v1/endpoints/search.py](../../backend/app/api/v1/endpoints/search.py)
- QA API: [backend/app/api/v1/endpoints/qa.py](../../backend/app/api/v1/endpoints/qa.py)
- Health API: [backend/app/api/v1/endpoints/health.py](../../backend/app/api/v1/endpoints/health.py)
- Metrics API: [backend/app/api/v1/endpoints/metrics.py](../../backend/app/api/v1/endpoints/metrics.py)
- Runtime configuration: [backend/app/core/config.py](../../backend/app/core/config.py)
- Metrics storage: [backend/app/core/metrics.py](../../backend/app/core/metrics.py)
- Database schema: [backend/app/db/models.py](../../backend/app/db/models.py)
- DB session and init: [backend/app/db/session.py](../../backend/app/db/session.py)
- Ingestion pipeline: [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py)
- Parser: [backend/app/services/parser_service.py](../../backend/app/services/parser_service.py)
- OCR: [backend/app/services/ocr_service.py](../../backend/app/services/ocr_service.py)
- Chunking: [backend/app/services/chunker_service.py](../../backend/app/services/chunker_service.py)
- Metadata extraction: [backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py)
- Embedding: [backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py)
- Vector database: [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)
- Retriever: [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)
- Reranker: [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py)
- RAG answer generation: [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)
- LLM prompt and generation: [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py)
- Answer consistency scoring: [backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py)
- Persistence of QA/favorites/history: [backend/app/services/interaction_service.py](../../backend/app/services/interaction_service.py)
- Docker deployment: [deploy/docker-compose.yml](../../deploy/docker-compose.yml), [deploy/backend.Dockerfile](../../deploy/backend.Dockerfile)
- Acceptance evaluation: [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py), [data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json), [docs/reports/acceptance_eval.md](../../docs/reports/acceptance_eval.md)
- API benchmark: [scripts/benchmark_api.py](../../scripts/benchmark_api.py)
- Tests: [backend/tests](../../backend/tests)

## D. Possible Presentation Angles for Defense PPT

### Angle 1: Engineering RAG pipeline for regulation documents

Focus on the full backend chain from ingestion to answer generation, emphasizing reliable data processing, persistence, and traceability. Evidence: [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py), [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py).

### Angle 2: Hybrid retrieval for Chinese regulatory text

Focus on dense retrieval plus keyword/BM25-like retrieval, candidate merging, and reranking. This is technically defensible because the retrieval code is explicit. Evidence: [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py), [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py).

### Angle 3: Evidence-grounded QA with confidence signals

Focus on answer generation from citations, no-evidence handling, degraded LLM status, confidence score, consistency score, and evidence coverage. Evidence: [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py), [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py), [backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py).

### Angle 4: Domain-oriented metadata and timeliness

Focus on extracting and using document metadata such as status, date, document number, source organization, region, and category. Evidence: [backend/app/db/models.py](../../backend/app/db/models.py), [backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py), [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py).

### Angle 5: Practical deployability and observability

Focus on Docker Compose, health checks, metrics, ingest task status, evaluation scripts, and test coverage. Evidence: [deploy/docker-compose.yml](../../deploy/docker-compose.yml), [backend/app/api/v1/endpoints/health.py](../../backend/app/api/v1/endpoints/health.py), [backend/app/api/v1/endpoints/metrics.py](../../backend/app/api/v1/endpoints/metrics.py), [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py), [backend/tests](../../backend/tests).

## E. Uncertainties and Evidence Gaps

- The repository does not include a frontend implementation. This is confirmed by the absence of frontend source directories and the README stating backend-first scope. Evidence: [README.md](../../README.md).
- The repository does not include a manually labeled gold chunk retrieval benchmark. The acceptance evaluation uses expected keyword matching rather than gold document or gold chunk labels. Evidence: [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py), [data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json).
- The repository does not include authentication or authorization middleware. Routes are exposed without user authentication checks. Evidence: [backend/app/api/v1/endpoints](../../backend/app/api/v1/endpoints).
- The repository does not include raw regulatory documents. The raw data directory is ignored by [.gitignore](../../.gitignore).
- The repository does not provide ablation experiments comparing keyword-only, vector-only, and hybrid retrieval. The reranking formula exists, but no ablation result file is present. Evidence: [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py), [docs/reports](../../docs/reports).
- The repository does not prove production-scale performance. The available reports are fixed acceptance and benchmark scripts, not large-scale load tests. Evidence: [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py), [scripts/benchmark_api.py](../../scripts/benchmark_api.py).
