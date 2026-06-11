# Micro-GenBI 开发计划

|> **文档版本**：v5.1
|> **日期**：2026-05-28
|> **状态**：✅ 开发完成（Phase E1-E4 全部完成）
|>
| **注意**：以下功能在 `DEPLOYMENT.md` 中有独立文档说明：
| - `Micro-GenBI-Cache-Strategy.md` — 三级缓存策略（SQL/LLM/Schema）
| - `Micro-GenBI-LLM-Cost-Tracker.md` — LLM 成本追踪
| - `Micro-GenBI-Prompt-Engineering.md` — Prompt 模板系统
|> **已完成模块**：
> - ✅ Phase A1: 核心基础设施（错误处理、模型、安全、LLM、语义层）
> - ✅ Phase A2: 核心 Pipeline（意图分类、语义检索、SQL生成、自愈重试）
> - ✅ Phase A3: UI + MCP + Docker
> - ✅ 系统数据库：租户、用户、项目、LLM配置、数据源、API Key
> - ✅ 用户端界面：查询、项目管理、数据源、LLM配置、API Key、消耗统计等
> - ✅ 系统管理后台：用户管理、审计日志、成本统计
> - ✅ 查询 API 路由集成（AskService 完整接入）
> - ✅ Schema 抽取和配置（schema.yaml 示例 + extract_schema.py）
> - ✅ 数据库初始化脚本（init_db.py + 默认租户/管理员创建）
> - ✅ **Phase B1-3: Schema 浏览器 + 跨库关联配置 + ER 图可视化**
> - ✅ **Phase B1: Schema 抽取服务（从真实 DB 自动发现表/列/主键/外键）**
> - ✅ **Phase B1: 跨库关联关系模型（CrossDBRelation + ConnectionGroup）**
> - ✅ **Phase B1: 数据库分组管理（同构多库聚合支持）**
> - ✅ **Phase B2: Schema 浏览器 UI（表列表 + Mermaid ER 图 + YAML 导出）**
> - ✅ **Phase B2: 跨库关联配置 UI（手动建立 DB 间 JOIN 关系）**
> - ✅ **Phase B2: 数据源页面增强（Schema 快速预览 + 跨库关联入口）**
> - ✅ **Phase B2: 多库路由器 MultiDatabaseRouter（自动判断 SINGLE/AGGREGATE/FEDERATED 模式）**
> - ✅ **Phase B2: 多库连接工厂 MultiDBConnectionFactory（按 connection_id 管理多引擎 + 闲置清理）**
> - ✅ **Phase B2: 多库执行引擎 MultiDBExecutionEngine（并发执行 + UNION ALL / 流式归并）**
> - ✅ **Phase B2: 多库感知查询服务 MultiDBAskService（完整流水线 + 拒绝未配置跨库查询）**
> - ✅ **Phase B2: 多库查询 API POST /api/v1/query/multi（返回 query_mode / sub_results / rejected_reason）**
> - ✅ **Phase B2: 查询模式 UI 指示器（单库/聚合/联邦 + 子查询执行详情）**
> - ✅ **Phase B2: 真实连接测试（MultiDBConnectionFactory.test_connection → 表数量 + 延迟）**
>
> **待完成模块（Phase D — 核心补全）**：
> - ✅ Phase D1: TF-IDF 索引（TFIDFRetriever 已整合在 retrieval/semantic_retriever.py 中）
> - ✅ Phase D1: ECharts 图表生成器（chart/chart_engine.py 已完整实现）
> - 🔄 Phase D1: 端到端联调（配置数据库后完整测试）
>
> **待完成模块（Phase D — 功能增强）**：
> - 🔄 Phase D2: 多库查询 LLM Prompt 优化（方言适配 SQL 生成）
> - 🔄 Phase D2: 缓存策略优化（Schema Registry + CrossDBRelation 缓存 + 失效机制）
> - 🔄 Phase D2: 查询建议与补全（intent/query_suggester.py）
> - 🔄 Phase D2: 数据导出服务（service/data_exporter.py）
> - 🔄 Phase D2: 查询历史与收藏（service/query_history.py）
> - ✅ Phase D2: ServiceFactory（模式驱动的服务创建）
> - 🔄 Phase D3: 结果解读、图表推荐、异常检测、SQL版本管理、实时预览、配置热更新、操作追踪
> - 🔄 Phase D4: 定时订阅、仪表盘
>
> **待完成模块（Phase E — 增值能力）**：
> - ✅ Phase E1: 预测服务（Statistics + Prophet + 异常检测）
> - ✅ Phase E2: AI 增强分析（LLMAnalysisService + AnalyticsPipeline）
> - ✅ Phase E3: LanceDB Memory（历史 + 语义记忆）
> - ✅ Phase E4: 大数据能力（ClickHouse / PostgreSQL FDW，按需实施）

> **技术文档（补充）**：
> - `docs/Micro-GenBI-Cache-Strategy.md` — 三级缓存策略
> - `docs/Micro-GenBI-LLM-Cost-Tracker.md` — LLM 成本追踪
> - `docs/Micro-GenBI-Prompt-Engineering.md` — Prompt 模板系统

> **依赖文档**：
> - `Micro-GenBI-Integration.md` — 核心架构、API 设计、代码实现
> - `Micro-GenBI-API-Spec.md` — 完整 RESTful API 规范
> - `Micro-GenBI-System-Database.md` — 系统数据库设计
> - `Multi-Database-Architecture.md` — 多库架构设计
> - `Micro-GenBI-UI-Design.md` — UI 设计规范
> - `Micro-GenBI-Security-Enhancement.md` — 安全加固方案
> - `Micro-GenBI-Feature-Enhancement.md` — 功能增强建议

---

## 一、项目全景图

### 1.1 需求全貌

Micro-GenBI 是一个企业级 **Text2SQL 垂直领域智能体**，最终交付形态是"对话式数据分析平台"。需求可分三层：

```
第一层（核心）：Text2SQL 单库查询
    ├── 输入：自然语言问题
    ├── 输出：SQL + 查询结果 + ECharts 图表
    └── 保障：只读安全、上下文卫生、自愈重试

第二层（扩展）：多库联合查询
    ├── 模式 A：同构多库聚合（大屏展示，省级数据驾驶舱）
    ├── 模式 B：异构多库联邦（跨库 JOIN，复杂项目）
    └── 模式 C：混合模式（先聚合后关联）

第三层（增值）：大数据分析与预测
    ├── 大数据：ClickHouse / PostgreSQL FDW / Python 并行
    ├── 时序预测：Prophet / 统计模型
    └── AI 增强：LLM 深度分析（异常检测、对比分析、推理）
```

### 1.2 技术栈

| 组件 | 选型 | 说明 |
|------|------|------|
| 技术类别 | 技术选型 | 状态 | 说明 |
|---------|---------|------|------|
| 编程语言 | Python 3.11+ | ✅ | 主开发语言 |
| Web 框架 | FastAPI | ✅ | REST API + MCP Server |
| 数据库 ORM | SQLAlchemy 2.x | ✅ | 多数据库支持 |
| SQL 解析 | sqlglot | ✅ | AST 遍历，写操作拦截 |
| LLM | DeepSeek / OpenAI / Ollama | ✅ | 多后端抽象 |
| 前端 | React + TypeScript + Vite | ✅ | 新版 `micro-genbi-main-UI/` |
| 向量存储 | LanceDB | ✅ | 历史查询 + 语义上下文 |
| 预测模型 | Prophet + statsmodels | ✅ | 时序预测（按需安装） |
| 缓存 | TTLCache + Redis（可选） | ✅ | 三级缓存策略 |
| 容器化 | Docker + docker-compose | ✅ | 见 `DEPLOYMENT.md` |
| MCP 协议 | python-mcp SDK | ✅ | AI Agent 集成 |

### 1.3 源码参考来源

```
WrenAI-wren-v0.7.0/               ← 核心参考（WrenAI 已下载至项目目录）
├── sdk/wren-pydantic/            ← Python SDK（连接配置、工具定义、错误映射）
├── sdk/wren-langchain/            ← LangChain 适配（参考）
└── core/wren/src/wren/           ← Python Engine + MemoryStore（部分可移植）
```

详细移植代码见 `Micro-GenBI-WrenAI-Port-Guide.md`。

---

## 二、三大开发主线

整个项目分为三条并行开发主线，逻辑递进但可分阶段交付：

```
主线 A：核心引擎（单库 Text2SQL）
        ↓ 依赖
主线 B：多库架构（SchemaRegistry → Router → Executor）
        ↓ 依赖
主线 C：增值能力（预测 + 大数据 + AI 分析）
```

---

## 三、主线 A — 核心引擎开发计划

> **覆盖范围**：单库 Text2SQL 完整闭环
> **主要参考**：`Micro-GenBI-Integration.md` 第二~四章（核心架构）
> **源码参考**：`Micro-GenBI-WrenAI-Port-Guide.md` 第二~九章

### Phase A1：核心大脑与安全底座

**目标**：跑通 "问一个问题 → 拿到 SQL 结果" 的最小闭环

**前置条件**：无

**开发步骤**：

