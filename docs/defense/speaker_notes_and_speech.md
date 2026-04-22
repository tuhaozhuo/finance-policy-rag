# 答辩逐页讲稿与完整演讲稿

本文用于口头答辩准备。讲稿风格按计算机专业本科项目答辩撰写，尽量使用准确的技术术语，不夸大研究创新，不声称仓库没有支持的实验结果。

## 第一部分：逐页 Speaker Notes

### 第 1 页：标题与系统范围

**完整讲稿**

各位老师好，我的项目是“基于 RAG 的金融制度知识问答系统”。这个系统的目标是构建一个后端服务，能够导入金融监管制度文档，检索相关条文，并生成带引用依据的答案。当前版本是后端优先版本，主要覆盖文档解析、元数据抽取、条文切分、embedding、向量索引、混合检索、LLM 问答生成、QA 记录持久化、健康检查和验收评测。它目前不包含前端和认证鉴权模块，所以我会把它定位为后端验收原型，而不是完整商业产品。系统设计的核心思想是：答案必须能追溯到原始制度条文，而不是完全依赖大模型内部知识。

**过渡句**

在介绍架构之前，我先说明这个系统要解决的具体问题。

**记忆版**

这是一个面向金融制度文档的后端 RAG 系统，支持导入、检索、带引用问答、持久化和评测，是后端验收原型。

### 第 2 页：问题定义

**完整讲稿**

这个项目解决的是金融监管制度文档上的证据化问答问题。监管制度通常篇幅较长，结构半规范化，并且包含条文编号、发布日期、发文机关、文号和时效状态等信息。如果只用关键词搜索，用户必须知道文档中的准确表述；如果只用大模型直接回答，模型可能生成看似合理但没有制度依据的内容。对于监管制度场景，这是不可接受的，因为用户需要知道答案来自哪一条、哪一份文件。因此系统需要先检索相关证据，再基于证据生成答案，同时保留引用、时效和可追溯信息。

**过渡句**

这也是我选择 RAG 架构的原因。

**记忆版**

问题是做制度文档的可溯源问答。关键词搜索不够灵活，LLM 直接回答有幻觉风险，所以需要 RAG。

### 第 3 页：为什么使用 RAG

**完整讲稿**

RAG 的优势在于把知识获取和答案生成拆开。系统先检索一小批相关条文，再把这些条文作为上下文交给大模型生成答案。这样做可以降低上下文长度和 token 成本，也能让答案附带引用依据。在本仓库中，`/qa` 接口会先调用 retriever 得到 citations，再把 citations 交给 RAGService。Prompt 中明确要求模型“仅根据给定条文回答，依据不足时说明不确定”。这不能彻底消除幻觉，但比直接让大模型自由回答更可控，也更适合制度问答。

**过渡句**

下面看整个系统在工程上是如何组织的。

**记忆版**

RAG 先检索证据再生成答案，优势是可追溯、上下文更小、生成更受约束。

### 第 4 页：总体架构

**完整讲稿**

系统主要由 FastAPI、MySQL、Milvus 和 OpenAI-Compatible 模型 API 组成。FastAPI 提供 `/api/v1` 下的后端接口。MySQL 保存结构化数据，包括 documents、chunks、ingest_tasks、qa_records、qa_citations 和 favorites。Milvus 保存 chunk 的向量，用于语义检索。Embedding 和 Chat 模型都通过可配置的 OpenAI-Compatible 接口调用。这样的分层设计比较清晰：MySQL 负责可靠的结构化存储和状态记录，Milvus 负责向量相似度检索，FastAPI 负责对外暴露服务。

**过渡句**

接下来我按数据进入系统的顺序，先讲文档导入流水线。

**记忆版**

FastAPI 提供接口，MySQL 存结构化数据，Milvus 存向量，模型 API 负责 embedding 和生成。

### 第 5 页：文档导入流水线

**完整讲稿**

文档导入由 `DocumentPipelineService` 编排。它包含 hash、parse、clean、metadata、apply_metadata、vector_delete、chunk、embedding、vector_upsert 和 database_commit 等阶段。解析器支持 docx、pdf、doc、图片和普通文本，图片通过 OCR 处理。系统还有 ingest task 服务，任务状态包括 pending、running、retrying、success 和 dead。每个阶段都会记录耗时和错误信息。这一点很重要，因为真实文档导入中最容易出问题的就是解析和 embedding，所以系统需要能看到失败发生在哪个阶段，而不是只有一个模糊的失败结果。

