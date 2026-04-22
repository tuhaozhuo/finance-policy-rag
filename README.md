# 基于 RAG 的金融制度知识问答系统

后端优先的金融监管制度检索问答系统。系统面向 `doc/docx/pdf/image` 等监管文件，完成批量解析、元数据抽取、条文切分、向量化入库、混合检索、可信问答、历史/收藏持久化与验收评测。

当前实现重点是后端与数据链路，前端可后续按 API 补齐。

## 当前状态

- 运行环境：Python `>=3.11,<3.12`，本地与 Docker 均按 Python 3.11 对齐。
- 数据存储：MySQL 保存文档、条文、任务、QA 记录、引用和收藏；Milvus 保存条文向量。
- 模型服务：聊天模型走 OpenAI-Compatible Qwen 配置；embedding 支持独立 API，也可回退到 Qwen embedding profile。
- 本地数据快照：150 个文档入库任务，148 个成功，2 个源 `.doc` 文件解析失败；MySQL chunks 与 Milvus entities 均为 1487。
- 最近测试：`/health`、`/search`、`/qa`、`/metrics`、固定验收评测与 `pytest` 均通过。

## 系统架构

```mermaid
flowchart LR
    A["原始监管文件<br/>doc/docx/pdf/image"] --> B["解析层<br/>antiword/textutil/docx/pdf/OCR"]
    B --> C["清洗与元数据抽取<br/>日期/文号/机关/地区/类别/时效"]
    C --> D["条文切分<br/>第X条优先 + 窗口回退"]
    D --> E["Embedding 服务<br/>Qwen 或独立 embedding API"]
    D --> F["MySQL<br/>documents/chunks/tasks/qa/favorites"]
    E --> G["Milvus<br/>chunk vectors + metadata fields"]
    H["用户问题"] --> I["混合检索<br/>关键词/BM25-like + Milvus 向量"]
    F --> I
    G --> I
    I --> J["Rerank<br/>关键词分/向量分/时效/混合命中"]
    J --> K["证据引用"]
    K --> L["LLM 生成<br/>仅基于引用条文"]
    L --> M["可信度评分<br/>retrieval/coverage/consistency/effective"]
    M --> N["答案 + 引用 + 可信度 + 降级状态"]
```

## 数据模型

核心表：

- `documents`：文档级元数据，包括标题、来源机关、文号、地区、类别、发布日期、生效日期、失效日期、时效状态、原文路径、标签、导入状态。
- `chunks`：条文级内容，包括章节、条号、正文、关键词、状态、embedding 模型、Milvus `vector_id`。
- `ingest_tasks`：导入任务状态机，记录 `pending/running/retrying/success/dead`、重试次数、阶段耗时和错误信息。
- `qa_records`：问答历史，记录问题、答案、可信度、时延、生成状态。
- `qa_citations`：每次问答使用的证据引用。
- `favorites`：用户收藏的文档或条文。

Milvus collection：

- collection：`finance_policy_chunks`
- 主键：`vector_id`
- 向量字段：`embedding`
- 标量字段：`doc_id`、`chunk_text`、`region`、`category`、`status`、`article_no`
- 当前本地维度：`1536`
- 索引：`IVF_FLAT + COSINE`

## 系统如何“构图”

当前系统没有引入独立图数据库，而是在 MySQL + Milvus 中构建一张“隐式条文证据图”。图的节点和边由文档结构、条文结构、元数据和检索关系共同形成。

节点：

- `Document`：监管文件节点。
- `Chunk`：条文或语义片段节点。
- `Citation`：一次问答中的证据节点。
- `QARecord`：用户问题与系统答案节点。

边：

- `Document -> Chunk`：文档包含条文。
- `Chunk -> Vector`：条文对应 Milvus 向量。
- `Chunk -> Metadata`：条文继承文档的地区、类别、时效、机关、文号等属性。
- `Chunk -> NeighborChunk`：同一文档内相邻条文，用于关联查询。
- `Chunk -> SameArticleChunk`：跨文档同条号扩展。
- `QARecord -> Citation -> Chunk`：问答证据链。

关联查询 `/search/related` 就是基于这张隐式图做扩展：

1. 用 `doc_id/article_no/chapter/query` 定位锚点条文。
2. 扩展同文档邻接条文。
3. 扩展跨文档同条号条文。
4. 用关键词 token 补充语义相关条文。
5. 按来源和距离打分后返回 anchor 与 related citations。