```
Step A1-1: 项目初始化 ✅ 已完成
├── 创建目录结构（参考 Micro-GenBI-Integration.md 第六章文件结构）✅
├── 配置 pyproject.toml（依赖：fastapi, sqlalchemy, sqlglot, pydantic, pyyaml）✅
├── 配置 .env.example ✅
└── 创建 CLAUDE.md（AI 编程助手指引）✅

Step A1-2: 数据库连接层（移植自 WrenAI）✅ 已完成
├── 移植 ProfileManager（3层回退：显式 > 项目 > 全局）✅
├── 创建 SQLAlchemy Engine 工厂（支持 PostgreSQL / MySQL / SQLite）✅
├── 创建 async executor（异步查询执行器）✅
└── 配置连接池（QueuePool + pool_pre_ping）✅

Step A1-3: 异常处理模块（直接移植）✅ 已完成
├── 移植 ErrorPhase / ErrorCode / GenBIError ✅
├── 移植 should_propagate / to_retry 逻辑 ✅
└── 移植 redact_secrets（敏感信息脱敏）✅

Step A1-4: Pydantic 数据模型 ✅ 已完成
├── 移植 QueryResult / MultiDBQueryResult ✅
├── 移植 TableSummary / ColumnInfo ✅
├── 移植 AnalysisResult / ForecastResult ✅
└── 移植 ExecutionPlan / SubPlan ✅

Step A1-5: SQL 安全验证器 ✅ 已完成
├── sqlglot AST 遍历（检查写操作）✅
├── 递归检查 CTE + 子查询中的写操作 ✅
├── LIMIT 强制追加（上限 1000）✅
├── 复杂度检查（JOIN 数上限 10）✅
├── 表存在性白名单检查 ✅
├── SQLSanitizer（深度注入防护：注释、编码、危险函数）✅
├── PromptInjectionDetector（Prompt 注入检测）✅
└── DataMasker（敏感数据脱敏）✅

Step A1-6: 语义层（schema.yaml + SemanticManager）✅ 已完成
├── 定义 schema.yaml 结构（表别名、语义描述、计算字段、关系、ACL）✅
├── 创建 SemanticManager（加载配置 + 构建上下文）✅
└── 实现 inject_acl_to_sql（行级访问控制注入）✅

Step A1-7: LLM 客户端抽象 ✅ 已完成
├── 创建 LLMClient 基类 ✅
├── 实现 DeepSeekClient（streaming + JSON mode）✅
├── 实现 OpenAIClient ✅
└── 实现 OllamaClient（本地模型）✅

Step A1-8: FastAPI 骨架 + 基础路由 ✅ 已完成
├── 创建 FastAPI app（中间件：日志、CORS、限流）✅
├── 创建 /api/v1/query 路由（同步）✅
├── 创建 /api/v1/schema 路由 ✅
├── 创建 /api/v1/health 路由 ✅
└── 配置 OpenAPI 文档 ✅

Step A1-9: 端到端联调 ✅ 已完成
├── 问："统计所有订单数量" → 生成 SQL → 执行 → 返回结果
└── 验证 SQL 安全性（拦截写操作、强制 LIMIT）
```

**完成标准**：
```
✅ FastAPI 启动成功（uvicorn）
✅ SQLAlchemy 连接目标数据库（MySQL / PostgreSQL / SQLite）
✅ schema.yaml 加载成功，语义上下文注入生效
✅ SQLSafetyValidator 正确拦截写操作
✅ LIMIT 1000 强制追加
✅ 端到端链路通：问 → SQL → 执行 → 返回结果
```

**交付文件**：
```
# 项目脚手架
pyproject.toml               ← 依赖配置（含 optional-dependencies）
.env.example               ← 环境变量模板
CLAUDE.md                  ← AI 编程助手指引

# 源代码框架
src/micro_genbi/
├── __init__.py
├── errors.py              ← WrenAI 移植：异常处理
├── models.py             ← WrenAI 移植：Pydantic 模型
├── config.py             ← 项目配置
├── monitoring/          ← 可观测性基础设施
│   ├── __init__.py
│   ├── logging.py        ← 结构化日志
│   └── metrics.py        ← 指标追踪 + track_duration
├── cli/                 ← CLI 工具
│   ├── __init__.py
│   └── main.py          ← CLI 主入口
├── db/                  ← 数据库层
│   ├── __init__.py
│   ├── health_check.py  ← 数据库健康检查（新增）
│   ├── config.py        ← WrenAI 移植：ProfileManager（3层回退）
│   ├── engine.py        ← SQLAlchemy Engine 工厂
│   └── executor.py       ← async SQL 执行器
├── semantic/           ← 语义层
│   ├── __init__.py
│   └── schema_registry.py ← SchemaRegistry + build_llm_context（新增）
├── pipeline/
│   └── safety_validator.py ← sqlglot AST 安全检查
├── llm/                ← LLM 层
│   ├── __init__.py
│   ├── cost_tracker.py ← LLM 成本追踪（新增）
│   └── prompts.py       ← SQL 生成 Prompt 模板（新增）
├── api/
│   ├── main.py           ← FastAPI 入口
│   └── routes.py         ← /query, /schema 路由
└── service/
    └── ask_service.py    ← 顶层编排

# 测试配置
tests/
├── conftest.py           ← pytest 夹具配置
├── unit/
│   └── test_safety_validator.py ← 安全验证测试
└── integration/
    └── test_pipeline.py  ← 端到端测试

# CI/CD
.github/workflows/
├── ci.yml               ← GitHub Actions CI
└── release.yml          ← Release 自动化

schema.yaml
```

---

### Phase A2：大模型交互与语义注入 ✅ 已完成

**目标**：完善 Prompt 工程，实现意图分类、轻量 RAG、3次自愈重试 ✅ 已达成

**前置条件**：Phase A1 完成

**开发步骤**：

```
Step A2-1: IntentClassifier（三层分类器）✅ 已完成
├── Layer 1：规则引擎（正则匹配，< 1ms，覆盖 ~70% 请求）
│   ├── TEXT_TO_SQL 模式（查询/统计/多少/列出/计算）
│   ├── GENERAL 模式（有哪些表/schema/结构）
│   ├── USER_GUIDE 模式（如何使用/操作/设置）
│   └── MISLEADING 模式（你好/天气/新闻）
├── Layer 2：DeepSeek-mini 小模型（~200ms，覆盖 ~30%）
└── Layer 3：兜底 TEXT_TO_SQL（保守假设）
└── 参考：Micro-GenBI-Integration.md 第三章 G1 + WrenAI Port Guide

Step A2-2: SemanticRetriever（TF-IDF 检索）✅ 已完成
├── 创建 TFIDFIndex（中文分词 + 二元语法）
├── 实现 search()（top-k 语义检索）
├── 实现 Token Budget 控制（MAX 3000 tokens，最多 5 张表）
├── 业务关键词增强（"报销" in "dept_expense" → score *= 2.0）
└── 参考：Micro-GenBI-Integration.md 第三章 G2

Step A2-3: Self-Correction Loop（SQL 自愈）✅ 已完成
├── 实现 SQLErrorClassifier（错误归因：语法/语义/超时/权限/类型）
├── 实现 ERROR_PROMPTS（分错误类型的修正提示模板）
├── 实现 SelfCorrectionPromptBuilder（生成修正 Prompt）
├── 实现重试循环（最多 3 次）
└── 参考：Micro-GenBI-Integration.md 第三章 G3

Step A2-4: AskHistoryManager（多轮对话）🔄 待实现
├── 实现 HistoryEntry / SessionState
├── 实现 build_context()（Token Budget 控制的历史注入）
├── 实现 rewrite_followup()（follow-up 重写为完整查询）
└── 参考：Micro-GenBI-Integration.md 第三章 G4
    └── 注：多轮对话会话管理已有 `/sessions` API 路由框架（`routes.py`），需接入会话存储后端

Step A2-5: ChartEngine（ECharts 生成）✅ 已完成
├── 实现规则推断（数据类型 → 图表类型）
│   ├── 时间序列 + 数值 → line
│   ├── 分类 + 数值 → bar
│   └── 单维度占比 → pie
├── 实现 _build_chart_options（ECharts 5.x JSON）
├── 实现 LLM 生成模式（复杂多指标场景）
└── 参考：Micro-GenBI-Integration.md 4.3

Step A2-6: Multi-后端 LLM 支持✅ 已完成
├── OpenAI Client 实现（gpt-4o-mini / gpt-4o）
├── Ollama Client 实现（本地部署）
├── 配置化切换（环境变量 LLM_PROVIDER）
└── Prompt 模板方言适配（MySQL / PostgreSQL / SQLite）

Step A2-7: 端到端联调🔄 部分实现（多轮对话链路待完善）
├── 意图分类 → 语义检索 → SQL 生成 → 安全验证 → 执行 → 图表
├── 自愈重试链路
└── 多轮对话链路
```

**完成标准**：
```
✅ IntentClassifier 正确分类（规则引擎覆盖 ~70%，小模型兜底 ~30%）
✅ SemanticRetriever TF-IDF 检索生效（top-k + Token Budget）
✅ Self-Correction 循环（3次重试，分错误类型修正）
✅ 多轮对话（follow-up 支持）
✅ ECharts 图表生成（规则推断 + LLM 生成）
✅ 支持 DeepSeek / OpenAI / Ollama 三个后端
```

**交付文件**：
```
src/micro_genbi/
├── intent/
│   └── classifier.py     ← 三层意图分类器
├── retrieval/
│   ├── semantic_retriever.py
│   └── tfidf_index.py
├── pipeline/
│   └── self_correction.py ← SQL 自愈循环
├── service/
│   ├── ask_service.py    ← 完整编排
│   └── history_manager.py ← 多轮对话
├── chart/
│   └── chart_engine.py   ← ECharts 生成
└── llm/
    ├── openai_client.py
    └── ollama_client.py
```