**过渡句**

导入之后，一个关键问题是如何把长文档切成适合检索的 chunk。

**记忆版**

导入流水线负责解析、清洗、元数据、切分、embedding 和向量入库；任务状态让失败可观测。

### 第 6 页：Chunking 策略

**完整讲稿**

切分逻辑在 `Chunker` 中。系统优先使用制度文档的条文结构，也就是识别 `第X条`，同时识别 `第X章`。这种方式比较适合监管文件，因为条文天然就是引用和问答的基本单位。如果文档没有条文结构，系统会回退到固定窗口切分，默认最大长度 500 字符，重叠 80 字符。这里有一个取舍：较小的 chunk 检索精度更高，但可能丢失上下文；较大的 chunk 上下文更完整，但会增加噪声和生成成本。当前系统选择条文优先，是为了让引用更清晰。

**过渡句**

切分完成后，每个 chunk 会被转换成向量并写入 Milvus。

**记忆版**

系统优先按 `第X条` 切分，失败时窗口切分。这保证制度引用更清楚。

### 第 7 页：Embedding 与向量索引

**完整讲稿**

Embedding 模块在 `EmbeddingService` 中。API 模式下，它会对重复文本去重，批量请求 `/embeddings` 接口，按返回的 index 对齐结果，并进行维度归一和向量 L2 归一。向量写入 Milvus 的逻辑在 `VectorStoreService` 中。Milvus collection 名为 `finance_policy_chunks`，字段包括 vector_id、doc_id、chunk_text、region、category、status、article_no 和 embedding。代码里配置的索引是 IVF_FLAT，距离度量是 COSINE，并通过 nprobe 参数控制检索范围。这一部分就是系统中的 ANN 或向量检索组件。

**过渡句**

有了向量索引之后，系统就可以实现混合检索。

**记忆版**

Embedding 会批量、去重、归一化；Milvus 使用 IVF_FLAT + COSINE，支持 metadata 字段过滤。

### 第 8 页：混合检索流程

**完整讲稿**

检索逻辑由 `RetrieverService` 实现。它同时使用关键词召回和向量召回。首先应用结构化过滤，例如 status、region、source_org 和 category。关键词分支包括完整 query 命中和 token contains 召回，并在候选集合上计算 BM25-like 分数。向量分支会先把 query 转为 embedding，再到 Milvus 中检索相似向量。两路候选按 chunk_id 合并，并标记来源为 keyword、vector 或 hybrid。这种设计的原因是：监管文本既有精确术语需求，也有自然语言语义查询需求，单一路径不够稳。

**过渡句**

候选召回之后，还需要一个排序策略来决定最终返回哪些条文。

**记忆版**

检索是 keyword + vector 双路召回，结构化过滤后合并候选，并标记来源。

### 第 9 页：重排设计

**完整讲稿**

重排逻辑在 `RerankService`。它不是神经网络 cross-encoder，而是一个轻量级加权公式。最终分数由关键词分、向量分、status bonus 和 hybrid bonus 组成。关键词分权重更高，是因为制度文档中精确术语很重要；向量分补充语义匹配；status bonus 让现行有效文件更靠前；hybrid bonus 奖励同时被关键词和向量命中的候选。这个方案的优点是快、可解释、容易调试；不足是权重是启发式设定，仓库中还没有消融实验或学习式调参。

**过渡句**

排好序的 citations 会进入生成阶段，组成 Prompt。

**记忆版**

重排公式结合关键词、向量、时效和 hybrid 命中。它可解释但权重是启发式的。

### 第 10 页：生成与 Prompt 组装

**完整讲稿**

生成由 `RAGService` 和 `LLMService` 完成。QA 接口会先检索 citations，再把 citations 的 chunk_text 传给 LLMService。LLMService 会限制上下文 chunk 数量、每个 chunk 的最大字符数和总字符数。这是召回完整性和延迟之间的取舍：上下文越多，答案可能更完整，但 token 成本和响应时延也更高。Prompt 中明确要求模型只根据给定条文回答，并在依据不足时说明不确定。如果没有证据，系统直接返回 no_evidence；如果 LLM 不可用，返回 degraded 状态，而不是伪造答案。

**过渡句**

系统除了生成答案，还会输出可信度和可追溯信号。

**记忆版**

