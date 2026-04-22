# 仓库分析报告（答辩准备）

本文只依据仓库中可验证的代码、配置、脚本和报告进行整理。未被仓库支持的内容不会作为事实陈述；需要推断的地方会明确标注为“合理推断”。

## A. 项目简要总结

### 已确认事实

本项目实现了一个面向金融监管制度文档的后端 RAG 问答系统。系统支持文档解析、元数据抽取、条文切分、向量入库、混合检索、RAG 问答、引用返回、QA 历史持久化、收藏、健康检查、指标统计和验收评测。证据见 [README.md](../../README.md)、[backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py)、[backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)、[backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)。

后端使用 FastAPI，所有 API 路由挂载在 `/api/v1` 下。证据见 [backend/app/main.py](../../backend/app/main.py)、[backend/app/api/v1/router.py](../../backend/app/api/v1/router.py)。

系统使用 SQL 数据库保存文档、分块、导入任务、QA 记录、QA 引用和收藏；当 `VECTOR_BACKEND=milvus` 时，使用 Milvus 保存向量。证据见 [backend/app/db/models.py](../../backend/app/db/models.py)、[backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)、[deploy/docker-compose.yml](../../deploy/docker-compose.yml)。

embedding 支持 `hash` 和 `api` 两种后端。API 模式调用 OpenAI-Compatible `/embeddings` 接口，并做批量请求、去重、维度归一和向量归一。证据见 [backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py)、[backend/app/core/config.py](../../backend/app/core/config.py)。

生成模块优先使用 LangChain 组合 Prompt、ChatModel 和 OutputParser；失败时回退到直接 HTTP 请求 OpenAI-Compatible `/chat/completions` 接口。证据见 [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py)。

### 合理推断

从 API、数据模型和 README 可以推断：本系统解决的问题是“让金融监管制度文档可检索、可问答、可溯源”，重点是基于制度原文给出带引用的答案，而不是让 LLM 凭内部知识自由回答。证据见 [README.md](../../README.md)、[backend/app/models/schemas.py](../../backend/app/models/schemas.py)。

## B. 模块拆解

### 1. 应用入口与路由

- [backend/app/main.py](../../backend/app/main.py)：创建 FastAPI 应用，挂载 `/api/v1` 路由，添加请求指标中间件，并在启动时初始化数据库。
- [backend/app/api/v1/router.py](../../backend/app/api/v1/router.py)：注册 documents、search、qa、history、favorites、health、metrics 等 endpoint 模块。

### 2. 配置模块

- [backend/app/core/config.py](../../backend/app/core/config.py)：使用 Pydantic `BaseSettings` 管理运行时配置，包括数据库、MySQL、Milvus、向量后端、embedding 后端、Qwen/dev API profile、LLM 超时、RAG 上下文长度、向量检索参数和 OCR 语言。
- 支持 `runtime_profile=dev_api/prod_qwen`，支持 `embedding_backend=hash/api`。证据见 [backend/app/core/config.py](../../backend/app/core/config.py)。

### 3. 数据模型

- [backend/app/db/models.py](../../backend/app/db/models.py)：定义 SQLAlchemy 模型：
  - `Document`：文档元数据。
  - `Chunk`：条文或文本分块。
  - `IngestTask`：导入任务状态。
  - `QARecord`：问答历史。
  - `QACitation`：问答引用。
  - `Favorite`：收藏。
- [backend/app/db/session.py](../../backend/app/db/session.py)：创建数据库 engine、session factory，并负责建表和运行时字段补齐。

### 4. 文档导入模块

- [backend/app/api/v1/endpoints/documents.py](../../backend/app/api/v1/endpoints/documents.py)：提供上传、单文档导入、文档列表、标签管理、导入任务创建、导入任务运行和导入任务查询接口。
- [backend/app/services/document_service.py](../../backend/app/services/document_service.py)：创建上传文档记录，查询文档，管理标签。
- [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py)：编排导入流水线，包括 hash、parse、clean、metadata、apply_metadata、vector_delete、chunk、embedding、vector_upsert、database_commit 等阶段。
- [backend/app/services/ingest_task_service.py](../../backend/app/services/ingest_task_service.py)：管理导入任务队列、重试、dead 状态、原子 claim 和阶段指标。

### 5. 解析、OCR、清洗、切分、元数据

