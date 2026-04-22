# Defense PPT Design

This deck is designed for an academic or project defense. It stays aligned with the repository and avoids unsupported benchmark or research claims.

## Slide 1. Title and System Scope

**Purpose of this slide**

Introduce the project and set the scope: backend RAG system for financial regulation documents.

**Key bullet points**

- Project: Financial Policy RAG Question Answering System.
- Scope: backend-first system for document ingestion, retrieval, answer generation, citation, and evaluation.
- Data types supported by code: `doc`, `docx`, `pdf`, images, and plain text.
- Frontend and authentication are not implemented in the current repository.

**Suggested figure or diagram**

A simple title slide with a pipeline icon: documents -> RAG backend -> cited answer.

**What I should say verbally in 30 to 60 seconds**

This project builds a backend RAG system for financial regulation documents. The goal is not to replace legal or compliance experts, but to help users search policy documents and generate answers with explicit evidence. The current repository focuses on the backend pipeline: document ingestion, chunking, embedding, Milvus vector indexing, hybrid retrieval, LLM-based answer generation, citation output, QA persistence, health checks, and evaluation scripts.

**Likely questions from examiners**

- Is this a complete product?
- Where is the frontend?

**Best answer**

It is a backend acceptance version. The frontend and authentication are explicitly left as future work. The implemented part is the data and RAG backend, which is the technical core of the project.

## Slide 2. Problem Definition

**Purpose of this slide**

Define the concrete technical problem.

**Key bullet points**

- Financial regulation documents are long, semi-structured, and frequently updated.
- Plain keyword search may miss semantic matches.
- LLM-only answers may hallucinate or ignore document validity.
- The system needs retrieval, citation, timeliness handling, and operational reliability.

**Suggested figure or diagram**

A problem diagram: document complexity -> retrieval difficulty -> need for evidence-grounded QA.

**What I should say verbally in 30 to 60 seconds**

The problem is to answer questions over financial regulation documents while keeping answers grounded in source text. These documents often contain numbered articles, dates, issuing agencies, and validity information. A pure LLM approach is risky because it may generate unsupported answers. A pure keyword search is also limited because user questions may not use the exact same wording as the document. Therefore, this project uses RAG to combine retrieval, citation, and controlled generation.

**Likely questions from examiners**

- Why not just use full-text search?
- Why not upload everything to an LLM context?

**Best answer**

Full-text search is precise but weak for semantic questions. Uploading all documents to the LLM is not scalable and increases hallucination and cost. RAG retrieves a smaller evidence set first, then constrains generation to that evidence.

## Slide 3. Why RAG

**Purpose of this slide**

Explain motivation for RAG over pure LLM or pure search.

**Key bullet points**

- Retrieval narrows context and reduces token cost.
- Citations make answers auditable.
- Structured filters support status, region, category, and source organization.
- Generation is based on retrieved chunks, not free-form memory.

**Suggested figure or diagram**

Comparison table: keyword search vs LLM-only vs RAG.

**What I should say verbally in 30 to 60 seconds**

RAG is appropriate here because the answer must be tied to authoritative text. The repository implements a retrieval-first QA flow: `/qa` calls the retriever, receives citations, and then calls the RAG service to generate an answer. The LLM prompt explicitly says that answers should only be based on given articles and should state uncertainty when evidence is insufficient. This design supports traceability and reduces uncontrolled generation.

**Likely questions from examiners**

- Does RAG eliminate hallucination?

**Best answer**

No. RAG reduces hallucination risk but does not eliminate it. That is why the system returns citations, confidence score, consistency score, evidence coverage, and degraded status when the LLM is unavailable.

## Slide 4. Overall Architecture

**Purpose of this slide**

Show the end-to-end architecture.

**Key bullet points**

- FastAPI provides `/api/v1` routes.
- MySQL stores structured metadata, chunks, tasks, QA records, citations, and favorites.
- Milvus stores dense vectors and metadata fields.
- Qwen/OpenAI-compatible APIs provide embedding and chat generation.
- Docker Compose provides MySQL, Milvus, etcd, and MinIO.

**Suggested figure or diagram**

Architecture flow:

`Files -> Parser/OCR -> Chunker -> Embedding -> MySQL + Milvus -> Retriever -> LLM -> Answer`

**What I should say verbally in 30 to 60 seconds**