Prompt 来自 top citations，并有长度限制。无证据和 LLM 不可用都会显式降级。

### 第 11 页：可信度与可追溯

**完整讲稿**

QA 返回结果不只是 answer，还包括 citations、related_articles、confidence_score、consistency_score、evidence_coverage、generation_status 和 degraded_reason。consistency_score 基于答案和引用条文的 token 重合度，evidence_coverage 衡量答案中有多少词能被证据覆盖。它们不是严格的事实正确性证明，但可以作为透明度和调试信号。系统还会把 QA 记录和引用持久化到 MySQL，这样之后可以检查某个答案当时依据了哪些条文。

**过渡句**

接下来介绍仓库中已有的评测和实验相关内容。

**记忆版**

系统返回引用、置信度、一致性和证据覆盖率。这些是透明度信号，不是绝对正确性证明。

### 第 12 页：评测与演示

**完整讲稿**

仓库中包含 `evaluate_acceptance.py` 验收评测脚本，覆盖 search、QA、related search、timeliness 和 OCR 类型问题。指标包括 success_rate、基于关键词的 accuracy、基于关键词的 recall、平均时延和 p95 时延。这个评测能证明系统链路可运行，返回结果覆盖预期关键词。但是它不是严格的信息检索评测，因为它没有人工标注的 gold chunk。仓库还包含单元测试和契约测试，覆盖 API、embedding、vector score、ingest task claim、health 和 LLM 行为。

**过渡句**

基于这些实现，我会区分工程贡献和研究贡献。

**记忆版**

当前评测是关键词验收评测和单元测试，能证明系统可运行，但不是 gold chunk benchmark。

### 第 13 页：工程亮点与研究贡献边界

**完整讲稿**

我会把这个项目主要定位为工程型 RAG 系统。工程贡献是打通了端到端后端链路：文档导入、条文切分、embedding、Milvus 向量库、混合检索、重排、生成、引用持久化、健康检查、指标、测试和 Docker 部署。比较有研究意味的设计点包括条文感知切分、元数据感知检索、时效状态处理和证据可信度信号。但我不会声称提出了新的 ANN 算法或新的大模型方法。这个项目的价值在于把已有技术组合成一个可运行、可追溯的领域 RAG 系统。

**过渡句**

最后我说明目前系统的局限和后续改进方向。

**记忆版**

主要贡献是工程集成；研究性设计包括条文切分、元数据过滤和可信度信号，但不是新算法。

### 第 14 页：局限与未来工作

**完整讲稿**

当前系统还有几个局限。第一，仓库没有前端和认证鉴权。第二，一些异常老 `.doc` 文件仍可能解析失败，后续可以引入 LibreOffice 转换或人工转码兜底。第三，评测还缺少 gold chunk 标注和消融实验。第四，重排权重是启发式的，不是训练得到的。后续我会优先补 gold chunk 评测集，因为它能直接衡量系统是否找到了正确条文；然后再优化文档转换、前端、认证，以及在时延允许的情况下引入 cross-encoder reranker。

**过渡句**

最后总结整个项目。

**记忆版**

主要局限是前端、鉴权、异常 doc、gold chunk 评测和启发式重排。未来优先补严格评测。

### 第 15 页：总结

**完整讲稿**

总结来说，这个项目实现了一个面向金融制度文档的后端 RAG 工作流。它能把原始文件转成 chunk 和 embedding，用 MySQL 保存结构化数据，用 Milvus 保存向量，通过混合检索找到证据，经过重排后把 citations 交给 LLM 生成答案，并保存 QA 历史。当前版本适合作为后端验收原型。它的主要优势是链路完整、证据可追溯、工程上可观测。后续重点是更严格的检索评测、前端、认证和生产化加固。谢谢各位老师，欢迎提问。

**过渡句**

答辩陈述结束。

**记忆版**

系统完成了导入、检索、生成、引用、持久化和评测，是可交付的后端验收版。

## 第二部分：8 分钟完整答辩稿

各位老师好，我的项目是“基于 RAG 的金融制度知识问答系统”。

这个系统的目标是构建一个后端服务，能够导入金融监管制度文档，检索相关条文，并生成带引用依据的答案。当前版本是后端优先版本，主要覆盖文档解析、元数据抽取、条文切分、embedding、向量索引、混合检索、LLM 问答生成、QA 记录持久化、健康检查和验收评测。它目前不包含前端和认证鉴权模块，所以我会把它定位为后端验收原型，而不是完整商业产品。系统设计的核心思想是：答案必须能追溯到原始制度条文，而不是完全依赖大模型内部知识。这里暂停一下。

