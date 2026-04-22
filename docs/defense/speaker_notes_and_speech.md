# Speaker Notes and Full Defense Speech

The scripts below are written for a CS undergraduate defense. They use English technical terms where appropriate and avoid unsupported novelty claims.

## Part 1. Slide-by-Slide Speaker Notes

### Slide 1. Title and System Scope

**Full speech script**

Good morning, teachers. My project is a Financial Policy RAG Question Answering System. The goal is to build a backend system that can ingest financial regulation documents, retrieve relevant articles, and generate answers with citations. The current version is backend-first. It focuses on the technical pipeline: document parsing, metadata extraction, chunking, embedding, vector indexing, hybrid retrieval, answer generation, citation output, QA persistence, health checks, and evaluation scripts. It does not include a frontend or authentication module yet. I will present it as a backend acceptance version, not as a fully commercial product. The key idea is to make answers traceable to source documents rather than relying only on the language model's internal knowledge.

**Transition**

Before discussing the architecture, I will first define the problem this system tries to solve.

**Short version for memorization**

This is a backend-first RAG system for financial policy documents. It supports ingestion, retrieval, citation-based QA, persistence, and evaluation. It is an acceptance prototype, not a full product.

### Slide 2. Problem Definition

**Full speech script**

The core problem is evidence-grounded question answering over financial regulation documents. These documents are long, semi-structured, and often organized by articles, dates, issuing agencies, and validity status. If we use only keyword search, users must know the exact terms used in the document. If we use only an LLM, the model may generate an answer that is fluent but not supported by the document. For regulation-related questions, this is risky. The system therefore needs to retrieve relevant text, keep citations, handle document metadata such as status and category, and then generate an answer based on the retrieved evidence.

**Transition**

This leads to the reason why I chose a RAG architecture.

**Short version for memorization**

The problem is answering regulatory questions with evidence. Keyword search lacks semantic flexibility, and LLM-only answers risk hallucination. RAG combines retrieval and controlled generation.

### Slide 3. Why RAG

**Full speech script**

RAG is suitable because it separates knowledge access from answer generation. Retrieval first narrows the context to a small set of relevant chunks. Then the LLM generates an answer from that context. This reduces token cost and makes the answer auditable through citations. In this repository, the `/qa` endpoint first calls the retriever and then passes citations to the RAG service. The prompt explicitly tells the model to answer only according to the given articles and to state uncertainty when evidence is insufficient. This does not completely eliminate hallucination, but it gives the system a stronger grounding mechanism than direct LLM prompting.

**Transition**

Next, I will show how the system is organized at the architecture level.

**Short version for memorization**

RAG is used to retrieve evidence first and generate later. It improves traceability, controls context size, and reduces unsupported generation.

### Slide 4. Overall Architecture

**Full speech script**

The system is built around FastAPI, MySQL, Milvus, and OpenAI-compatible model APIs. FastAPI exposes routes under `/api/v1`. MySQL stores structured data, including documents, chunks, ingest tasks, QA records, citations, and favorites. Milvus stores chunk embeddings and metadata fields for vector search. The embedding service calls an API endpoint or uses hash embedding in fallback development mode. The LLM service uses LangChain if available and can fall back to direct HTTP requests. This separation is important: MySQL is used for reliable structured persistence, while Milvus is used for approximate vector search.

**Transition**

Now I will walk through how raw documents become searchable knowledge.

**Short version for memorization**

FastAPI provides APIs, MySQL stores structured records, Milvus stores vectors, and model APIs provide embedding and chat generation.

### Slide 5. Document Ingestion Pipeline

**Full speech script**

Document ingestion is handled by `DocumentPipelineService`. The pipeline includes several stages: file hash, parse, clean, metadata extraction, metadata application, optional old vector deletion, chunking, embedding, vector upsert, and database commit. This staged design is useful because document processing can fail in many places, especially parsing and embedding. The repository also includes an ingest task service with states such as pending, running, retrying, success, and dead. Each task records stage metrics and errors. So the system is not just a one-shot script; it has basic operational visibility.

**Transition**