## 系统如何检索

检索入口是 `POST /api/v1/search`，核心逻辑在 `RetrieverService`。

### 1. 过滤条件

先应用结构化过滤：

- `status`：默认可按有效/失效/全部过滤。
- `region`：地区。
- `source_org`：发文机关。
- `category`：制度类别。

Milvus 向量检索也会同步使用 `region/category/status` 标量过滤。

### 2. 关键词召回

关键词召回分两层：

- 精确召回：直接查 `chunk_text contains query`。
- 分词召回：把中文连续文本拆成 2-4 字短片段，再用 `contains(token)` 扩展候选。

候选内再计算 BM25-like 分数，综合词频、逆文档频率、长度归一和完整 query 命中奖励。

### 3. 向量召回

问题文本先调用 embedding 服务得到 query vector，再到 Milvus 中查 top-k 相似向量。返回的 `vector_id` 回到 MySQL 映射为完整 chunk 与 document，避免只依赖 Milvus 中截断文本。

### 4. 候选融合与重排

系统把关键词候选和向量候选按 `chunk_id` 合并，记录来源：

- `keyword`
- `vector`
- `hybrid`

最终重排分数：

```text
final_score = 0.62 * keyword_score
            + 0.30 * vector_score
            + 0.08 * status_bonus
            + hybrid_bonus
```

其中 `status_bonus` 优先现行有效制度，`hybrid_bonus` 奖励同时被关键词和向量命中的条文。

### 5. 输出证据

检索结果返回：

- `citations`：文档 ID、标题、条号、章节、正文片段、检索分、检索来源。
- `keyword_candidates`：关键词召回数量。
- `vector_candidates`：向量召回数量。
- `reranked_candidates`：融合后参与排序的候选数量。

## QA 如何保证可信

问答入口是 `POST /api/v1/qa`。流程：

1. 先检索证据条文。
2. 没有证据时直接返回 `generation_status=no_evidence`，不调用 LLM。
3. 有证据时把 top citations 截断后交给 LLM。
4. Prompt 明确要求只基于给定条文回答，依据不足要说明不确定。
5. LLM 不可用时返回 `generation_status=degraded`，不会静默伪造答案。
6. 保存 QA 历史和引用到数据库。

可信度评分由以下因素组成：

- 引用数量。
- 平均检索分。
- `consistency_score`：答案 token 与引用条文 token 的重合度。
- `evidence_coverage`：答案中的信息有多少能被证据覆盖。
- 是否命中现行有效制度。
- LLM 生成状态是否成功。

如果可信度低于阈值，答案会附加“证据较弱，需要核对原文”的提示。

## 元数据与时效识别

导入时会从标题和正文中抽取：

- 发文机关。
- 文号。
- 发布日期。
- 生效日期。
- 失效/废止日期。
- 地区。
- 类别。
- 时效状态：`effective/expired/unknown`。
- 时效证据：识别状态所依据的文本片段。

时效识别目前是规则型，优点是可解释、可追溯；局限是对隐含废止、外部链接废止和跨文件修订关系识别不充分。

## 导入流程

```mermaid
sequenceDiagram
    participant U as User/Script
    participant API as FastAPI
    participant DB as MySQL
    participant P as Pipeline
    participant E as Embedding API
    participant V as Milvus

    U->>API: upload or enqueue ingest task
    API->>DB: create documents / ingest_tasks
    U->>API: run ingest tasks
    API->>P: ingest(doc_id)
    P->>P: hash / parse / clean / metadata / chunk
    P->>DB: delete old chunks when reindex
    P->>V: delete old vectors by doc_id
    P->>E: batch embed chunks
    P->>DB: insert chunks
    P->>V: upsert vectors
    P->>DB: update document and task status
```

批量导入：

```bash
set -a
source .env.runtime
set +a
./backend/.venv/bin/python scripts/ingest_batch.py --root 金融监督管理局 --force --max-attempts 3
```

## 运行方式

### 1. 准备 Python 3.11 环境

```bash
python3.11 -m venv backend/.venv
./backend/.venv/bin/pip install -r backend/requirements.txt
./backend/.venv/bin/pip install -r backend/requirements.prod.txt
```

### 2. 启动 MySQL/Milvus

```bash
docker compose -f deploy/docker-compose.yml up -d mysql etcd minio milvus
```