这个项目解决的是金融监管制度文档上的证据化问答问题。监管制度通常篇幅较长，结构半规范化，并且包含条文编号、发布日期、发文机关、文号和时效状态等信息。如果只用关键词搜索，用户必须知道文档中的准确表述；如果只用大模型直接回答，模型可能生成看似合理但没有制度依据的内容。对于监管制度场景，这是不可接受的，因为用户需要知道答案来自哪一条、哪一份文件。因此系统需要先检索相关证据，再基于证据生成答案，同时保留引用、时效和可追溯信息。

这也是我选择 RAG 架构的原因。RAG 的优势在于把知识获取和答案生成拆开。系统先检索一小批相关条文，再把这些条文作为上下文交给大模型生成答案。这样做可以降低上下文长度和 token 成本，也能让答案附带引用依据。在本仓库中，`/qa` 接口会先调用 retriever 得到 citations，再把 citations 交给 RAGService。Prompt 中明确要求模型“仅根据给定条文回答，依据不足时说明不确定”。这不能彻底消除幻觉，但比直接让大模型自由回答更可控，也更适合制度问答。

从总体架构看，系统主要由 FastAPI、MySQL、Milvus 和 OpenAI-Compatible 模型 API 组成。FastAPI 提供 `/api/v1` 下的后端接口。MySQL 保存结构化数据，包括 documents、chunks、ingest_tasks、qa_records、qa_citations 和 favorites。Milvus 保存 chunk 的向量，用于语义检索。Embedding 和 Chat 模型都通过可配置的 OpenAI-Compatible 接口调用。这样的分层设计比较清晰：MySQL 负责可靠的结构化存储和状态记录，Milvus 负责向量相似度检索，FastAPI 负责对外暴露服务。

第一个核心流程是文档导入。文档导入由 `DocumentPipelineService` 编排。它包含 hash、parse、clean、metadata、apply_metadata、vector_delete、chunk、embedding、vector_upsert 和 database_commit 等阶段。解析器支持 docx、pdf、doc、图片和普通文本，图片通过 OCR 处理。系统还有 ingest task 服务，任务状态包括 pending、running、retrying、success 和 dead。每个阶段都会记录耗时和错误信息。这一点很重要，因为真实文档导入中最容易出问题的就是解析和 embedding，所以系统需要能看到失败发生在哪个阶段，而不是只有一个模糊的失败结果。

导入之后，一个关键问题是如何切分文本。切分逻辑在 `Chunker` 中。系统优先使用制度文档的条文结构，也就是识别 `第X条`，同时识别 `第X章`。这种方式比较适合监管文件，因为条文天然就是引用和问答的基本单位。如果文档没有条文结构，系统会回退到固定窗口切分，默认最大长度 500 字符，重叠 80 字符。这里有一个取舍：较小的 chunk 检索精度更高，但可能丢失上下文；较大的 chunk 上下文更完整，但会增加噪声和生成成本。当前系统选择条文优先，是为了让引用更清晰。

切分完成后，每个 chunk 会被转换成向量。Embedding 模块在 `EmbeddingService` 中。API 模式下，它会对重复文本去重，批量请求 `/embeddings` 接口，按返回的 index 对齐结果，并进行维度归一和向量 L2 归一。向量写入 Milvus 的逻辑在 `VectorStoreService` 中。Milvus collection 名为 `finance_policy_chunks`，字段包括 vector_id、doc_id、chunk_text、region、category、status、article_no 和 embedding。代码里配置的索引是 IVF_FLAT，距离度量是 COSINE，并通过 nprobe 参数控制检索范围。这一部分就是系统中的 ANN 或向量检索组件。

检索逻辑由 `RetrieverService` 实现。它同时使用关键词召回和向量召回。首先应用结构化过滤，例如 status、region、source_org 和 category。关键词分支包括完整 query 命中和 token contains 召回，并在候选集合上计算 BM25-like 分数。向量分支会先把 query 转为 embedding，再到 Milvus 中检索相似向量。两路候选按 chunk_id 合并，并标记来源为 keyword、vector 或 hybrid。这种设计的原因是：监管文本既有精确术语需求，也有自然语言语义查询需求，单一路径不够稳。