The next important step in ingestion is how the document is split into chunks.

**Short version for memorization**

The ingestion pipeline parses files, extracts metadata, chunks text, embeds chunks, writes MySQL records, and upserts Milvus vectors. Task states make failures observable.

### Slide 6. Chunking Strategy

**Full speech script**

Chunking appears in `Chunker`. The system first tries to split text by Chinese regulation article patterns, especially `第X条`, and it also tracks chapter patterns like `第X章`. This is domain-aware because regulation documents are naturally organized by articles. If no article pattern is found, the system falls back to fixed-size window chunking with overlap. The trade-off is clear: article chunks are more explainable and precise, while sliding windows make the system robust for less structured files. However, smaller chunks can lose surrounding context, so the generation stage later controls how many chunks are assembled into the prompt.

**Transition**

After chunking, each chunk must be represented as a vector for dense retrieval.

**Short version for memorization**

The system uses article-first chunking and window fallback. This keeps regulation structure when possible while still supporting unstructured text.

### Slide 7. Embedding and Vector Index

**Full speech script**

Embedding is implemented in `EmbeddingService`. In API mode, it deduplicates repeated texts, sends batch requests to an OpenAI-compatible `/embeddings` endpoint, sorts results by returned index, normalizes dimensions, and normalizes vector length. The vectors are stored in Milvus by `VectorStoreService`. The Milvus collection is named `finance_policy_chunks`, and it includes both vector and metadata fields such as region, category, status, and article number. The index configured in code is `IVF_FLAT` with `COSINE` metric, and the search uses the configurable `nprobe` parameter. This is where ANN-style vector search appears in the system.

**Transition**

With vectors ready, the system can perform hybrid retrieval.

**Short version for memorization**

Chunks are embedded through an API, normalized, and stored in Milvus. The Milvus index is IVF_FLAT with cosine similarity and configurable nprobe.

### Slide 8. Hybrid Retrieval Pipeline

**Full speech script**

The retriever combines keyword retrieval and dense vector retrieval. First, it applies structured filters such as status, region, source organization, and category. The keyword branch uses exact query matching and token-based SQL `contains` matching. It then computes a BM25-like score over candidates. The dense branch embeds the query and searches Milvus. After both branches return candidates, the system merges them by chunk ID and marks the source as keyword, vector, or hybrid. This is a practical design because exact regulatory terms and semantic natural-language questions both matter.

**Transition**

After retrieval, candidates need to be ranked in a consistent way.

**Short version for memorization**

The retriever uses structured filters, keyword recall, BM25-like scoring, vector recall, candidate merging, and source labels.

### Slide 9. Reranking Design

**Full speech script**

The reranker is a lightweight scoring function rather than a neural cross-encoder. The final score is a weighted sum of keyword score, vector score, status bonus, and hybrid bonus. Keyword score has the largest weight, because in regulatory text exact terms are often important. Vector score adds semantic matching. Status bonus pushes effective documents upward, and hybrid bonus rewards candidates found by both keyword and vector branches. The trade-off is that this reranker is transparent and fast, but the weights are heuristic. The repository does not include training or ablation experiments for these weights.

**Transition**

The top-ranked chunks are then used to build the prompt for answer generation.

**Short version for memorization**

Reranking is interpretable: keyword, vector, status, and hybrid signals are combined. It is fast but heuristic.

### Slide 10. Generation and Prompt Assembly

**Full speech script**

Answer generation is handled by `RAGService` and `LLMService`. The QA endpoint first retrieves citations, then calls the RAG service. The LLM service builds a context block from retrieved chunk texts, with limits on number of chunks, characters per chunk, and total context length. This is a recall-latency trade-off: more context may improve completeness, but increases latency and token cost. The system prompt tells the model to answer only based on the given articles and to state uncertainty if evidence is insufficient. If LangChain fails, raw HTTP is used. If the LLM is unavailable, the system returns a degraded status instead of silently inventing an answer.

**Transition**

Besides the answer text, the system also returns confidence and traceability signals.

**Short version for memorization**