- [backend/app/services/parser_service.py](../../backend/app/services/parser_service.py)：按后缀解析 `.docx`、`.pdf`、`.doc`、图片和普通文本。其中 `.doc` 会尝试 `antiword`、`catdoc`、`textutil`。
- [backend/app/services/ocr_service.py](../../backend/app/services/ocr_service.py)：使用 `pytesseract` 和 Pillow 做图片 OCR。
- [backend/app/services/cleaner_service.py](../../backend/app/services/cleaner_service.py)：做文本空白符和空行归一。
- [backend/app/services/chunker_service.py](../../backend/app/services/chunker_service.py)：优先按中文制度条文模式 `第X条` 切分，同时识别 `第X章`；无法按条文切分时回退到固定窗口切分。
- [backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py)：抽取来源机关、文号、日期、状态、地区、类别和时效证据。

### 6. Embedding 与向量数据库

- [backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py)：API embedding 模式会对文本去重、批量请求、按返回 index 对齐、维度裁剪/补零、L2 归一；API embedding 失败时抛错，避免混入 hash 向量。
- [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)：创建和访问 Milvus collection，字段包括 `vector_id`、`doc_id`、`chunk_text`、`region`、`category`、`status`、`article_no`、`embedding`。
- Milvus 索引为 `IVF_FLAT`，距离度量为 `COSINE`。证据见 [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)。
- ANN 或向量检索体现在 Milvus 对 `embedding` 字段的 search 调用，并使用 `nprobe` 参数。证据见 [backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)、[backend/app/core/config.py](../../backend/app/core/config.py)。

### 7. 检索与重排

- [backend/app/api/v1/endpoints/search.py](../../backend/app/api/v1/endpoints/search.py)：提供 `/search` 和 `/search/related`。
- [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)：实现混合检索：
  - 结构化过滤：status、region、source_org、category。
  - 关键词召回：完整 query 命中和 token 命中。
  - BM25-like 关键词评分。
  - 向量召回：query embedding + Milvus search。
  - 候选按 chunk ID 合并。
  - 最终重排。
- [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py)：用关键词分、向量分、时效状态 bonus、hybrid bonus 计算最终分数。
- `/search/related` 支持基于锚点条文的同文邻接扩展、同条号扩展和关键词扩展。证据见 [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)。

### 8. 生成与可信度

- [backend/app/api/v1/endpoints/qa.py](../../backend/app/api/v1/endpoints/qa.py)：先检索证据，再处理有效制度与历史/失效制度回退，然后调用 `RAGService`，最后记录 QA 历史。
- [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)：从 citations 生成答案，处理 no-evidence 场景，计算 consistency、evidence coverage 和 confidence。
- [backend/app/services/llm_service.py](../../backend/app/services/llm_service.py)：从检索 chunk 拼接上下文，限制上下文长度，构建 Prompt，并调用 LangChain 或原始 HTTP。
- [backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py)：用答案和引用条文的 token 重合度计算一致性分数。
- [backend/app/services/interaction_service.py](../../backend/app/services/interaction_service.py)：持久化 QA 记录、引用、历史和收藏。

### 9. 评测、报告和测试

- [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)：评测 `/search`、`/qa`、`/search/related`、时效性问题和 OCR 问题，指标包括 success rate、accuracy、recall、平均时延和 p95 时延。
- [data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json)：固定评测问题集。
- [docs/reports/acceptance_eval.md](../../docs/reports/acceptance_eval.md) 和 [docs/reports/acceptance_eval.json](../../docs/reports/acceptance_eval.json)：保存一次验收评测结果。
- [scripts/benchmark_api.py](../../scripts/benchmark_api.py)：对 search、QA、related search 做 API 延迟基线测试。
- [backend/tests](../../backend/tests)：包含 API 契约、配置、embedding、health、LLM、ingest task、vector store 等测试。

## C. 证据索引

