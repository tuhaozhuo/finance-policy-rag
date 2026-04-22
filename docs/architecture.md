# 金融制度 RAG 后端架构（第 4 阶段进行中）

## 分层
- 数据层：MySQL（结构化元数据）+ Milvus（向量）+ 文件目录（原文）
- 服务层：FastAPI（`/api/v1`）
- 算法层：解析、OCR、清洗、切分、Embedding、检索、生成、评分

## 目录约定
- `backend/app/api`：接口层
- `backend/app/services`：检索/问答/导入服务
- `backend/app/db`：ORM 模型、会话与建表
- `backend/app/models`：请求响应模型
- `backend/tests`：单元与契约测试
- `scripts`：导入、初始化、评测脚本
- `deploy`：Docker 与部署配置

## 导入流水线
1. 上传或注册文档（写 `documents`）
2. 解析器按类型提取文本：`doc/docx/pdf/image`
3. OCR（图片/扫描件）
4. 文本清洗（去重、空行归一）
5. 条文切分（优先按“第X条”，失败回退窗口切分）
6. 生成 embedding（默认 hash，可切 API）
7. 写 `chunks` 与 Milvus（可关闭）
8. 更新文档导入状态与哈希，实现增量跳过

## 导入任务与重试
- 新增 `ingest_tasks` 表，状态机：
  - `pending`：待执行
  - `running`：执行中
  - `retrying`：失败待重试（指数退避）
  - `success`：执行完成
  - `dead`：超过最大重试次数
- 支持 API 与脚本两种入口入队，统一使用同一任务服务消费。

## 检索策略（第 3 阶段）
- 关键词召回：优先全文命中，再按 query token 召回
- 向量召回：Milvus 可用时启用向量检索；不可用自动降级
- 重排：综合关键词分、向量分、时效状态分进行排序
- 输出包含候选统计：`keyword_candidates`、`vector_candidates`、`reranked_candidates`
- 条文关联查询：新增 `/search/related`
  - 锚点定位：按 `doc_id/article_no/chapter/query` 组合定位条文
  - 邻接扩展：同文档相邻块（`neighbor_window`）
  - 同条号扩展：跨文档同 `article_no`
  - 关键词扩展：按 query token 召回补充相关条款

## LLM 运行策略
- 本地开发：`RUNTIME_PROFILE=dev_api`
- 服务器测试：`RUNTIME_PROFILE=prod_qwen`
- 两种模式都走 OpenAI-Compatible 协议，接口层无需改动
- 生成层采用 LangChain 编排（Prompt + ChatModel + OutputParser），失败时回退原始 HTTP 调用
- 聊天与 embedding 可解耦：
  - 聊天默认走 `QWEN_*`
  - 当 `EMBEDDING_BACKEND=api` 且设置 `EMBEDDING_API_BASE/MODEL` 时，embedding 优先走独立提供方（如硅基流动）

## 问答与可信度（第 3 阶段）
- 时效性策略：
  - 默认仅检索 `effective`
  - 未命中有效条文时自动回退 `all`，并在 `effective_status_summary` 显式提示
- 可信度策略：
  - `confidence_score`：综合引用数量、检索分与答案特征
  - `consistency_score`：答案 token 与引用条文 token 的一致性重叠评分
- 性能优化：
  - 无证据场景快速返回，避免空召回时阻塞 LLM 调用
  - query embedding 缓存，减少重复问题向量化开销

## 评测脚本
- `scripts/benchmark_api.py`
  - 覆盖 `/search`、`/qa`、`/search/related`
  - 输出 `docs/reports/perf_baseline.json` 与 `docs/reports/perf_baseline.md`
  - 支持目标阈值判定：`--target-ms 2000`

## 第 4 阶段部署约定
- Docker 部署默认：
  - `RUNTIME_PROFILE=prod_qwen`
  - `QWEN_CHAT_MODEL` 建议设置为你实际可用的 Qwen3 模型 ID
- 若 embedding 走独立服务：
  - `EMBEDDING_BACKEND=api`
  - `EMBEDDING_API_BASE=https://api.siliconflow.cn/v1`
  - `EMBEDDING_API_KEY=<runtime-env>`
  - `EMBEDDING_API_MODEL=<runtime-env>`
- 密钥不入库，仅运行时注入
- 已提供 Postman 资产：`docs/postman/*.json`

## 首期接口
- `POST /api/v1/documents/upload`
- `POST /api/v1/documents/ingest`
- `PATCH /api/v1/documents/{doc_id}/tags`
- `GET /api/v1/documents/tags`
- `POST /api/v1/documents/ingest/tasks`
- `POST /api/v1/documents/ingest/tasks/run`
- `GET /api/v1/documents/ingest/tasks`
- `GET /api/v1/documents`
- `GET /api/v1/documents/{doc_id}`
- `POST /api/v1/search`
- `POST /api/v1/search/related`
- `POST /api/v1/qa`
- `GET /api/v1/history`
- `POST /api/v1/history`
- `GET /api/v1/favorites`
- `POST /api/v1/favorites`
- `GET /api/v1/health`
- `GET /api/v1/metrics`