候选召回之后，系统会进行重排。重排逻辑在 `RerankService`。它不是神经网络 cross-encoder，而是一个轻量级加权公式。最终分数由关键词分、向量分、status bonus 和 hybrid bonus 组成。关键词分权重更高，是因为制度文档中精确术语很重要；向量分补充语义匹配；status bonus 让现行有效文件更靠前；hybrid bonus 奖励同时被关键词和向量命中的候选。这个方案的优点是快、可解释、容易调试；不足是权重是启发式设定，仓库中还没有消融实验或学习式调参。

生成由 `RAGService` 和 `LLMService` 完成。QA 接口会先检索 citations，再把 citations 的 chunk_text 传给 LLMService。LLMService 会限制上下文 chunk 数量、每个 chunk 的最大字符数和总字符数。这是召回完整性和延迟之间的取舍：上下文越多，答案可能更完整，但 token 成本和响应时延也更高。Prompt 中明确要求模型只根据给定条文回答，并在依据不足时说明不确定。如果没有证据，系统直接返回 no_evidence；如果 LLM 不可用，返回 degraded 状态，而不是伪造答案。

QA 返回结果不只是 answer，还包括 citations、related_articles、confidence_score、consistency_score、evidence_coverage、generation_status 和 degraded_reason。consistency_score 基于答案和引用条文的 token 重合度，evidence_coverage 衡量答案中有多少词能被证据覆盖。它们不是严格的事实正确性证明，但可以作为透明度和调试信号。系统还会把 QA 记录和引用持久化到 MySQL，这样之后可以检查某个答案当时依据了哪些条文。

评测方面，仓库中包含 `evaluate_acceptance.py` 验收评测脚本，覆盖 search、QA、related search、timeliness 和 OCR 类型问题。指标包括 success_rate、基于关键词的 accuracy、基于关键词的 recall、平均时延和 p95 时延。这个评测能证明系统链路可运行，返回结果覆盖预期关键词。但是它不是严格的信息检索评测，因为它没有人工标注的 gold chunk。仓库还包含单元测试和契约测试，覆盖 API、embedding、vector score、ingest task claim、health 和 LLM 行为。

我会把这个项目主要定位为工程型 RAG 系统。工程贡献是打通了端到端后端链路：文档导入、条文切分、embedding、Milvus 向量库、混合检索、重排、生成、引用持久化、健康检查、指标、测试和 Docker 部署。比较有研究意味的设计点包括条文感知切分、元数据感知检索、时效状态处理和证据可信度信号。但我不会声称提出了新的 ANN 算法或新的大模型方法。这个项目的价值在于把已有技术组合成一个可运行、可追溯的领域 RAG 系统。

当前系统还有几个局限。第一，仓库没有前端和认证鉴权。第二，一些异常老 `.doc` 文件仍可能解析失败，后续可以引入 LibreOffice 转换或人工转码兜底。第三，评测还缺少 gold chunk 标注和消融实验。第四，重排权重是启发式的，不是训练得到的。后续我会优先补 gold chunk 评测集，因为它能直接衡量系统是否找到了正确条文；然后再优化文档转换、前端、认证，以及在时延允许的情况下引入 cross-encoder reranker。

总结来说，这个项目实现了一个面向金融制度文档的后端 RAG 工作流。它能把原始文件转成 chunk 和 embedding，用 MySQL 保存结构化数据，用 Milvus 保存向量，通过混合检索找到证据，经过重排后把 citations 交给 LLM 生成答案，并保存 QA 历史。当前版本适合作为后端验收原型。它的主要优势是链路完整、证据可追溯、工程上可观测。后续重点是更严格的检索评测、前端、认证和生产化加固。谢谢各位老师，欢迎提问。

## 第三部分：2 分钟精简版

各位老师好，我的项目是“基于 RAG 的金融制度知识问答系统”，它是一个后端优先的金融监管制度文档问答系统。

这个项目解决的问题是：监管制度文档长、结构复杂，而且回答必须能追溯到制度原文。单纯关键词搜索不够灵活，单纯让大模型回答又有幻觉风险。所以系统采用 RAG：先检索证据条文，再基于证据生成答案。

系统架构由 FastAPI、MySQL、Milvus 和 OpenAI-Compatible 模型 API 组成。MySQL 保存文档、chunk、导入任务、QA 记录和引用；Milvus 保存 chunk 向量。导入流程包括解析、清洗、元数据抽取、条文切分、embedding 和向量入库。