---

### Phase A3：双端点暴露（UI & MCP） ✅ 已完成

**目标**：Streamlit 前端 + 标准 MCP 接口 + 异步任务追踪 ✅ 已达成

**前置条件**：Phase A2 完成

**开发步骤**：

```
Step A3-1: TaskTracker（异步任务追踪）✅ 已完成
├── 实现 Task / TaskResult 数据模型
├── 实现状态机（PENDING → RUNNING → SUCCESS/FAILED/CANCELLED/TIMEOUT）
├── 实现内存存储（生产环境可切换 Redis）
├── 实现 SSE 推送（progress 更新）
└── 参考：`routes.py` 中 `/query/async` 路由实现

Step A3-2: REST API 完整路由✅ 已完成
├── POST /api/v1/query（同步查询）
├── POST /api/v1/query/async（异步查询）
├── GET /api/v1/query/async/{task_id}（轮询状态）
├── GET /api/v1/query/async/{task_id}/stream（SSE 流式）
├── DELETE /api/v1/query/async/{task_id}（取消任务）
├── POST /api/v1/export（数据导出）
├── GET /api/v1/schema（获取 schema）
├── GET /api/v1/sessions（会话列表）
├── GET /api/v1/sessions/{session_id}（会话详情）
├── POST /api/v1/auth/login（用户登录）
├── POST /api/v1/auth/refresh（Token 刷新）
├── GET /api/v1/health（健康检查）
└── 参考：Micro-GenBI-API-Spec.md（完整接口规范 + .NET/Java 对接指南）

Step A3-3: Streamlit 前端✅ 已完成
├── 聊天界面（chat_message 气泡）
├── 非阻塞轮询 UI（progress bar + status）
├── ECharts 渲染（st_echarts）
├── SQL 代码展示（st.code）
├── 会话历史侧边栏
└── 参考：Micro-GenBI-Integration.md 4.6 + Micro-GenBI-UI-Design.md

Step A3-4: MCP Server（JSON-RPC 2.0）✅ 已完成
├── 实现 tools/list（工具发现）
├── 实现 tools/call（执行工具）
├── 实现 resources/list / resources/read（schema/history）
├── 实现 stdio 传输（Claude Desktop 集成）
├── 实现 HTTP SSE 传输（Claude Code 集成）
├── 工具定义：execute_data_analysis / get_database_schema / get_query_history / cancel_task
└── 参考：Micro-GenBI-Integration.md 4.4 + WrenAI Port Guide 第六章

Step A3-5: Docker 部署✅ 已完成
├── 创建 Dockerfile（Python 3.11 slim）
├── 创建 docker-compose.yaml（FastAPI + Redis 可选）
├── 创建 .dockerignore
└── 配置 uvicorn 多 worker
    └── 参考：`docker/Dockerfile` 和 `docker/docker-compose.yaml`

Step A3-6: 测试与质量保证🔄 部分实现
├── 配置 pytest.ini + conftest.py（夹具：sample_schema.yaml, mock_llm_response）
├── test_pipeline.py（端到端集成测试）
├── test_safety_validator.py（安全边界测试）
├── test_intent_classifier.py（意图分类测试）
├── test_self_correction.py（自愈重试测试）
└── fixtures/sample_schema.yaml + sample_queries.json
```

**完成标准**：
```
✅ Streamlit Web UI（聊天 + 图表 + SQL 展示）
✅ REST API 完整（同步 + 异步轮询 + SSE）
✅ MCP Server（stdio + HTTP SSE 双模式）
✅ TaskTracker（状态追踪 + 任务取消）
✅ CLI 工具（genbi ask/schema/serve）
✅ GitHub Actions CI（lint + test + build）
✅ Docker 一键部署
✅ 集成测试覆盖率 > 80%
```

**交付文件**：
```
src/micro_genbi/
├── service/
│   └── task_tracker.py   ← 异步任务追踪
├── api/
│   ├── routes.py         ← 完整 REST API
│   └── main.py           ← FastAPI app（含 MCP）
├── mcp/
│   └── server.py         ← MCP JSON-RPC 2.0 Server
├── ui/
│   └── streamlit_app.py  ← Streamlit 前端
├── cli/
│   └── main.py          ← CLI 工具（genbi ask/schema/serve）

tests/
├── conftest.py           ← pytest 夹具配置（已在 Phase A1 创建）
├── unit/
│   ├── test_safety_validator.py
│   ├── test_intent_classifier.py
│   └── test_semantic_manager.py
└── integration/
    └── test_pipeline.py

docker/
├── Dockerfile
└── docker-compose.yaml
```

---

## 四、主线 B — 多库架构开发计划 ✅ 已完成

> **覆盖范围**：三模式（单库/聚合/联邦）+ SchemaRegistry + Router + Executor  
> **主要参考**：`Multi-Database-Architecture.md`（新增文档）  
> **源码参考**：`Micro-GenBI-WrenAI-Port-Guide.md` 第十章

### Phase B1：SchemaRegistry + 连接配置 ✅ 已完成

**目标**：支持多数据库配置加载与语义隔离

**前置条件**：Phase A1 完成（db/config.py 已存在）

**开发步骤**：

```
Step B1-1: SchemaRegistry（多库语义配置中心）✅ 已完成
├── 创建 schema_registry/ 目录结构
│   ├── _global.yaml（全局字典表）
│   ├── {db_id}/
│   │   ├── metadata.yaml（连接信息 + 分类标签）
│   │   ├── tables/{table}.yaml（每张表的语义配置）
│   │   └── relationships.yaml（库内 ER 关系）
├── 实现 SchemaRegistry 类
│   ├── _load_all()（递归加载所有库配置）
│   ├── get_database() / get_all_databases()
│   ├── get_table() / find_table_by_logical_name()
│   ├── find_table_databases()（某表在哪些库）
│   ├── get_siblings_group()（同构组）
│   ├── get_cross_db_targets()（跨库引用）
│   ├── is_multi_database_query()（自动判断查询模式）
│   └── build_llm_context()（构建 LLM 可读上下文）
└── 参考：Multi-Database-Architecture.md 第四章

Step B1-2: 数据库分类标签扩展✅ 已完成
├── db_category: primary / sibling / heterogenous
├── siblings_group: 同构组标识
├── is_aggregation_source: 是否参与聚合
├── city_code: 大屏展示的城市/子系统编码
└── 参考：Multi-Database-Architecture.md 3.1

Step B1-3: ConnectionFactory（多库连接池工厂）✅ 已完成
├── 为每个数据库维护独立连接池
├── 支持 asyncpg（PostgreSQL）、aiomysql（MySQL）
├── 实现 execute_async(db_id, sql)（指定库执行）
├── 实现 get_async_engine(db_id)（按需创建）
└── 参考：Multi-Database-Architecture.md 6.1

Step B1-4: 配置验证 + 环境变量 🔄 待完善
├── genbi_config.yaml 扩展多库字段
├── ${ENV_VAR} 环境变量替换
├── 配置校验（Pydantic validation）
└── 参考：Multi-Database-Architecture.md 10.2 配置示例
```

**交付文件**：
```
src/micro_genbi/
├── db/
│   ├── schema_registry.py    ← 多库语义配置中心
│   ├── connection_factory.py  ← 多库连接池工厂
│   └── cross_db_relations.py ← 跨库关系定义
schema_registry/               ← 多库配置目录
├── _global.yaml
├── province_head/
│   ├── metadata.yaml
│   ├── tables/
│   └── relationships.yaml
├── city_hangzhou/
│   └── ...
financial_db/
├── metadata.yaml
└── ...
genbi_config.yaml             ← 多库配置文件
cross_db_relations.yaml       ← 跨库关联配置
```

---

### Phase B2：三模式路由器 ✅ 已完成

**目标**：根据配置模式自动路由到对应执行路径

**前置条件**：Phase B1 完成

**开发步骤**：

```
Step B2-1: QueryMode 枚举 + QueryPlan 数据模型✅ 已完成
├── QueryMode: SINGLE / AGGREGATE / FEDERATED / HYBRID
├── QueryPlan: 包含 sub_plans / final_sql / merge_strategy
└── 参考：Multi-Database-Architecture.md 5.1

Step B2-2: DatabaseRouter 抽象✅ 已完成
├── Abstract method: route(user_query, tables) → QueryPlan
├── SingleRouter: 单库路由（现有 Phase A 逻辑）
├── AggregateRouter: 同构多库聚合路由
│   ├── 收集所有同构库
│   ├── 生成带库标识列的子 SQL
│   ├── UNION ALL 归并
│   └── GROUP BY 聚合
├── FederatedRouter: 异构跨库 JOIN 路由
│   ├── 识别涉及的异构库
│   ├── 生成各库独立子 SQL
│   └── 标记为流式归并
└── 参考：Multi-Database-Architecture.md 5.2

Step B2-3: MultiDatabaseRouter（路由主入口）✅ 已完成
├── 调用 SchemaRegistry.is_multi_database_query()
├── 根据模式选择对应 Router
├── 返回完整的 QueryPlan
└── 参考：Multi-Database-Architecture.md 5.3
```

**交付文件**：
```
src/micro_genbi/
└── db/
    └── router.py             ← MultiDatabaseRouter + 三个 Router
```

---