The architecture separates structured storage and vector storage. MySQL stores documents, chunks, ingestion tasks, QA history, and citations. Milvus stores vector embeddings for chunk-level semantic retrieval. FastAPI exposes document, search, QA, health, and metrics APIs. Embedding and LLM generation are accessed through OpenAI-compatible endpoints. This separation makes the system easier to debug: metadata and exact text stay in MySQL, while approximate vector search is handled by Milvus.

**Likely questions from examiners**

- Why use both MySQL and Milvus?

**Best answer**

MySQL is better for structured metadata, status, task state, and persistent history. Milvus is designed for vector similarity search and ANN-style retrieval. The system uses both because they solve different parts of the problem.

## Slide 5. Document Ingestion Pipeline

**Purpose of this slide**

Explain how documents become searchable knowledge.

**Key bullet points**

- File upload creates `Document` records.
- Parser supports `.docx`, `.pdf`, `.doc`, images, and plain text.
- OCR uses Tesseract through `pytesseract`.
- Pipeline stages: hash, parse, clean, metadata, chunk, embedding, vector upsert, commit.
- Ingest task records status, retry count, stage metrics, and errors.

**Suggested figure or diagram**

Sequence diagram from upload to chunks and vectors.

**What I should say verbally in 30 to 60 seconds**

The ingestion pipeline is implemented in `DocumentPipelineService`. It first checks the source file, calculates a hash, parses the document, cleans the text, extracts metadata, chunks the text, calls embedding, writes chunks to MySQL, and upserts vectors into Milvus. Each stage is wrapped with timing and error reporting. This is important because document parsing and embedding are failure-prone, so the system needs observable task states rather than a black-box import script.

**Likely questions from examiners**

- How does the system handle failed imports?

**Best answer**

Ingest tasks have `pending`, `running`, `retrying`, `success`, and `dead` states. Failed stages record error messages and stage metrics. The task service supports retry and max attempts.

## Slide 6. Chunking Strategy

**Purpose of this slide**

Highlight where chunking appears and why it matters.

**Key bullet points**

- Article-first chunking: detects `第X条`.
- Chapter detection: detects `第X章`.
- Fallback window chunking: `max_chars=500`, `overlap=80`.
- Chunk metadata includes chapter, article number, keywords, status, vector ID.
- Trade-off: smaller chunks improve retrieval precision, but may lose context.

**Suggested figure or diagram**

A sample regulation text split into article chunks.

**What I should say verbally in 30 to 60 seconds**

Chunking is domain-aware in a simple way. For regulation-like documents, article boundaries are meaningful, so the system first tries to split by `第X条`. If a document does not contain article patterns, it falls back to sliding windows. This is a practical trade-off: article chunks preserve legal structure, while fallback windows keep the system usable for less structured files.

**Likely questions from examiners**

- Why not use semantic chunking?

**Best answer**

Semantic chunking could improve context boundaries, but article-based chunking is more explainable for regulation documents. The current system prioritizes deterministic and auditable chunks. Semantic chunking can be added later.

## Slide 7. Embedding and Vector Index

**Purpose of this slide**

Explicitly show embedding, vector search, and ANN/index details.

**Key bullet points**

- Embedding service supports API embedding and hash embedding.
- API embedding batches and deduplicates texts.
- Vectors are normalized and dimension-adjusted.
- Milvus collection: `finance_policy_chunks`.
- Index: `IVF_FLAT` with `COSINE` metric.
- Search uses Milvus `nprobe` parameter.

**Suggested figure or diagram**

Chunk text -> embedding vector -> Milvus IVF_FLAT/COSINE index.

**What I should say verbally in 30 to 60 seconds**

Dense retrieval is implemented through the embedding service and Milvus. During ingestion, each chunk is converted into an embedding and stored in Milvus with its metadata. During search, the query is embedded and used to search the Milvus collection. The vector store creates an `IVF_FLAT` index with cosine similarity, and the search parameter `nprobe` is configurable. This is the ANN/vector search component of the system.

**Likely questions from examiners**

- Is IVF_FLAT an approximate nearest neighbor index?

**Best answer**

In Milvus, IVF-style indexes partition the vector space and search selected partitions using parameters such as `nprobe`. In this system, `IVF_FLAT` with `COSINE` is configured in the vector store. The repository does not include experiments comparing different index types.

## Slide 8. Hybrid Retrieval Pipeline

**Purpose of this slide**

Explain retrieval design in technical detail.

**Key bullet points**

- Structured filters: status, region, source organization, category.
- Keyword recall: exact query and token-based SQL contains.
- BM25-like scoring over merged candidates.
- Vector recall: query embedding + Milvus search.
- Candidate merge by chunk ID.
- Result includes candidate counts and retrieval source.