检索流程是混合检索。系统同时使用关键词召回和 Milvus 向量召回，然后按 chunk_id 合并候选，并用关键词分、向量分、时效状态和 hybrid bonus 做重排。这样可以兼顾监管文本中的精确术语和自然语言语义查询。

生成阶段中，QA 接口先拿到 citations，再把 top chunks 组装成 Prompt。Prompt 要求模型只根据给定条文回答。没有证据时返回 no_evidence，LLM 不可用时返回 degraded，不会静默伪造答案。返回结果包括 answer、citations、confidence_score、consistency_score 和 evidence_coverage。

仓库中包含验收评测脚本和单元测试。当前评测是关键词命中式验收评测，可以证明链路可运行，但还不是严格的 gold chunk benchmark。未来需要补人工标注的正确 chunk，进一步计算 Recall@K、MRR 和 nDCG。

总结来说，这个项目不是提出新算法，而是完成了一个面向金融制度文档的可运行、可追溯、可验收的 RAG 后端系统。

## 第四部分：15 个高频答辩问题与参考回答

### 1. 为什么选择 RAG，而不是直接使用大模型？

因为监管制度问答需要证据来源。RAG 先检索原文条文，再基于条文生成答案，可以返回 citations，降低无依据生成的风险。直接使用大模型无法保证答案来自本地制度库。

### 2. 为什么同时使用 MySQL 和 Milvus？

MySQL 适合保存结构化数据，例如文档元数据、chunk、任务状态、QA 记录和引用；Milvus 适合向量相似度检索。两者职责不同，所以系统同时使用。

### 3. ANN 在系统哪里体现？

ANN 或向量检索体现在 `VectorStoreService`。代码创建 Milvus `IVF_FLAT` + `COSINE` 索引，并使用 `nprobe` 参数对 embedding 字段进行向量检索。

### 4. 系统如何切分文档？

优先识别中文制度条文模式 `第X条`，同时识别 `第X章`。如果无法按条文切分，则回退到固定窗口切分，并带有 overlap。

### 5. 为什么不用语义切分？

监管制度天然有条文结构，条文切分更可解释，也更适合引用。语义切分可能改善边界，但会降低确定性和可解释性，可以作为后续增强。

### 6. 为什么要混合关键词和向量检索？

关键词检索适合精确术语、文号和条文名称；向量检索适合自然语言语义查询。两者结合可以提高鲁棒性。

### 7. 重排器如何工作？

重排器用关键词分、向量分、status bonus 和 hybrid bonus 加权得到最终分数。它是轻量级可解释公式，不是神经网络 reranker。

### 8. 重排权重是训练出来的吗？

不是。当前权重是启发式设定。仓库没有训练数据和消融实验。后续可以基于 gold chunk 评测集调参或训练 reranker。

### 9. 系统如何降低幻觉？

系统先检索 citations，再把 citations 作为上下文交给 LLM；Prompt 要求只根据给定条文回答。没有证据时不调用 LLM，LLM 不可用时返回 degraded 状态。

### 10. LLM 服务失败怎么办？

`LLMService` 会返回 degraded generation status 和明确提示，不会静默伪造答案。

### 11. confidence_score 代表什么？

它是启发式可信度分数，综合引用数量、检索分、答案和证据的一致性、证据覆盖率、生成状态和是否命中有效制度。它不是严格正确性证明。

### 12. 系统如何评测？

仓库提供 `evaluate_acceptance.py`，覆盖 search、QA、related、timeliness、OCR 等问题，计算 success_rate、关键词 accuracy、关键词 recall、平均时延和 p95 时延。

### 13. 当前评测有什么不足？

当前评测是关键词命中式验收评测，没有人工标注 gold chunk。因此不能严格证明 top-k 检索到了标准正确条文。后续应补 Recall@K、MRR、nDCG 和引用正确率。

### 14. 系统主要局限是什么？

没有前端和认证鉴权；异常老 `.doc` 仍可能解析失败；没有 gold chunk benchmark；没有大规模压测；重排权重是启发式。

### 15. 项目主要贡献是什么？

主要贡献是工程集成：实现了从文档导入、条文切分、embedding、Milvus 向量检索、混合检索、重排、带引用生成、QA 持久化到评测和部署的完整后端 RAG 流程。