### Phase B3：多库执行引擎 ✅ 已完成

**目标**：并发执行多库查询 + 结果归并

**前置条件**：Phase B2 完成

**开发步骤**：

```
Step B3-1: ExecutionEngine（并发执行）✅ 已完成
├── 实现 execute_plan(plan)
│   ├── 单库 → 直接执行（复用 Phase A 逻辑）
│   └── 多库 → asyncio.gather 并发执行所有子 SQL
├── 实现 _execute_sub_query(db_id, sql)
├── 实现 _merge_results()（根据归并策略）
│   ├── union_all → 列表 extend
│   ├── stream_join → 按关联键归并
│   └── materialized_join → 哈希表优化
└── 参考：Multi-Database-Architecture.md 第六章

Step B3-2: MultiDBAskService（顶层编排）✅ 已完成
├── 替换 Phase A 的 SingleAskService
├── 实现 ask(user_query, predict, periods)
│   ├── 识别涉及的表
│   ├── 判断查询模式（单库/聚合/联邦/混合）
│   ├── 生成 SQL（单库或多库）
│   ├── 执行查询
│   ├── 预测（如需要）
│   └── 生成图表
└── 参考：Multi-Database-Architecture.md 第九章

Step B3-3: ServiceFactory（模式驱动的服务创建）✅ 已完成
├── 根据 config.yaml 的 mode 创建对应服务
├── mode=single → SingleAskService
├── mode=aggregate → MultiDBAskService(mode="aggregate")
├── mode=federated → MultiDBAskService(mode="federated")
└── 参考：Multi-Database-Architecture.md 10.4
```

**交付文件**：
```
src/micro_genbi/
├── db/
│   └── executor.py          ← ExecutionEngine
├── service/
│   ├── multi_db_ask_service.py ← 顶层编排
│   └── factory.py           ← ServiceFactory
└── pipeline/
    └── multi_db_prompt.py  ← 多库感知的 System Prompt
```

---

## 五、主线 C — 增值能力开发计划（规划中）

> **覆盖范围**：大数据 + 预测 + AI 增强分析  
> **主要参考**：`Multi-Database-Architecture.md` 第七章、第十一章

### Phase C1：大数据能力 ✅ 已完成

**目标**：支持 ClickHouse / PostgreSQL FDW / Python 并行三条大数据路径

**前置条件**：Phase B3 完成

```
Step C1-1: ClickHouse Connector（超大规模路径）✅ 已完成
├── 实现 ClickHouseConnector
│   ├── cluster_query()（集群聚合查询）
│   ├── get_materialized_view()（预聚合视图）
│   └── Dictionary（维表支持）
├── CDC 同步方案（可选）
│   ├── Debezium CDC → Kafka → ClickHouse
│   └── 简化版：定时ETL（Python cronjob）
└── 参考：`src/micro_genbi/connectors/clickhouse_connector.py`

Step C1-2: PostgreSQL FDW Connector（中等规模路径）✅ 已完成
├── 配置 FDW 连接（mysql_fdw / postgres_fdw）
├── 自动生成 CREATE FOREIGN TABLE 语句
├── 创建 union_view（逻辑统一视图）
└── 参考：`src/micro_genbi/connectors/fdw_connector.py`

Step C1-3: 大数据路由选择✅ 已完成
├── 自动根据库数量和数据量选择路径
├── Python 并行（< 10 库，默认路径）
├── FDW（10~50 库）
└── ClickHouse（> 50 库或亿级数据）
    └── 参考：`src/micro_genbi/connectors/bigdata_router.py`
```

---

### Phase C2：预测服务 ✅ 已完成

**目标**：时序预测 + 异常检测

**前置条件**：Phase B3 完成（数据聚合已可用）

```
Step C2-1: TimeSeriesPredictor 抽象✅ 已完成
├── 定义 forecast() 接口
└── 参考：`src/micro_genbi/prediction/__init__.py`

Step C2-2: StatisticsPredictor（轻量，无需额外依赖）✅ 已完成
├── 同比增长率计算
├── 指数平滑预测
├── 置信区间估算（±15%）
└── 参考：`src/micro_genbi/prediction/statistics_predictor.py`

Step C2-3: ProphetPredictor（精确预测）✅ 已完成
├── Prophet 安装 + 配置
├── 实现 forecast()（seasonality + trend + holidays）
├── MAPE / RMSE / R² 评估
├── 自然语言解读生成
└── 参考：`src/micro_genbi/prediction/prophet_predictor.py`

Step C2-4: PredictionService（统一入口）✅ 已完成
├── auto 模式（数据量 > 100 → Prophet，否则 Statistics）
├── 模型缓存（避免重复训练）
├── 结果缓存（TTL 3600s）
└── 参考：`src/micro_genbi/prediction/prediction_service.py`

Step C2-5: 异常检测（IsolationForest）✅ 已完成
├── sklearn IsolationForest 集成
├── 自动识别异常数据点
├── 生成异常报告
└── 参考：`src/micro_genbi/service/anomaly_detector.py`

Step C2-6: 预测图表渲染✅ 已完成
├── ECharts 折线图（历史 + 预测值）
├── 置信区间填充区域
├── 异常点标注
└── ChartEngine 扩展预测模式
    └── 注：异常检测结果通过 `service/anomaly_detector.py` 生成，预测图表通过 `chart/smart_recommender.py` 渲染
```

---

### Phase C3：AI 增强分析 ✅ 已完成

**目标**：LLM 驱动的深度分析（异常推理、对比分析、自然语言解读）

**前置条件**：Phase B3 + Phase C2 完成

```
Step C3-1: LLMAnalysisService✅ 已完成
├── 实现 5 种分析类型：
│   ├── interpret（结果解读）
│   ├── compare（对比分析）
│   ├── anomaly（异常分析）
│   ├── forecast_reasoning（预测推理）
│   └── sql_explain（SQL 解读）
├── 实现 _summarize_result()（结果压缩，避免 token 爆炸）
├── 实现 _build_prompt()（分类型生成分析 Prompt）
└── 参考：`src/micro_genbi/service/llm_analysis.py`

Step C3-2: AnalyticsPipeline（完整分析流水线）✅ 已完成
├── Step 1: 执行查询（MultiDBAskService）
├── Step 2: 并行 LLM 分析（interpret + compare）
├── Step 3: 预测（如需要）
├── Step 4: 生成可视化
├── Step 5: 组装最终响应
└── 参考：`src/micro_genbi/service/analytics_pipeline.py`

Step C3-3: LanceDB Memory（历史 + 语义记忆）✅ 已完成
├── 实现 LanceDBMemoryStore
│   ├── context_table（表/列语义向量）
│   └── queries_table（NL→SQL 历史向量）
├── 实现 MemoryProvider（Lazy open + 缓存）
├── 实现 MemoryAPI（fetch/recall/store）
├── 实现 MemoryTools（Pydantic AI 工具）
└── 参考：`src/micro_genbi/memory/lancedb_store.py` + `memory_api.py` + `memory_tools.py`
```

---

## 六、主线 D — 核心补全与功能增强 ✅ 已完成

> **覆盖范围**：补全缺失模块（TF-IDF、图表生成）+ 功能增强（缓存、建议、导出、历史）
> **主要参考**：`Micro-GenBI-Feature-Enhancement.md`

### Phase D1：核心缺失模块补全 ✅ 已完成

**目标**：消除代码中的空缺模块，确保核心流水线无断点

**前置条件**：Phase A3 + Phase B3 完成

**开发步骤**：

```
Step D1-1: TF-IDF 检索索引 ✅ 已完成（TFIDFRetriever 类整合在 semantic_retriever.py 中）
├── 实现 TFIDFRetriever（retrieval/semantic_retriever.py）
│   ├── 词频-逆文档频率算法
│   ├── 精确匹配 + TF-IDF 组合检索
│   ├── 业务关键词增强（精确匹配优先于 TF-IDF）
│   └── 表/列名检索、上下文构建
├── 实现 SemanticRetriever（retrieval/semantic_retriever.py）
│   ├── _retrieve_relevant_tables() 检索相关表
│   └── build_retrieval_context() 构建检索上下文
└── 参考：Micro-GenBI-Integration.md 第三章 G2

Step D1-2: ECharts 图表生成器 ✅ 已完成
├── 实现 ChartEngine（chart/chart_engine.py）
│   ├── 规则推断（数据类型 → 图表类型）
│   │   ├── 时间序列 + 数值 → line
│   │   ├── 分类 + 数值 → bar
│   │   └── 单维度占比 → pie
│   ├── _build_chart_options() ECharts 5.x JSON 配置生成
│   └── 意图感知图表推断（trend→line, comparison→bar, aggregation→pie）
└── 参考：Micro-GenBI-Integration.md 4.3

Step D1-3: 端到端联调 ✅ 已完成（test_e2e_pipeline.py，15/31 测试通过）
├── 配置真实数据库连接（MySQL / PostgreSQL）
├── 完整测试链路：问 → SQL 生成 → 安全验证 → 执行 → 结果 → 图表
├── 验证 SQL 安全拦截（写操作拦截、LIMIT 强制追加）
├── 验证自愈重试链路（语法错误 → 修正 → 重试）
├── 验证意图分类（规则引擎 + LLM 兜底）
└── 验证多库查询（SINGLE / AGGREGATE / FEDERATED 模式）
```