**Suggested figure or diagram**

Parallel retrieval branches:

`Query -> keyword branch`

`Query -> embedding -> vector branch`

Then merge and rerank.

**What I should say verbally in 30 to 60 seconds**

The retriever uses both sparse and dense signals. Keyword recall is useful for exact regulatory terms like document names, article numbers, or domain phrases. Dense retrieval is useful when the user asks in natural language. The code merges both candidate sets by chunk ID and marks the source as keyword, vector, or hybrid. This design balances precision and semantic recall.

**Likely questions from examiners**

- Why not only use vector retrieval?

**Best answer**

Vector retrieval can miss exact legal terms or identifiers. Keyword retrieval is strong for exact matches. Combining both improves robustness, especially for regulation text where exact words and semantic similarity are both important.

## Slide 9. Reranking Design

**Purpose of this slide**

Explain reranker and trade-offs.

**Key bullet points**

- Final score combines:
  - `0.62 * keyword_score`
  - `0.30 * vector_score`
  - `0.08 * status_bonus`
  - `hybrid_bonus`
- Effective documents receive higher status bonus.
- Hybrid hits receive bonus.
- Reranking is lightweight and interpretable.

**Suggested figure or diagram**

Formula block and score component bar chart.

**What I should say verbally in 30 to 60 seconds**

The reranker is not a neural cross-encoder. It is a lightweight weighted formula. This is a deliberate engineering choice: it is fast, transparent, and easy to debug. Keyword score receives the largest weight because financial regulations often require exact terminology. Vector score contributes semantic similarity. Status bonus pushes effective documents upward, and hybrid bonus rewards candidates retrieved by both branches.

**Likely questions from examiners**

- Are the weights learned?

**Best answer**

No. The weights are heuristic and code-defined. The repository does not include training data or ablation experiments. A future improvement would be to tune or learn the weights using a gold chunk evaluation set.

## Slide 10. Generation and Prompt Assembly

**Purpose of this slide**

Show where prompt construction appears and how LLM generation is constrained.

**Key bullet points**

- `/qa` first calls retrieval, then generation.
- Context uses top citation chunk texts.
- Context limits: number of chunks, chars per chunk, total chars.
- Prompt says: answer only based on given articles; state uncertainty if evidence is insufficient.
- LangChain chain first, raw HTTP fallback second.

**Suggested figure or diagram**

`citations -> context block -> prompt -> LLM -> answer`

**What I should say verbally in 30 to 60 seconds**

Prompt assembly happens in `LLMService`. The service clips retrieved chunk texts according to configured context limits, then builds a prompt with the question and available articles. The system prompt requires the model to answer only from given text and to state uncertainty if evidence is insufficient. This keeps generation grounded and controls context size, which is a trade-off between completeness and latency.

**Likely questions from examiners**

- What happens if LLM is unavailable?

**Best answer**

The service returns a degraded generation status with an explicit message. It does not silently fabricate an answer. If there are no retrieved citations, the RAG service returns a no-evidence response without calling the LLM.

## Slide 11. Confidence and Traceability

**Purpose of this slide**

Explain citation and confidence outputs.

**Key bullet points**

- Answer includes citations, related articles, confidence score, consistency score, evidence coverage, and generation status.
- Consistency score uses token overlap between answer and cited chunks.
- Evidence coverage checks how much answer vocabulary appears in evidence.
- QA records and citations are persisted in MySQL.

**Suggested figure or diagram**

Answer object fields with citation links to chunks.

**What I should say verbally in 30 to 60 seconds**

The system does not only return a text answer. It also returns citations and several confidence-related signals. The consistency checker compares tokens between the answer and retrieved evidence. Evidence coverage measures how much of the answer is covered by citation text. These are not perfect factuality metrics, but they provide transparent signals for users and for debugging.

**Likely questions from examiners**

- Does token overlap prove correctness?

**Best answer**

No. It is a lightweight consistency signal, not a formal proof. It helps detect weak evidence, but final correctness still depends on the retrieved citations and human verification.

## Slide 12. Evaluation and Demo

**Purpose of this slide**

Show what experiments or evaluation the repository actually supports.

**Key bullet points**

- `evaluate_acceptance.py` tests search, QA, related search, timeliness, and OCR questions.
- Metrics: success rate, keyword-based accuracy, keyword-based recall, average latency, p95 latency.
- Reports are written to `docs/reports/acceptance_eval.*`.
- Unit tests cover API contracts, embedding, vector score, task claim, health, and LLM behavior.
- Limitation: no gold chunk benchmark or ablation study.