### 3. 配置运行时变量

```bash
cp .env.example .env.runtime
```

本地 MySQL + Milvus 常用项：

```bash
DATABASE_URL=mysql+pymysql://rag:rag@127.0.0.1:3306/rag_finance?charset=utf8mb4
VECTOR_BACKEND=milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=finance_policy_chunks
EMBEDDING_BACKEND=api
EMBEDDING_DIMENSION=1536
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_API_KEY=<runtime-secret>
QWEN_CHAT_MODEL=<your-chat-model>
QWEN_EMBEDDING_MODEL=text-embedding-v1
```

不要提交 `.env.runtime` 或任何真实密钥。

### 4. 启动 API

```bash
set -a
source .env.runtime
set +a
PYTHONPATH=backend ./backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

### 5. 健康检查

```bash
curl http://127.0.0.1:8010/api/v1/health
```

健康检查会验证：

- MySQL 连接。
- embedding 服务与维度。
- Milvus collection、字段和维度。
- LLM 服务。

## 评测方式

固定验收评测：

```bash
./backend/.venv/bin/python scripts/evaluate_acceptance.py \
  --base-url http://127.0.0.1:8010/api/v1 \
  --timeout 30
```

输出：

- `docs/reports/acceptance_eval.json`
- `docs/reports/acceptance_eval.md`

当前评测口径：

- `success_rate`：接口请求 HTTP 200 的比例。
- `accuracy`：每道题返回文本命中至少 50% 预期关键词则计为准确。
- `recall`：所有预期关键词中的整体命中比例。

注意：当前评测不是严格 IR 标注集评测。它能证明链路可用、关键词覆盖正常，但不能完全证明检索到了人工标准答案条文。后续应补充 `gold_doc_id/gold_article_no/gold_chunk_id`，计算 `Recall@K/MRR/nDCG/引用正确率/答案要点命中率`。

## 常用接口

- `POST /api/v1/documents/upload`
- `POST /api/v1/documents/ingest`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{doc_id}`
- `PATCH /api/v1/documents/{doc_id}/tags`
- `GET /api/v1/documents/tags`
- `POST /api/v1/documents/ingest/tasks`
- `POST /api/v1/documents/ingest/tasks/run`
- `GET /api/v1/documents/ingest/tasks`
- `POST /api/v1/search`
- `POST /api/v1/search/related`
- `POST /api/v1/qa`
- `GET /api/v1/history`
- `GET /api/v1/favorites`
- `POST /api/v1/favorites`
- `GET /api/v1/health`
- `GET /api/v1/metrics`

## 创新点

- 后端优先的制度 RAG 闭环：从批量导入、解析、切分、embedding、检索、问答到评测全部可自动化运行。
- 隐式条文证据图：不引入图数据库，也能通过 `Document-Chunk-Citation-QA` 关系和邻接/同条号/关键词扩展支持条文关联查询。
- 面向制度文本的时效性识别：将发文日期、生效日期、失效关键词、文号和发文机关纳入元数据，检索和问答时优先现行有效制度。
- 混合召回与可解释重排：关键词/BM25-like 召回保证精确术语命中，Milvus 向量召回补自然语言语义，重排分中显式体现时效和 hybrid 命中。
- 可信 QA 降级机制：LLM 不可用时返回明确降级状态，不伪造答案；答案同时输出 citations、confidence、consistency、evidence coverage。
- 导入任务可观测：每个阶段记录耗时和错误，支持重试、dead 状态与批量验收。
- 结构化向量过滤：Milvus schema 包含 `region/category/status/article_no`，可在向量层过滤，减少无关候选。

## 当前局限与后续改进

- `.doc` 老格式仍可能存在 WPS/OLE 异常文件，需要引入 LibreOffice 转换或离线人工转码兜底。
- 固定评测集还缺少人工 gold chunk，需要升级为严格检索评测。
- 导入任务已增加原子 claim，能避免多消费者重复领取同一任务；如果未来高并发部署，还应进一步补充数据库级锁等待和 worker 心跳恢复。
- 当前认证鉴权仍未接入，校企项目验收可用，但正式生产应增加用户身份、接口权限和上传文件安全扫描。

## 安全要求

- 不要把真实密钥写入仓库文件。
- `.env.runtime`、上传文件、数据库文件、缓存和虚拟环境都不应提交。
- API Key 仅通过环境变量或运行时配置文件注入。