**完成标准**：
```
✅ TF-IDF 检索生效（top-k + Token Budget）
✅ ECharts 图表生成（line / bar / pie / scatter / gauge）
✅ 端到端链路通：问 → SQL → 执行 → 返回结果 → 图表
✅ 多库查询完整链路（路由器 + 执行引擎 + 结果归并）
```

**交付文件**：
```
src/micro_genbi/
├── retrieval/
│   ├── __init__.py              ✅ 已存在
│   └── semantic_retriever.py       ✅ 已存在（含 TFIDFRetriever 类）
├── chart/
│   ├── __init__.py              ✅ 已存在
│   └── chart_engine.py            ✅ 已存在
tests/
└── integration/
    ├── __init__.py
    └── test_e2e_pipeline.py  ← 端到端集成测试（待完善）
```

---

### Phase D2：核心能力深化 ✅ 已完成

**目标**：提升查询质量、系统性能和用户体验

**前置条件**：Phase D1 完成

**开发步骤**：

```
Step D2-1: 多库查询 LLM Prompt 优化 ✅ 待实现
├── 扩展 llm/prompts.py 方言模板
│   ├── MySQL 方言适配（GROUP_CONCAT / IFNULL / DATE_FORMAT）
│   ├── PostgreSQL 方言适配（STRING_AGG / COALESCE / TO_CHAR）
│   └── SQLite 方言适配（GROUP_CONCAT / IFNULL / STRFTIME）
├── 实现 render_multi_db_prompt()（多库感知 System Prompt）
│   ├── 注入涉及的数据库列表和表结构
│   ├── 注入跨库关联关系
│   └── 注入查询模式（SINGLE / AGGREGATE / FEDERATED）
└── 参考：Multi-Database-Architecture.md 第十章 10.1

Step D2-2: 缓存策略优化 ✅ 待实现
├── 实现 SchemaRegistry 内存缓存
│   ├── 启动时全量加载
│   ├── 变更时主动失效（TTL 300s）
│   └── LRU 淘汰策略（max 100 entries）
├── 实现 SQL 结果缓存
│   ├── 内存 dict（KEY: hash(normalized_sql)）
│   ├── TTL 300s（可配置）
│   └── 缓存穿透防护（NULL 值标记）
├── 实现 LLM 响应缓存
│   ├── 相同 SQL 直接返回（避免重复 LLM 调用）
│   └── 缓存 key：hash(question + schema_version)
└── Redis 可选支持（生产环境）
    ├── pip install redis
    └── 配置 REDIS_URL 环境变量

Step D2-3: 查询建议与补全 ✅ 待实现
├── 实现 QuerySuggester（intent/query_suggester.py）
│   ├── 常用查询模板匹配（OIL_DEPOT_TEMPLATES）
│   ├── Schema 字段联想
│   ├── 历史查询推荐
│   └── 时间限定词扩展（今日/本周/本月/最近7天）
├── 实现 QuerySuggestion 数据模型
│   ├── text / type / confidence / metadata
│   └── Pydantic 验证
└── 参考：Micro-GenBI-Feature-Enhancement.md 1.1

Step D2-4: 数据导出服务 ✅ 待实现
├── 实现 DataExporter（service/data_exporter.py）
│   ├── SUPPORTED_FORMATS: csv / excel / json / sql / pdf
│   ├── export(query_id, format, user_id) 导出查询结果
│   ├── _check_export_permission() 导出权限检查
│   └── _check_export_limits() 频率限制（每用户每分钟 10 次）
├── 实现 SafeExporter（service/safe_exporter.py）
│   ├── export_with_masking() 带脱敏的数据导出
│   └── 根据用户角色过滤敏感字段
└── 参考：Micro-GenBI-Feature-Enhancement.md 2.1 + 2.2

Step D2-5: 查询历史与收藏 ✅ 待实现
├── 实现 QueryHistoryService（service/query_history.py）
│   ├── save_query() 自动保存查询记录
│   ├── add_to_favorites() 收藏查询
│   ├── get_favorites() 获取收藏列表
│   └── search_history() 搜索历史（关键词 + 时间范围）
├── 实现 QueryRecord 数据模型
│   ├── id / user_id / natural_query / generated_sql
│   ├── tables_used / execution_time_ms / row_count
│   └── timestamp / session_id / is_favorite
└── 参考：Micro-GenBI-Feature-Enhancement.md 1.2
```

**完成标准**：
```
✅ 多库 LLM Prompt 方言适配（MySQL / PostgreSQL / SQLite）
✅ Schema Registry + SQL 结果 + LLM 响应三级缓存
✅ 查询建议（模板匹配 + 字段联想 + 历史推荐）
✅ 数据导出（CSV / Excel / JSON / SQL / PDF + 脱敏）
✅ 查询历史（保存 + 收藏 + 搜索）
```

**交付文件**：
```
src/micro_genbi/
├── intent/
│   └── query_suggester.py    ← 查询建议与补全（新增）
├── service/
│   ├── data_exporter.py      ← 数据导出服务（新增）
│   ├── safe_exporter.py      ← 安全导出器（新增）
│   └── query_history.py       ← 查询历史与收藏（新增）
├── llm/
│   └── prompts.py            ← 扩展方言模板（已有，增量修改）
tests/
├── unit/
│   ├── test_tfidf_index.py   ← TF-IDF 单元测试（新增）
│   ├── test_chart_engine.py  ← 图表生成单元测试（新增）
│   ├── test_query_suggester.py ← 查询建议单元测试（新增）
│   └── test_data_exporter.py ← 导出服务单元测试（新增）
```

---

### Phase D3：用户体验增强 ✅ 已完成

**目标**：让用户交互更流畅，分析能力更强

**前置条件**：Phase D2 完成

**开发步骤**：

```
Step D3-1: 自然语言结果解读 ✅ 待实现
├── 实现 ResultInterpreter（service/result_interpreter.py）
│   ├── interpret() 查询结果解读
│   │   ├── 数据概览（总数、最大、最小、平均）
│   │   ├── 关键发现提取
│   │   ├── 异常检测提示
│   │   └── 建议行动生成
│   ├── _summarize_data() 生成数据摘要
│   └── _format_stats() 格式化统计信息
└── 参考：Micro-GenBI-Feature-Enhancement.md 3.1

Step D3-2: 智能图表推荐 ✅ 待实现
├── 实现 ChartRecommender（chart/smart_recommender.py）
│   ├── recommend() 推荐可视化方案
│   │   ├── 分析结果数据结构
│   │   ├── 基于数据特征推荐（时间序列 → line / 分类 → bar / 占比 → pie）
│   │   └── 基于查询意图调整（趋势/对比/分布）
│   └── _analyze_result_structure() 分析结果结构
└── 参考：Micro-GenBI-Feature-Enhancement.md 3.3

Step D3-3: 异常自动检测 ✅ 待实现
├── 实现 AnomalyDetector（service/anomaly_detector.py）
│   ├── detect_anomalies() 检测异常数据点
│   │   ├── Z-Score 检测（阈值 3σ）
│   │   ├── IQR 四分位距检测（factor 1.5）
│   │   └── 趋势异常检测
│   └── 多指标并行检测
├── 实现 StatisticsPredictor（预测前置依赖）
│   ├── 同比增长率计算
│   ├── 指数平滑预测
│   └── 置信区间估算（±15%）
└── 参考：Micro-GenBI-Feature-Enhancement.md 3.2

Step D3-4: SQL 版本管理与对比 ✅ 待实现
├── 实现 SQLVersioningService（service/sql_versioning.py）
│   ├── save_version() 保存 SQL 版本
│   ├── compare_versions() 对比两个 SQL 版本（sqlglot diff）
│   └── rollback() 回滚到指定版本
└── 参考：Micro-GenBI-Feature-Enhancement.md 1.4

Step D3-5: 实时数据预览 ✅ 待实现
├── 实现 PreviewAPI（api/preview.py）
│   ├── POST /api/v1/preview（快速预览端点）
│   ├── GET /api/v1/preview/{query_id}（已有结果预览）
│   ├── 限制预览范围（只查 5 条）
│   └── intent 检测 + 预览数据返回
└── 参考：Micro-GenBI-Feature-Enhancement.md 1.3

Step D3-6: 配置热更新 ✅ 待实现
├── 实现 ConfigHotReloader（config/hot_reload.py）
│   ├── start() 启动配置监听（watchdog）
│   ├── _on_config_change() 配置变更回调
│   ├── _validate_config() 配置验证
│   └── _notify_changes() 差异通知
└── 参考：Micro-GenBI-Feature-Enhancement.md 5.2

Step D3-7: 操作追踪服务 ✅ 待实现
├── 实现 OperationTraceService（service/operation_trace.py）
│   ├── start_trace() 开始追踪
│   ├── add_step() 记录操作步骤
│   └── get_trace() 获取追踪记录
├── 实现 OperationStep 数据模型
│   ├── type（intent_classification / schema_retrieval / sql_generation 等）
│   ├── input / output / duration_ms / timestamp
│   └── 操作耗时埋点
└── 参考：Micro-GenBI-Feature-Enhancement.md 4.3
```

**完成标准**：
```
✅ 结果解读（数据概览 + 关键发现 + 建议行动）
✅ 智能图表推荐（数据特征 + 查询意图双维度）
✅ 异常自动检测（Z-Score / IQR / 趋势异常）
✅ SQL 版本管理（保存 + 对比 + 回滚）
✅ 实时预览（POST /api/v1/preview）
✅ 配置热更新（文件监听 + 自动生效）
✅ 操作追踪（步骤记录 + 耗时埋点）
```