The prompt is assembled from top citation chunks with length limits. The LLM is constrained to answer from evidence, and failures return explicit degraded status.

### Slide 11. Confidence and Traceability

**Full speech script**

The answer response includes citations, related articles, confidence score, consistency score, evidence coverage, generation status, and degraded reason. The consistency score is based on token overlap between the answer and cited chunks. Evidence coverage measures how much of the answer vocabulary is covered by the evidence. These are lightweight signals, not formal factuality proofs. Their purpose is to make the system more transparent and easier to debug. QA records and citations are also persisted in MySQL, so previous questions and their evidence can be inspected later.

**Transition**

Next, I will describe what evaluation is included in the repository.

**Short version for memorization**

The system returns answer, citations, confidence, consistency, evidence coverage, and generation status. These are transparency signals, not absolute correctness guarantees.

### Slide 12. Evaluation and Demo

**Full speech script**

The repository includes an acceptance evaluation script. It tests search, QA, related search, timeliness questions, and OCR-related questions. The metrics include success rate, keyword-based accuracy, keyword-based recall, average latency, and p95 latency. This is useful for checking whether the system works end-to-end, but it is not a strict information retrieval benchmark. The test set uses expected keywords, not manually labeled gold chunks. The repository also includes unit and contract tests for API behavior, embedding, vector score conversion, ingest task claim, health, and LLM fallback.

**Transition**

Based on this implementation, I will separate engineering contribution from research contribution.

**Short version for memorization**

Evaluation is keyword-based acceptance testing plus unit tests. It proves the pipeline works, but it is not a gold-label retrieval benchmark.

### Slide 13. Engineering Highlights vs Research Contribution

**Full speech script**

I position this project mainly as an engineering RAG system. The engineering contribution is the end-to-end backend: ingestion, chunking, embedding, vector database, hybrid retrieval, generation, citation persistence, health checks, metrics, tests, and Docker deployment. The research-oriented design points are article-aware chunking, metadata-aware retrieval, and evidence-based confidence signals. However, I do not claim a new ANN algorithm or a new LLM method. The value is in integrating existing techniques into a traceable domain-specific RAG workflow.

**Transition**

Finally, I will be explicit about limitations and future work.

**Short version for memorization**

The main contribution is engineering integration. Research-like parts are domain-aware chunking, metadata filtering, and confidence signals, but not a new model or algorithm.

### Slide 14. Limitations and Future Work

**Full speech script**

There are several limitations. First, the repository does not include a frontend or authentication. Second, old abnormal `.doc` files may still fail parsing and may need LibreOffice conversion or manual conversion. Third, the evaluation lacks gold chunk labels and ablation studies. Fourth, the reranker weights are heuristic. Future work should first build a gold chunk evaluation set, because it would directly measure whether the retriever finds the correct article. Then I would improve document conversion, add authentication and frontend, and consider a stronger reranker such as a cross-encoder if latency allows.

**Transition**

I will now conclude the presentation.

**Short version for memorization**

The main gaps are frontend, auth, abnormal doc parsing, gold chunk evaluation, and heuristic reranking. Future work should start with stricter evaluation.

### Slide 15. Conclusion

**Full speech script**

To conclude, this project implements a backend RAG workflow for financial regulation documents. It turns raw files into chunks and embeddings, stores structured data in MySQL, stores vectors in Milvus, retrieves evidence through hybrid search, reranks candidates, generates answers with citations, and records QA history. The current version is suitable as a backend acceptance prototype. Its main strength is traceability and operational completeness. Its next stage should focus on stricter evaluation, frontend, authentication, and production hardening. Thank you, and I welcome your questions.

**Transition**

End of presentation.

**Short version for memorization**

The system is a complete backend RAG prototype with ingestion, retrieval, generation, citation, persistence, and evaluation. It is ready for defense but not full production.

## Part 2. Full 8-Minute Defense Speech

Good morning, teachers. My project is a Financial Policy RAG Question Answering System.

