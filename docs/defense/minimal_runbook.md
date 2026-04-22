# 最小可执行说明书

本说明面向第一次拿到代码的同伴，目标是在本机跑通后端 API、MySQL、Milvus、健康检查、检索和问答。本文只使用仓库中已有能力，不包含前端。

## 1. 前置条件

必须安装：

- Git
- Docker 和 Docker Compose
- Python 3.11
- 可访问 Qwen OpenAI-Compatible API 的网络

建议安装：

- `curl`
- `jq` 或 Python 自带 `json.tool`

系统解析依赖：

- Docker 镜像中已经安装 `antiword`、`catdoc`、`tesseract-ocr`、`tesseract-ocr-chi-sim`，见 [deploy/backend.Dockerfile](../../deploy/backend.Dockerfile)。
- 如果在宿主机直接运行批量导入，宿主机也需要具备对应解析工具，否则部分 `.doc` 或 OCR 文件可能失败。

## 2. 克隆仓库

```bash
git clone git@github.com:tuhaozhuo/finance-policy-rag.git
cd finance-policy-rag
```

如果没有配置 SSH，也可以用 HTTPS：

```bash
git clone https://github.com/tuhaozhuo/finance-policy-rag.git
cd finance-policy-rag
```

## 3. 创建 Python 3.11 虚拟环境

```bash
python3.11 -m venv backend/.venv
./backend/.venv/bin/pip install --upgrade pip
./backend/.venv/bin/pip install -r backend/requirements.txt
./backend/.venv/bin/pip install -r backend/requirements.prod.txt
```

依据：

- Python 版本约束见 [backend/pyproject.toml](../../backend/pyproject.toml)。
- Milvus 依赖 `pymilvus` 来自 [backend/requirements.prod.txt](../../backend/requirements.prod.txt)。

## 4. 启动 MySQL 和 Milvus

```bash
docker compose -f deploy/docker-compose.yml up -d mysql etcd minio milvus
```

检查容器：

```bash
docker compose -f deploy/docker-compose.yml ps
```

仓库中的 Compose 配置会启动：

- MySQL 8.0
- etcd
- MinIO
- Milvus standalone

配置依据见 [deploy/docker-compose.yml](../../deploy/docker-compose.yml)。

## 5. 准备运行时配置

复制示例配置：

```bash
cp .env.example .env.runtime
```

编辑 `.env.runtime`，至少确认以下项。不要把真实 `.env.runtime` 提交到 Git。

```bash
DATABASE_URL=mysql+pymysql://rag:rag@127.0.0.1:3306/rag_finance?charset=utf8mb4
VECTOR_BACKEND=milvus
MILVUS_HOST=127.0.0.1
MILVUS_PORT=19530
MILVUS_COLLECTION=finance_policy_chunks

RUNTIME_PROFILE=prod_qwen
EMBEDDING_BACKEND=api
EMBEDDING_DIMENSION=1536
QWEN_API_BASE=https://dashscope.aliyuncs.com/compatible-mode/v1
QWEN_API_KEY=<填你的运行时密钥>
QWEN_CHAT_MODEL=<填你的聊天模型>
QWEN_EMBEDDING_MODEL=text-embedding-v1
```

如果使用独立 embedding 服务，还需要配置：

```bash
EMBEDDING_API_BASE=<embedding OpenAI-Compatible base url>
EMBEDDING_API_KEY=<embedding key>
EMBEDDING_API_MODEL=<embedding model>
```

配置读取逻辑见 [backend/app/core/config.py](../../backend/app/core/config.py)。

## 6. 启动后端 API

```bash
set -a
source .env.runtime
set +a
PYTHONPATH=backend ./backend/.venv/bin/uvicorn app.main:app --host 127.0.0.1 --port 8010
```

不要关闭这个终端。另开一个终端执行后续检查。

## 7. 健康检查

```bash
curl -s http://127.0.0.1:8010/api/v1/health | ./backend/.venv/bin/python -m json.tool
```

期望看到：

- `database.status = ok`
- `embedding.status = ok`
- `vector_store.status = ok`
- `llm.status = ok`

健康检查实现见 [backend/app/api/v1/endpoints/health.py](../../backend/app/api/v1/endpoints/health.py)。