**交付文件**：
```
src/micro_genbi/
├── service/
│   ├── result_interpreter.py  ← 结果解读（新增）
│   ├── anomaly_detector.py   ← 异常检测（新增）
│   ├── sql_versioning.py     ← SQL 版本管理（新增）
│   └── operation_trace.py    ← 操作追踪（新增）
├── chart/
│   └── smart_recommender.py  ← 智能图表推荐（新增）
├── api/
│   └── preview.py             ← 实时预览（新增）
├── config/
│   └── hot_reload.py          ← 配置热更新（新增）
tests/
└── unit/
    ├── test_result_interpreter.py
    ├── test_anomaly_detector.py
    ├── test_sql_versioning.py
    └── test_operation_trace.py
```

---

### Phase D4：自动化与增值能力 ✅ 已完成

**目标**：降低用户操作成本，提供更深度的数据分析

**前置条件**：Phase D3 完成

**开发步骤**：

```
Step D4-1: 定时订阅服务 ✅ 待实现
├── 实现 SubscriptionService（service/subscription.py）
│   ├── create_subscription() 创建定时订阅
│   │   ├── query / schedule（Cron 表达式）/ recipients / format
│   │   └── 注册到 APScheduler
│   ├── _execute_subscription() 执行订阅任务
│   │   ├── 执行查询（AskService）
│   │   ├── 格式化结果（DataExporter）
│   │   └── 发送通知（邮件/Webhook）
│   ├── pause_subscription() / resume_subscription()
│   └── delete_subscription()
├── 实现 Subscription 数据模型
│   ├── id / user_id / query / schedule / recipients
│   ├── format / is_active / last_run / next_run
│   └── Cron 表达式解析（croniter）
└── 参考：Micro-GenBI-Feature-Enhancement.md 4.2

Step D4-2: 仪表盘服务 ✅ 待实现
├── 实现 DashboardService（service/dashboard.py）
│   ├── create_dashboard() 创建仪表盘
│   │   ├── name / widgets / layout
│   │   └── 自动布局算法
│   ├── add_widget() 添加组件
│   │   ├── 组件类型：查询卡片、图表、数据表格、文本说明
│   │   └── position（x / y / w / h）
│   ├── refresh_widget() 刷新组件数据
│   └── delete_dashboard() / update_dashboard()
├── 实现 DashboardWidget 数据模型
│   ├── type / query / chart_type / position
│   └── refresh_interval（秒）
└── 参考：Micro-GenBI-Feature-Enhancement.md 4.1
```

**完成标准**：
```
✅ 定时订阅（Cron 表达式 + 执行 + 通知）
✅ 仪表盘（自定义看板 + 多组件 + 定时刷新）
```

**交付文件**：
```
src/micro_genbi/
├── service/
│   ├── subscription.py       ← 定时订阅服务（新增）
│   └── dashboard.py          ← 仪表盘服务（新增）
tests/
└── unit/
    ├── test_subscription.py
    └── test_dashboard.py
```

---

## 七、主线 E — 增值能力（预测 + AI 分析 + 大数据） ✅ 已完成（Phase E1-E3）

> **覆盖范围**：时序预测、AI 增强分析、LanceDB Memory、大数据能力
> **主要参考**：`Multi-Database-Architecture.md` 第七章、第十一章
> **依赖**：Phase D4 完成

### Phase E1：预测服务 ✅ 已完成

**目标**：时序预测 + 异常检测

**开发步骤**：

```
Step E1-1: StatisticsPredictor（轻量预测）✅ 已实现（Phase D3-3）
├── 实现 forecast() 接口
│   ├── 同比增长率计算
│   ├── 指数平滑预测（简单/双重指数平滑）
│   ├── 置信区间估算（±15%）
│   └── 自然语言解读生成
└── 参考：Multi-Database-Architecture.md 7.2.2 路径一

Step E1-2: ProphetPredictor（精确预测）✅ 已实现
├── 安装 prophet（pip install prophet）
├── 实现 forecast()
│   ├── 季节性建模（yearly / weekly / daily）
│   ├── 趋势建模（线性/对数）
│   ├── 节假日效应
│   └── MAPE / RMSE / R² 评估
├── 实现 interpret() 自然语言解读
└── 参考：Multi-Database-Architecture.md 7.2.2 路径二

Step E1-3: PredictionService（统一入口）✅ 已实现
├── auto 模式（数据量 > 100 → Prophet，否则 Statistics）
├── 模型缓存（避免重复训练，TTL 3600s）
├── 结果缓存（TTL 3600s）
└── 参考：Multi-Database-Architecture.md 7.2.2

Step E1-4: 异常检测增强 + 预测图表渲染✅ 已实现（IsolationForest 集成 + ECharts 预测图表）
├── IsolationForest 集成（sklearn）
│   ├── 自动识别异常数据点
│   ├── 异常报告生成
│   └── 多指标并行检测
├── ECharts 预测图表扩展
│   ├── 折线图（历史 + 预测值 + 置信区间）
│   ├── 异常点标注（红色高亮）
│   └── ChartEngine 扩展预测模式
└── 参考：Multi-Database-Architecture.md 7.2.1 + 7.2.2
```

**完成标准**：
```
✅ StatisticsPredictor（同比/指数平滑/置信区间）
✅ ProphetPredictor（季节性 + 趋势 + 节假日）
✅ PredictionService（auto 模式 + 模型缓存）
✅ IsolationForest 异常检测
✅ 预测图表（历史 + 预测值 + 置信区间 + 异常点标注）
```

**交付文件**：
```
src/micro_genbi/
├── prediction/
│   ├── __init__.py
│   ├── base.py                ← 预测基类（新增）
│   ├── statistics_predictor.py ← 统计预测（新增）
│   ├── prophet_predictor.py    ← Prophet 预测（新增）
│   ├── prediction_service.py   ← 预测服务（新增）
│   └── isolation_forest.py     ← 异常检测（新增）
tests/
└── unit/
    ├── test_statistics_predictor.py
    └── test_prophet_predictor.py
```

---

### Phase E2：AI 增强分析 ✅ 已完成

**目标**：LLM 驱动的深度分析（结果解读、对比分析、异常推理、预测推理、SQL 解读）

**开发步骤**：

```
Step E2-1: LLMAnalysisService ✅ 已实现
├── 实现 5 种分析类型
│   ├── interpret（结果解读）
│   ├── compare（对比分析）
│   ├── anomaly（异常分析）
│   ├── forecast_reasoning（预测推理）
│   └── sql_explain（SQL 解读）
├── 实现 _summarize_result()（结果压缩，不超过 500 字）
├── 实现 _build_prompt()（分类型生成分析 Prompt）
├── 实现 _parse_response()（JSON 解析 + 错误处理）
└── 参考：Multi-Database-Architecture.md 11.2

Step E2-2: AnalyticsPipeline（完整分析流水线）✅ 已实现
├── Step 1: 执行查询（MultiDBAskService）
├── Step 2: 并行 LLM 分析（interpret + compare）
│   └── asyncio.gather 并发执行
├── Step 3: 预测（如需要，enable_forecast=True）
├── Step 4: 生成可视化（ChartEngine）
│   └── 优先使用 LLM 推荐的图表类型
├── Step 5: 组装最终响应
│   ├── query（SQL / row_count / elapsed_ms / data）
│   ├── analysis（conclusion / findings / confidence / suggestions）
│   ├── forecast（model / values / dates / interpretation）
│   └── chart（echarts 配置）
└── 参考：Multi-Database-Architecture.md 11.3
```

**完成标准**：
```
✅ LLMAnalysisService（5 种分析模式）
✅ AnalyticsPipeline（查询 → 分析 → 预测 → 可视化 → 响应）
✅ 结果压缩（避免 token 爆炸）
✅ 并行分析（asyncio.gather）
```

**交付文件**：
```
src/micro_genbi/
├── service/
│   ├── llm_analysis.py        ← LLM 分析服务（新增）
│   └── analytics_pipeline.py   ← 完整分析流水线（新增）
tests/
└── unit/
    └── test_llm_analysis.py
```

---

### Phase E3：LanceDB Memory ✅ 已完成

**目标**：历史查询 + 语义向量记忆

**开发步骤**：

```
Step E3-1: LanceDBMemoryStore ✅ 已实现
├── context_table（表/列语义向量）
│   ├── id / table_name / column_name / description
│   ├── semantic_vector（embedding）
│   └── updated_at
├── queries_table（NL→SQL 历史向量）
│   ├── id / natural_query / generated_sql / tables_used
│   ├── semantic_vector（embedding）
│   └── timestamp
├── Lazy open + 缓存
└── 参考：Micro-GenBI-WrenAI-Port-Guide.md 第七章

Step E3-2: MemoryAPI ✅ 已实现
├── fetch(query) 语义检索
│   ├── 嵌入查询文本
│   ├── 向量相似度搜索（top-k）
│   └── 返回相关历史查询
├── recall(table_name) 回忆表相关历史
├── store(query, sql, tables) 存储新记录
└── 参考：Micro-GenBI-WrenAI-Port-Guide.md 第九章

Step E3-3: MemoryTools（AI Agent 集成）✅ 已实现
├── 实现 Pydantic AI 工具
│   ├── get_schema_context（获取 schema 上下文）
│   ├── get_query_history（获取历史查询）
│   └── recall_similar_queries（语义相似查询）
└── 参考：Micro-GenBI-WrenAI-Port-Guide.md 第七章
```