The goal is to build a backend system that can ingest financial regulation documents, retrieve relevant articles, and generate answers with citations. The current version is backend-first. It focuses on the core technical pipeline: document parsing, metadata extraction, chunking, embedding, vector indexing, hybrid retrieval, LLM-based answer generation, QA persistence, health checks, and evaluation scripts. It does not include a frontend or authentication module yet, so I will present it as a backend acceptance prototype rather than a complete production product. [pause]

The problem I want to solve is evidence-grounded question answering over financial regulation documents. These documents are usually long, semi-structured, and organized by articles, dates, issuing agencies, and validity status. If we use only keyword search, users must know the exact wording used in the document. If we use only an LLM, the model may produce a fluent but unsupported answer. This is risky in a regulation scenario, because users need to know which article supports the answer. Therefore, the system needs retrieval, citation, metadata handling, and controlled generation.

This is why I chose a RAG architecture. RAG separates knowledge access from answer generation. Retrieval first narrows the context to a small set of relevant chunks. Then the LLM generates the answer from that context. This reduces token cost and makes the answer auditable. In this repository, the `/qa` endpoint first calls the retriever, gets citations, and then passes the citations to the RAG service. The prompt explicitly tells the model to answer only according to the given articles and to state uncertainty if evidence is insufficient. RAG does not completely eliminate hallucination, but it gives the system a stronger grounding mechanism than direct LLM prompting. [pause]

At the architecture level, the system uses FastAPI, MySQL, Milvus, and OpenAI-compatible model APIs. FastAPI exposes the backend routes under `/api/v1`. MySQL stores structured data, including documents, chunks, ingest tasks, QA records, citations, and favorites. Milvus stores dense vectors for chunk-level semantic search. The embedding service calls an API endpoint in production mode and also supports hash embedding for development. The LLM service uses LangChain if available, and can fall back to raw HTTP calls. This separation is intentional: MySQL is reliable for structured metadata and persistence, while Milvus is designed for vector similarity search.

The first main workflow is document ingestion. It is implemented in `DocumentPipelineService`. The stages are file hash, parse, clean, metadata extraction, metadata application, optional old vector deletion, chunking, embedding, vector upsert, and database commit. The parser supports `.docx`, `.pdf`, `.doc`, images, and plain text. Images are handled through OCR. The system also has an ingest task service with states such as pending, running, retrying, success, and dead. Each task records stage metrics and error messages. This is useful because parsing and embedding can fail, and the system should expose where and why a failure happens.

For chunking, the system uses a simple but domain-aware strategy. It first tries to split text by Chinese regulation article patterns, especially `第X条`, and it also tracks chapter patterns like `第X章`. This matches the natural structure of regulation documents. If no article pattern is found, it falls back to fixed-size window chunking with overlap. The trade-off is that article chunks are explainable and precise, while window chunks make the system robust for less structured files. Smaller chunks improve retrieval precision, but may lose surrounding context, so the generation stage later controls how many chunks are assembled into the prompt. [pause]

After chunking, each chunk is converted into an embedding. In API mode, the embedding service deduplicates repeated texts, sends batch requests to an OpenAI-compatible `/embeddings` endpoint, sorts returned vectors by index, normalizes vector dimensions, and normalizes vector length. The vectors are stored in a Milvus collection named `finance_policy_chunks`. The collection includes both vector data and metadata fields such as region, category, status, and article number. The configured vector index is `IVF_FLAT` with cosine similarity, and search uses the configurable `nprobe` parameter. This is where ANN-style vector search appears in the system.

The retrieval pipeline is hybrid. It combines keyword retrieval and dense vector retrieval. First, it applies structured filters such as status, region, source organization, and category. The keyword branch uses exact query matching and token-based SQL `contains` matching. It then computes a BM25-like score over the candidate set. The dense branch embeds the query and searches Milvus. After both branches return candidates, the system merges them by chunk ID and marks the source as keyword, vector, or hybrid. This design is practical because exact legal terms and semantic natural-language questions are both important in regulation documents.