## 8. 导入数据

仓库不会上传原始监管文件目录。你的同伴需要自己准备制度文件目录，或用上传接口导入少量样例文件。

### 方式 A：上传一个 txt 样例并导入

```bash
curl -s -X POST http://127.0.0.1:8010/api/v1/documents/upload \
  -F "file=@sample.txt" \
  | ./backend/.venv/bin/python -m json.tool
```

返回中会有 `doc_id`。然后执行：

```bash
curl -s -X POST http://127.0.0.1:8010/api/v1/documents/ingest \
  -H "Content-Type: application/json" \
  -d '{"doc_id":"<替换为 doc_id>","force_reindex":true}' \
  | ./backend/.venv/bin/python -m json.tool
```

上传和导入接口见 [backend/app/api/v1/endpoints/documents.py](../../backend/app/api/v1/endpoints/documents.py)。

### 方式 B：批量导入目录

把制度文件放在项目根目录下的某个文件夹，例如：

```text
金融监督管理局/
```

然后运行：

```bash
set -a
source .env.runtime
set +a
./backend/.venv/bin/python scripts/ingest_batch.py --root 金融监督管理局 --force --max-attempts 3
```

批量脚本见 [scripts/ingest_batch.py](../../scripts/ingest_batch.py)。

## 9. 检索测试

```bash
curl -s -X POST http://127.0.0.1:8010/api/v1/search \
  -H "Content-Type: application/json" \
  -d '{"query":"保险公司合规管理","top_k":3,"status":"all"}' \
  | ./backend/.venv/bin/python -m json.tool
```

期望返回：

- `data.citations`
- `keyword_candidates`
- `vector_candidates`
- `reranked_candidates`

检索接口见 [backend/app/api/v1/endpoints/search.py](../../backend/app/api/v1/endpoints/search.py)。

## 10. 问答测试

```bash
curl -s -X POST http://127.0.0.1:8010/api/v1/qa \
  -H "Content-Type: application/json" \
  -d '{"question":"保险公司合规管理有哪些要求？","top_k":5}' \
  | ./backend/.venv/bin/python -m json.tool
```

期望返回：

- `answer`
- `citations`
- `confidence_score`
- `consistency_score`
- `evidence_coverage`
- `generation_status`

问答接口见 [backend/app/api/v1/endpoints/qa.py](../../backend/app/api/v1/endpoints/qa.py)。

## 11. 运行测试

```bash
cd backend
./.venv/bin/pytest -q
```

当前仓库测试覆盖 API 契约、embedding、health、LLM 降级、ingest task claim、Milvus 分数处理等，测试文件在 [backend/tests](../../backend/tests)。

## 12. 运行验收评测

需要 API 服务已启动，且已有可检索数据。

```bash
./backend/.venv/bin/python scripts/evaluate_acceptance.py \
  --base-url http://127.0.0.1:8010/api/v1 \
  --timeout 30
```

评测脚本见 [scripts/evaluate_acceptance.py](../../scripts/evaluate_acceptance.py)，固定问题集见 [data/eval/acceptance_queries.json](../../data/eval/acceptance_queries.json)。

## 13. 常见问题

### 13.1 `/health` 中 embedding degraded

检查 `.env.runtime` 中：

- `EMBEDDING_BACKEND`
- `EMBEDDING_DIMENSION`
- `QWEN_API_BASE`
- `QWEN_API_KEY`
- `QWEN_EMBEDDING_MODEL`

### 13.2 Milvus 维度不一致

切换 embedding 模型或维度后，必须重建 Milvus collection 并重新 ingest。否则会出现 collection dim 与当前 embedding dim 不一致。

### 13.3 `.doc` 解析失败

老 `.doc` 文件可能需要 `antiword/catdoc/textutil`，部分 WPS/OLE 异常文件可能仍无法解析。当前系统会把失败记录到 ingest task。

### 13.4 不要上传密钥

仓库 [.gitignore](../../.gitignore) 已忽略：

- `.env.runtime`
- `.env.*`
- 数据库文件
- 上传目录
- 虚拟环境
- 原始监管文件目录

运行时密钥只放在 `.env.runtime` 或环境变量中。