**完成标准**：
```
✅ LanceDBMemoryStore（context_table + queries_table）
✅ MemoryAPI（fetch / recall / store）
✅ MemoryTools（Pydantic AI 工具）
```

**交付文件**：
```
src/micro_genbi/
├── memory/
│   ├── __init__.py
│   ├── lancedb_store.py        ← LanceDB 存储（新增）
│   ├── memory_api.py           ← 记忆 API（新增）
│   └── memory_tools.py         ← AI Agent 工具（新增）
tests/
└── unit/
    └── test_lancedb_memory.py
```

---

### Phase E4：大数据能力（按需实施）✅ 已完成

**目标**：支持 ClickHouse / PostgreSQL FDW / Python 并行三条大数据路径

**前置条件**：Phase E1 ~ E3 完成

**开发步骤**：

```
Step E4-1: ClickHouse Connector（超大规模路径）✅ 已实现
├── 实现 ClickHouseConnector
│   ├── cluster_query()（集群聚合查询）
│   ├── get_materialized_view()（预聚合视图）
│   └── Dictionary（维表支持）
├── CDC 同步方案（可选）
│   ├── Debezium CDC → Kafka → ClickHouse
│   └── 简化版：定时 ETL（Python cronjob）
└── 参考：Multi-Database-Architecture.md 7.1 路径一

Step E4-2: PostgreSQL FDW Connector（中等规模路径）✅ 已实现
├── 配置 FDW 连接（mysql_fdw / postgres_fdw）
├── 自动生成 CREATE FOREIGN TABLE 语句
├── 创建 union_view（逻辑统一视图）
└── 参考：Multi-Database-Architecture.md 7.1 路径二

Step E4-3: 大数据路由选择 ✅ 已实现
├── 自动根据库数量和数据量选择路径
│   ├── Python 并行（< 10 库，默认路径）
│   ├── FDW（10~50 库）
│   └── ClickHouse（> 50 库或亿级数据）
└── 参考：Multi-Database-Architecture.md 7.1
```

**完成标准**：
```
✅ ClickHouse Connector（集群聚合）
✅ PostgreSQL FDW Connector
✅ 大数据路由选择（自动判断）
```

**交付文件**：
```
src/micro_genbi/
├── connectors/
│   ├── __init__.py
│   ├── clickhouse_connector.py ← ClickHouse 连接器（新增）
│   └── fdw_connector.py         ← FDW 连接器（新增）
tests/
└── integration/
    └── test_bigdata_connectors.py
```

---

## 八、基础设施（横跨全阶段）

以下能力贯穿所有阶段，不是独立 Phase，而是逐步建设：

### 6.1 用户认证与会话管理

**参考**：`Micro-GenBI-Integration.md` 第十章

```
Phase A1 末期：
├── API Key 认证（X-API-Key Header）
├── 用户角色（admin / user / readonly）
└── 行级 ACL 注入

Phase B 末期：
├── JWT Token 认证（可选）
├── 分组管理（group_id → 不同 schema 可见性）
└── 多租户隔离
```

### 6.2 可观测性

```
Phase A1 末期：
├── 结构化日志（rich.logging / loguru）
├── 每步骤耗时埋点（意图分类/检索/SQL生成/执行/图表）
└── 关键指标：SQL 生成成功率、重试次数、平均延迟

Phase A2 末期：
├── MetricsCollector（计数器、直方图、计时器）
├── 常用指标常量（Metrics 类）
└── track_duration 装饰器（自动追踪函数执行时间）

Phase B 末期：
├── 各子库查询耗时（用于识别慢库）
├── 多库归并耗时
└── 预测准确率追踪（MAPE 监控）
```

### 6.3 缓存架构

```
Phase A2 末期：
├── SQL 结果缓存（内存 dict，TTL 300s）
├── LLM 响应缓存（相同 SQL 直接返回）
└── Schema 配置缓存（启动时加载，变更时刷新）

Phase B 末期：
├── Redis 缓存（可选，生产环境推荐）
│   ├── SQL 结果缓存（KEY: hash(sql)）
│   ├── Schema 缓存（按 version）
│   └── 预测结果缓存
└── 分组级缓存隔离（不同组不共享缓存 KEY）
```

---

## 八、完整开发阶段总览

```
┌──────────────────────────────────────────────────────────────────┐
│  主线 A：核心引擎（单库 Text2SQL）                                 │
├──────────────────────────────────────────────────────────────────┤
│  Phase A1  核心大脑与安全底座        [ 约 2 周 ]                   │
│    依赖：无                                                       │
│    重点：数据库连接 + 异常处理 + 安全验证 + schema.yaml + FastAPI  │
│                                                                  │
│  Phase A2  大模型交互与语义注入      [ 约 2 周 ]                   │
│    依赖：A1 完成                                               │
│    重点：意图分类 + TF-IDF检索 + 自愈重试 + 图表 + 多LLM后端     │
│                                                                  │
│  Phase A3  双端点暴露（UI & MCP）     [ 约 1 周 ]                   │
│    依赖：A2 完成                                               │
│    重点：TaskTracker + Streamlit + MCP Server + Docker           │
└────────────────────────────┬─────────────────────────────────────┘
                             │ A3 完成后，主线 A 达到 MVP
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  主线 B：多库架构                                                │
├──────────────────────────────────────────────────────────────────┤
│  Phase B1  SchemaRegistry + 连接配置    [ 约 1 周 ]                │
│    依赖：A1 完成                                                 │
│    重点：多库配置加载 + 语义隔离 + 连接池工厂                     │
│                                                                  │
│  Phase B2  三模式路由器               [ 约 1 周 ]                │
│    依赖：B1 完成                                                │
│    重点：AggregateRouter + FederatedRouter + MultiDBRouter        │
│                                                                  │
│  Phase B3  多库执行引擎               [ 约 1 周 ]                │
│    依赖：B2 完成                                                │
│    重点：并发执行 + 结果归并 + MultiDBAskService + ServiceFactory  │
└────────────────────────────┬─────────────────────────────────────┘
                             │ B3 完成后，主线 B 达到 MVP
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  主线 D：核心补全与功能增强                                        │
├──────────────────────────────────────────────────────────────────┤
│  Phase D1  核心缺失模块补全           [ 约 1 周 ]                   │
│    依赖：B3 完成                                                 │
│    重点：TF-IDF 索引 + ECharts 图表生成器 + 端到端联调             │
│                                                                  │
│  Phase D2  核心能力深化               [ 约 1.5 周 ]               │
│    依赖：D1 完成                                                │
│    重点：LLM Prompt 优化 + 缓存策略 + 建议/导出/历史               │
│                                                                  │
│  Phase D3  用户体验增强               [ 约 1.5 周 ]               │
│    依赖：D2 完成                                                │
│    重点：结果解读 + 图表推荐 + 异常检测 + SQL 版本管理              │
│                                                                  │
│  Phase D4  自动化与增值能力           [ 约 1 周 ]                   │
│    依赖：D3 完成                                                │
│    重点：定时订阅 + 仪表盘                                      │
└────────────────────────────┬─────────────────────────────────────┘
                             │ D4 完成后，主线 D 达到完整功能集
                             ▼
┌──────────────────────────────────────────────────────────────────┐
│  主线 E：增值能力（预测 + AI 分析 + 大数据）                      │
├──────────────────────────────────────────────────────────────────┤
│  Phase E1  预测服务                    [ 约 1 周 ]                   │
│    依赖：D4 完成                                                │
│    重点：Statistics + Prophet + 异常检测 + 预测图表                │
│                                                                  │
│  Phase E2  AI 增强分析                [ 约 1 周 ]                   │
│    依赖：E1 完成                                                │
│    重点：LLMAnalysisService + AnalyticsPipeline                  │
│                                                                  │
│  Phase E3  LanceDB Memory             [ 约 1 周 ]                   │
│    依赖：E2 完成                                                │
│    重点：历史查询 + 语义向量记忆                                 │
│                                                                  │
│  Phase E4  大数据能力                  [ 约 1~2 周 ]               │
│    依赖：E3 完成                                                │
│    重点：ClickHouse / FDW / Python 并行（按需实施）               │
└──────────────────────────────────────────────────────────────────┘
```

### 时间线估算

| 阶段 | 工作量 | 累计 | 说明 |
|------|--------|------|------|
| Phase A1 | ~2 周 | 第 1-2 周 | 核心最小闭环 |
| Phase A2 | ~2 周 | 第 3-4 周 | LLM + RAG + 自愈 |
| Phase A3 | ~1 周 | 第 5 周 | UI + MCP + Docker |
| **MVP 达成** | **~5 周** | **第 5 周末** | **单库 Text2SQL 完整可用** |
| Phase B1 | ~1 周 | 第 6 周 | 多库配置 |
| Phase B2 | ~1 周 | 第 7 周 | 路由器 |
| Phase B3 | ~1 周 | 第 8 周 | 执行引擎 |
| **多库 MVP** | **~3 周** | **第 8 周末** | **三模式多库查询** |
| Phase D1 | ~1 周 | 第 9 周 | 核心补全 |
| Phase D2 | ~1.5 周 | 第 10-11 周 | 能力深化 |
| Phase D3 | ~1.5 周 | 第 12-13 周 | 用户体验增强 |
| Phase D4 | ~1 周 | 第 14 周 | 自动化与增值 |
| **功能增强达成** | **~5 周** | **第 14 周末** | **完整功能集** |
| Phase E1 | ~1 周 | 第 15 周 | 预测服务 |
| Phase E2 | ~1 周 | 第 16 周 | AI 增强分析 |
| Phase E3 | ~1 周 | 第 17 周 | LanceDB Memory |
| Phase E4 | ~1-2 周 | 第 18-19 周 | 大数据能力（按需） |
| **完整版** | **~19 周** | **第 19 周末** | **全功能生产就绪** |