After retrieval, the system reranks candidates using a lightweight scoring function. The final score combines keyword score, vector score, status bonus, and hybrid bonus. Keyword score has the largest weight, because exact terminology is important in financial regulation. Vector score adds semantic matching. Status bonus pushes effective documents upward, and hybrid bonus rewards candidates found by both retrieval branches. This reranker is not a neural cross-encoder. The advantage is that it is transparent and fast. The limitation is that the weights are heuristic and are not learned from training data.

For generation, the QA endpoint passes retrieved citations to `RAGService` and `LLMService`. The LLM service builds a context block from the retrieved chunk texts. It limits the number of chunks, characters per chunk, and total context length. This is a recall-versus-latency trade-off: more context may improve completeness, but it increases token cost and response time. The system prompt tells the model to answer only based on the given articles and to state uncertainty if the evidence is insufficient. If there is no evidence, the RAG service returns a no-evidence response without calling the LLM. If the LLM is unavailable, the service returns a degraded status instead of silently inventing an answer.

The answer is not just plain text. It includes citations, related article numbers, confidence score, consistency score, evidence coverage, generation status, and degraded reason. The consistency score is based on token overlap between the answer and cited chunks. Evidence coverage checks how much of the answer vocabulary appears in the evidence. These are not formal correctness proofs, but they are useful transparency signals. QA records and citations are also persisted in MySQL, so previous questions and their evidence can be inspected later. [pause]

For evaluation, the repository includes an acceptance evaluation script. It tests search, QA, related search, timeliness questions, and OCR-related questions. The metrics include success rate, keyword-based accuracy, keyword-based recall, average latency, and p95 latency. This proves the pipeline works end-to-end under the fixed evaluation set. However, it is not a strict information retrieval benchmark, because it uses expected keywords rather than manually labeled gold chunks. The repository also includes unit and contract tests for API behavior, embedding, vector score conversion, ingest task claim, health check, and LLM behavior.

I would position this project mainly as an engineering RAG system. The engineering contribution is the end-to-end backend integration: ingestion, chunking, embedding, vector database, hybrid retrieval, generation, citation persistence, health checks, metrics, tests, and Docker deployment. The research-oriented design points are article-aware chunking, metadata-aware retrieval, and evidence-based confidence signals. I do not claim a new ANN algorithm or a new LLM method. The value is in integrating existing techniques into a traceable domain-specific RAG workflow.

There are also limitations. The repository does not include a frontend or authentication. Some abnormal old `.doc` files may still fail parsing and may need LibreOffice conversion or manual conversion. The evaluation lacks gold chunk labels and ablation studies. The reranker weights are heuristic. In future work, I would first build a gold chunk evaluation set, because it directly measures whether the retriever finds the correct article. Then I would improve document conversion, add authentication and frontend, and consider a stronger reranker such as a cross-encoder if latency allows.

To conclude, this project implements a backend RAG workflow for financial regulation documents. It turns raw files into chunks and embeddings, stores structured data in MySQL, stores vectors in Milvus, retrieves evidence through hybrid search, reranks candidates, generates answers with citations, and records QA history. The current version is suitable as a backend acceptance prototype. Its main strength is traceability and operational completeness. Its next stage should focus on stricter evaluation, frontend, authentication, and production hardening.

Thank you. I welcome your questions.

## Part 3. Two-Minute Condensed Version

Good morning, teachers. My project is a backend-first RAG system for financial regulation documents.

The problem is that regulation documents are long, article-based, and require traceable answers. Keyword search is not flexible enough for natural-language questions, while LLM-only answers may hallucinate. Therefore, I use RAG: retrieve evidence first, then generate an answer based on the retrieved evidence.

The system is built with FastAPI, MySQL, Milvus, and OpenAI-compatible model APIs. MySQL stores documents, chunks, ingest tasks, QA records, citations, and favorites. Milvus stores chunk embeddings for vector search. The ingestion pipeline parses files, cleans text, extracts metadata, chunks by regulation articles such as `第X条`, embeds chunks, and writes both MySQL records and Milvus vectors.

The retrieval pipeline is hybrid. It combines keyword recall, BM25-like scoring, and Milvus vector search. It then merges candidates by chunk ID and reranks them using keyword score, vector score, status bonus, and hybrid bonus. This balances exact legal terminology and semantic matching.