- 问题和范围：[README.md](../../README.md)
- FastAPI 应用入口：[backend/app/main.py](../../backend/app/main.py)
- API 路由注册：[backend/app/api/v1/router.py](../../backend/app/api/v1/router.py)
- 文档接口：[backend/app/api/v1/endpoints/documents.py](../../backend/app/api/v1/endpoints/documents.py)
- 检索接口：[backend/app/api/v1/endpoints/search.py](../../backend/app/api/v1/endpoints/search.py)
- QA 接口：[backend/app/api/v1/endpoints/qa.py](../../backend/app/api/v1/endpoints/qa.py)
- 健康检查：[backend/app/api/v1/endpoints/health.py](../../backend/app/api/v1/endpoints/health.py)
- 指标接口：[backend/app/api/v1/endpoints/metrics.py](../../backend/app/api/v1/endpoints/metrics.py)
- 配置：[backend/app/core/config.py](../../backend/app/core/config.py)
- 数据库模型：[backend/app/db/models.py](../../backend/app/db/models.py)
- 导入流水线：[backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py)
- 解析器：[backend/app/services/parser_service.py](../../backend/app/services/parser_service.py)
- OCR：[backend/app/services/ocr_service.py](../../backend/app/services/ocr_service.py)
- 切分：[backend/app/services/chunker_service.py](../../backend/app/services/chunker_service.py)
- 元数据抽取：[backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py)
- Embedding：[backend/app/services/embedding_service.py](../../backend/app/services/embedding_service.py)
- 向量库：[backend/app/services/vector_store_service.py](../../backend/app/services/vector_store_service.py)
- 检索器：[backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)
- 重排器：[backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py)
- RAG 答案生成：[backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)
- LLM Prompt 和生成：[backend/app/services/llm_service.py](../../backend/app/services/llm_service.py)
- 一致性评分：[backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py)
- 持久化交互记录：[backend/app/services/interaction_service.py](../../backend/app/services/interaction_service.py)
- Docker 部署：[deploy/docker-compose.yml](../../deploy/docker-compose.yml)、[deploy/backend.Dockerfile](../../deploy/backend.Dockerfile)
- 验收评测：[scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)、[data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json)、[docs/reports/acceptance_eval.md](../../docs/reports/acceptance_eval.md)
- API 基准：[scripts/benchmark_api.py](../../scripts/benchmark_api.py)
- 测试：[backend/tests](../../backend/tests)

## D. 答辩 PPT 可选角度

### 角度 1：面向监管制度的工程化 RAG 闭环

重点展示从文档导入到答案生成的完整后端链路，突出可运行、可观测、可追溯。证据见 [backend/app/services/document_pipeline_service.py](../../backend/app/services/document_pipeline_service.py)、[backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)。

### 角度 2：中文监管文本的混合检索

重点展示关键词/BM25-like 检索与 Milvus 向量检索如何互补，以及候选合并和重排。证据见 [backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)、[backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py)。

### 角度 3：带证据和可信度信号的 QA

重点展示 citations、confidence、consistency、evidence coverage、degraded status 等设计。证据见 [backend/app/services/rag_service.py](../../backend/app/services/rag_service.py)、[backend/app/services/llm_service.py](../../backend/app/services/llm_service.py)、[backend/app/services/consistency_service.py](../../backend/app/services/consistency_service.py)。

### 角度 4：制度元数据和时效性处理

重点展示发文机关、文号、日期、状态、地区、类别等元数据如何进入检索与问答。证据见 [backend/app/db/models.py](../../backend/app/db/models.py)、[backend/app/services/metadata_service.py](../../backend/app/services/metadata_service.py)、[backend/app/services/retriever_service.py](../../backend/app/services/retriever_service.py)。

### 角度 5：可部署和可验收的后端系统

重点展示 Docker Compose、health、metrics、ingest task、评测脚本和测试。证据见 [deploy/docker-compose.yml](../../deploy/docker-compose.yml)、[backend/app/api/v1/endpoints/health.py](../../backend/app/api/v1/endpoints/health.py)、[backend/app/api/v1/endpoints/metrics.py](../../backend/app/api/v1/endpoints/metrics.py)、[scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)、[backend/tests](../../backend/tests)。

## E. 不确定性和证据不足

- 仓库没有前端实现。README 也明确当前是后端优先。证据见 [README.md](../../README.md)。
- 仓库没有人工标注的 gold chunk 检索评测集。当前验收评测使用 expected keywords，而不是 gold document 或 gold chunk。证据见 [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)、[data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json)。
- 仓库没有认证鉴权中间件。当前 routes 中没有用户身份校验逻辑。证据见 [backend/app/api/v1/endpoints](../../backend/app/api/v1/endpoints)。
- 仓库没有上传原始监管文件。原始数据目录被 [.gitignore](../../.gitignore) 忽略。
- 仓库没有 keyword-only、vector-only、hybrid 的消融实验。重排公式存在，但没有对应消融结果。证据见 [backend/app/services/rerank_service.py](../../backend/app/services/rerank_service.py)、[docs/reports](../../docs/reports)。
- 仓库没有生产级大规模压测报告。现有脚本更接近验收评测和 API 基线测试。证据见 [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)、[scripts/benchmark_api.py](../../scripts/benchmark_api.py)。