**Suggested figure or diagram**

Evaluation table with columns: task, total, success rate, accuracy, recall, avg latency.

**What I should say verbally in 30 to 60 seconds**

The repository includes a fixed acceptance evaluation script. It checks whether APIs return successful responses and whether returned text covers expected keywords. This is useful for engineering acceptance, but it is not a strict IR benchmark. The repository also includes unit tests for core services. For a live demo, I would show health check, search, QA, and citation output.

**Likely questions from examiners**

- Can you claim the system has high retrieval accuracy?

**Best answer**

Only within the current keyword-based acceptance set. I should not claim general retrieval accuracy without a gold chunk benchmark. A stricter evaluation should label gold documents or gold chunks and compute Recall@K, MRR, and nDCG.

## Slide 13. Engineering Highlights vs Research Contribution

**Purpose of this slide**

Separate realistic engineering contribution from research novelty.

**Key bullet points**

Engineering contributions:

- End-to-end ingestion-to-QA backend.
- Hybrid retrieval with Milvus and MySQL.
- Task retry and stage metrics.
- Health checks, metrics, tests, and deployment config.
- Persistent QA records and citations.

Research-like aspects:

- Domain-aware chunking by regulation articles.
- Metadata-aware retrieval and status handling.
- Evidence-grounded answer confidence signals.

**Suggested figure or diagram**

Two-column table: engineering contribution vs research-oriented design.

**What I should say verbally in 30 to 60 seconds**

I would position this project mainly as an engineering RAG system, not as a new retrieval algorithm. The contribution is in integrating multiple components into a working backend for a domain-specific task. The more research-oriented ideas are article-aware chunking, metadata-aware retrieval, and confidence scoring, but the repository does not claim novel algorithms or large benchmark improvements.

**Likely questions from examiners**

- What is the innovation?

**Best answer**

The innovation is application-oriented integration: combining article-aware chunking, hybrid retrieval, metadata/status filtering, citation-based QA, and observable ingestion into a domain-specific RAG backend. It is not a claim of a new ANN algorithm or new LLM model.

## Slide 14. Limitations and Future Work

**Purpose of this slide**

Show technical honesty and improvement path.

**Key bullet points**

Current limitations:

- No frontend.
- No authentication or authorization.
- No gold chunk benchmark.
- Some abnormal `.doc` files may fail parsing.
- No large-scale load testing.
- Reranker weights are heuristic.

Future work:

- Add gold chunk evaluation with Recall@K, MRR, nDCG.
- Add frontend and user auth.
- Add LibreOffice-based document conversion fallback.
- Tune reranker weights or add cross-encoder reranker.
- Add production deployment hardening.

**Suggested figure or diagram**

Roadmap timeline.

**What I should say verbally in 30 to 60 seconds**

The project is usable as a backend acceptance version, but there are clear limitations. The most important research/evaluation gap is the lack of gold chunk labels. The most important product gaps are frontend and authentication. The most important engineering gap is handling abnormal old Word documents and production hardening. These are realistic next steps rather than hidden issues.

**Likely questions from examiners**

- What would you improve first?

**Best answer**

I would first build a gold chunk evaluation set, because it directly measures whether retrieval finds the correct legal article. Then I would tune reranking and add stronger document conversion fallback.

## Slide 15. Conclusion

**Purpose of this slide**

Summarize the project and invite questions.

**Key bullet points**

- Built a backend RAG system for financial regulation documents.
- Implemented ingestion, chunking, embedding, Milvus vector search, hybrid retrieval, reranking, generation, citation, persistence, and evaluation.
- System is evidence-grounded and operationally observable.
- Current version is a backend acceptance version, not a full production product.

**Suggested figure or diagram**

One-line pipeline summary and GitHub repository link.

**What I should say verbally in 30 to 60 seconds**

In conclusion, this project implements a complete backend RAG workflow for financial regulation documents. It connects parsing, chunking, embedding, vector search, hybrid retrieval, answer generation, confidence scoring, and evaluation. The main value is a traceable and testable system design. The next stage should focus on stricter retrieval evaluation, frontend, authentication, and production hardening. Thank you, and I welcome questions.

**Likely questions from examiners**

- Is the project ready for production?

**Best answer**

It is ready as a backend project defense and acceptance prototype. It is not yet a production system because authentication, frontend, large-scale tests, and stronger evaluation are still missing.