For generation, the QA endpoint retrieves citations first, assembles a bounded prompt from top chunks, and asks the LLM to answer only according to the given articles. If there is no evidence, it returns a no-evidence response. If the LLM is unavailable, it returns a degraded status rather than fabricating an answer. The response includes citations, confidence score, consistency score, evidence coverage, and generation status.

The repository includes acceptance evaluation scripts and unit tests. The evaluation checks success rate, keyword-based accuracy, keyword-based recall, and latency. However, it is not a strict gold chunk benchmark. Future work should add manually labeled gold chunks, frontend, authentication, better `.doc` conversion, and possibly a stronger reranker.

In summary, this project is not a new retrieval algorithm, but a complete engineering implementation of a traceable RAG backend for financial policy documents.

## Part 4. Likely Defense Questions and Model Answers

### 1. Why did you choose RAG instead of only using an LLM?

Because the domain requires evidence-grounded answers. RAG retrieves source articles first and uses them as context, reducing unsupported generation and enabling citations. LLM-only answering cannot guarantee that the answer comes from the local document collection.

### 2. Why did you use both MySQL and Milvus?

MySQL is used for structured data such as documents, chunks, metadata, tasks, QA records, and citations. Milvus is used for vector similarity search. They solve different storage and query problems.

### 3. Where does ANN appear in the system?

ANN-style vector search appears in `VectorStoreService`, where Milvus creates an `IVF_FLAT` index with `COSINE` metric and searches the `embedding` field using `nprobe`.

### 4. What is the chunking strategy?

The system first chunks by regulation article patterns such as `第X条`, and tracks chapter patterns like `第X章`. If no articles are found, it falls back to fixed-size window chunking with overlap.

### 5. Why not use semantic chunking?

Semantic chunking may improve boundaries, but regulation documents have explicit article structure. Article-based chunking is deterministic, explainable, and easier to cite. Semantic chunking is a possible future improvement.

### 6. Why combine keyword and vector retrieval?

Keyword retrieval is strong for exact legal terms, document names, and article phrases. Vector retrieval is stronger for natural-language semantic matching. Combining both improves robustness.

### 7. How does the reranker work?

The reranker computes a weighted score from keyword score, vector score, status bonus, and hybrid bonus. It is lightweight and interpretable, but the weights are heuristic.

### 8. Are the reranker weights learned?

No. They are manually defined in code. The repository does not include training data or ablation experiments. A future gold chunk benchmark could be used to tune them.

### 9. How do you reduce hallucination?

The system retrieves citations first, constructs a prompt only from retrieved chunks, and instructs the LLM to answer only based on those articles. It also returns citations and confidence signals. This reduces but does not eliminate hallucination.

### 10. What happens if the LLM service fails?

The LLM service returns a degraded generation status with an explicit message. The system does not silently fabricate an answer.

### 11. What does confidence score mean?

It is a heuristic score combining citation count, retrieval score, answer-evidence consistency, evidence coverage, generation status, and whether the result hits effective documents. It is a transparency signal, not a formal proof of correctness.

### 12. How is the system evaluated?

The repository includes an acceptance evaluation script. It tests search, QA, related search, timeliness, and OCR-related questions. Metrics include success rate, keyword-based accuracy, keyword-based recall, average latency, and p95 latency.

### 13. What is missing from the evaluation?

The repository does not include a gold chunk benchmark. A stricter evaluation should label the correct document, article, or chunk for each query and compute Recall@K, MRR, nDCG, citation correctness, and answer point accuracy.

### 14. What are the main limitations?

The current repository lacks frontend, authentication, gold chunk evaluation, large-scale load testing, and robust conversion for some abnormal old `.doc` files. The reranker weights are also heuristic.

### 15. What is the main contribution?

The main contribution is engineering integration: a complete backend RAG workflow for regulation documents, including ingestion, article-aware chunking, metadata extraction, hybrid retrieval, vector search, reranking, evidence-grounded generation, citations, persistence, health checks, and evaluation scripts.