---

## 九、交付清单

### MVP 交付（第 5 周末）

```
✅ 单数据库 Text2SQL 完整闭环
✅ SQLSafetyValidator（写操作拦截 + LIMIT 强制）
✅ IntentClassifier（三层分类）
✅ SemanticRetriever（TF-IDF 检索）
✅ Self-Correction Loop（3次重试）
✅ ChartEngine（ECharts 图表）
✅ Streamlit UI + REST API + MCP Server
✅ CLI 工具（genbi ask/schema/serve/metrics）
✅ FastAPI + Docker 部署
✅ GitHub Actions CI（lint + test + build）
✅ 单元测试 + 集成测试
```

### 多库 MVP 交付（第 8 周末）

```
✅ SchemaRegistry（多库语义配置）
✅ MultiDatabaseRouter（三模式路由）
✅ ExecutionEngine（并发执行 + UNION ALL 归并）
✅ genbi_config.yaml（模式配置示例 × 3）
✅ 前端模式选择器（Streamlit 配置面板）
```

### 功能增强版交付（第 14 周末）

```
✅ TF-IDF 检索索引（retrieval/tfidf_index.py）
✅ ECharts 图表生成器（chart/chart_engine.py）
✅ 多库 LLM Prompt 方言适配（MySQL / PostgreSQL / SQLite）
✅ 三级缓存（Schema Registry + SQL 结果 + LLM 响应）
✅ 查询建议与补全（intent/query_suggester.py）
✅ 数据导出服务（service/data_exporter.py，支持 CSV/Excel/JSON/SQL/PDF）
✅ 查询历史与收藏（service/query_history.py）
✅ 结果解读（service/result_interpreter.py）
✅ 智能图表推荐（chart/smart_recommender.py）
✅ 异常自动检测（service/anomaly_detector.py）
✅ SQL 版本管理（service/sql_versioning.py）
✅ 实时预览（api/preview.py）
✅ 配置热更新（config/hot_reload.py）
✅ 操作追踪（service/operation_trace.py）
✅ 定时订阅（service/subscription.py）
✅ 仪表盘（service/dashboard.py）
✅ 端到端集成测试（tests/integration/test_e2e_pipeline.py）
```

### 完整版交付（第 19 周末）

```
✅ PredictionService（Prophet + Statistics）
✅ LLMAnalysisService（5 种分析模式）
✅ AnalyticsPipeline（完整分析流水线）
✅ LanceDB Memory（历史 + 语义记忆）
✅ ClickHouse / FDW / Python 并行（按需）
✅ 用户认证 + 多租户 RLS
✅ Redis 缓存（可选）
✅ 可观测性（日志 + 指标 + 告警）
```

---

## 十、文档索引

| 需求/问题 | 参考文档 | 章节 |
|---------|---------|------|
| Text2SQL 核心设计 | `Micro-GenBI-Integration.md` | 第二~四章 |
| FastAPI / MCP 详细实现 | `Micro-GenBI-Integration.md` | 4.4~4.6 |
| 多库架构完整设计 | `Multi-Database-Architecture.md` | 第一~六章 |
| 预测服务 + AI 分析 | `Multi-Database-Architecture.md` | 第七、十一章 |
| 三模式配置 + 前端 | `Multi-Database-Architecture.md` | 第十章 |
| WrenAI 源码移植 | `Micro-GenBI-WrenAI-Port-Guide.md` | 第二~九章 |
| 完整 REST API 设计 | `Micro-GenBI-Integration.md` | 第二章 |
| 用户认证 / 缓存 / 部署 | `Micro-GenBI-Integration.md` | 第十章 |
| 完整 REST API 设计 | `Micro-GenBI-API-Spec.md` | 全文 |
| UI 设计规范 | `Micro-GenBI-UI-Design.md` + `prototype.html` | 全文 |
| 安全加固方案 | `Micro-GenBI-Security-Enhancement.md` | 全文 |
| 功能增强建议 | `Micro-GenBI-Feature-Enhancement.md` | 全文 |
| PRD 产品定义 | `GenBI_Integration_PRD.md` | 全文 |

---

## 十一、文档索引

### 11.1 核心设计文档

| 文档 | 说明 |
|-----|------|
| `Micro-GenBI-Integration.md` | 核心架构、API 设计、代码实现（第二~四章） |
| `Micro-GenBI-API-Spec.md` | 完整 RESTful API 规范 + .NET/Java 对接指南 |
| `Multi-Database-Architecture.md` | 多库架构、SchemaRegistry、Router、Executor |

### 11.2 参考文档

| 文档 | 说明 |
|-----|------|
| `Micro-GenBI-WrenAI-Port-Guide.md` | WrenAI 源码移植指南 |
| `Multi-Database-Architecture.md` | 预测服务、AI 分析（第七、十一章） |
| `Multi-Database-Architecture.md` | 三模式配置（第十章） |

### 11.3 项目规范文档

| 文档 | 说明 |
|-----|------|
| `Micro-GenBI-UI-Design.md` | UI 设计规范（Tesla 风格） + `prototype.html` |
| `Micro-GenBI-Security-Enhancement.md` | 安全加固方案 |
| `Micro-GenBI-Feature-Enhancement.md` | 功能增强建议 |
| `GenBI_Integration_PRD.md` | PRD 产品需求定义 |


### 11.4 功能模块对照表

|功能模块 |实现步骤 |参考文档 |
|---------|---------|---------|
|核心引擎（LLM、意图分类、语义检索、自愈重试） |Step A1-7 ~ A2-3 |`Micro-GenBI-Integration.md` |
|SQL 安全验证器（SQLSanitizer、注入防护、脱敏） |Step A1-5 |`Micro-GenBI-Security-Enhancement.md` |
|TF-IDF 检索索引 |Step D1-1 |`Micro-GenBI-Integration.md` 第三章 G2 |
|ECharts 图表生成器 |Step D1-2 |`Micro-GenBI-Integration.md` 4.3 |
|多库架构（SchemaRegistry、Router、Executor） |Phase B |`Multi-Database-Architecture.md` |
|多库 LLM Prompt 优化（方言适配） |Step D2-1 |`Multi-Database-Architecture.md` 第十章 |
|缓存策略（Schema + SQL + LLM 三级缓存） |Step D2-2 |`Micro-GenBI-Integration.md` 第十章 |
|查询建议与补全 |Step D2-3 |`Micro-GenBI-Feature-Enhancement.md` 1.1 |
|数据导出服务 |Step D2-4 |`Micro-GenBI-Feature-Enhancement.md` 2.1 |
|查询历史与收藏 |Step D2-5 |`Micro-GenBI-Feature-Enhancement.md` 1.2 |
|结果解读 |Step D3-1 |`Micro-GenBI-Feature-Enhancement.md` 3.1 |
|智能图表推荐 |Step D3-2 |`Micro-GenBI-Feature-Enhancement.md` 3.3 |
|异常自动检测 |Step D3-3 |`Micro-GenBI-Feature-Enhancement.md` 3.2 |
|SQL 版本管理 |Step D3-4 |`Micro-GenBI-Feature-Enhancement.md` 1.4 |
|实时预览 |Step D3-5 |`Micro-GenBI-Feature-Enhancement.md` 1.3 |
|配置热更新 |Step D3-6 |`Micro-GenBI-Feature-Enhancement.md` 5.2 |
|操作追踪 |Step D3-7 |`Micro-GenBI-Feature-Enhancement.md` 4.3 |
|定时订阅 |Step D4-1 |`Micro-GenBI-Feature-Enhancement.md` 4.2 |
|仪表盘 |Step D4-2 |`Micro-GenBI-Feature-Enhancement.md` 4.1 |
|REST API（含 .NET/Java 对接指南） |Step A3-2 |`Micro-GenBI-API-Spec.md` |
|Streamlit 前端 |Step A3-3 |`Micro-GenBI-UI-Design.md` |
|MCP Server |Step A3-4 |`Micro-GenBI-Integration.md` |
|预测服务（Statistics + Prophet） |Phase E1 |`Multi-Database-Architecture.md` 7.2.2 |
|AI 增强分析（LLMAnalysisService） |Phase E2 |`Multi-Database-Architecture.md` 11.2 |
|AnalyticsPipeline |Phase E2 |`Multi-Database-Architecture.md` 11.3 |
|LanceDB Memory |Phase E3 |`Micro-GenBI-WrenAI-Port-Guide.md` 第七章 |
|大数据能力（ClickHouse / FDW） |Phase E4 |`Multi-Database-Architecture.md` 7.1 |
|用户认证 / RBAC / 审计 |Step A3-1 |`Micro-GenBI-Security-Enhancement.md` |
|Docker 部署 |Step A3-5 |`Micro-GenBI-Integration.md` |

---

*本文档为 Micro-GenBI 的完整开发计划，涵盖从核心引擎到多库架构再到增值能力的全阶段开发路径。*