# Micro-GenBI — 集成方案与扩展计划

> 本文档为 Micro-GenBI 的**核心集成方案**，聚焦于：
> 1. WrenAI 借鉴部分 vs 自研部分的详细边界划分
> 2. RESTful API 设计（面向 Java Web / .NET 桌面程序集成）
> 3. 前端原型扩展路线图
> 4. 完整部署架构
> 5. **多推理模型支持与模型管理**
> 6. **细粒度读写权限控制与写操作安全**
> 7. **PRD Claude 模式整合、Hook 框架、6 项新增功能**
> 8. **用户体系、分组管理与缓存架构重构**（用户认证 + 分组 + SQL Key 缓存 + 向量语义搜索 + 写操作并发控制）
> 9. **Schema 管理与业务字典映射**（自动抽取表结构 + ER 图生成 + 枚举值解析 + 业务字典注入 LLM）
> 10. **枚举推断规则与字段确认机制**（state/mode/type 命名规则 + 置信度评分 + 阻断 SQL 生成直到用户确认）
> 11. **五个功能深化设计**（跨库 JOIN + 多租户 RLS + LLM 输出稳定性 + SQL 模板缓存 + 回归测试 + 字段中文别名）

---

## 一、WrenAI 借鉴 vs 自研：边界矩阵

### 1.1 总体原则

| 维度 | WrenAI 提供 | 自研实现 | 原因 |
|------|-----------|---------|------|
| **架构思想** | ✅ 完整参考 | — | 语义中间件 + Agent 编排是经过验证的最佳实践 |
| **MDL 语义层** | ✅ 核心概念 | 简化为 YAML | MDL 太重，YAML 已覆盖 90% 需求 |
| **Wren Engine (Rust)** | ✅ 技术方向 | 用 SQLAlchemy 替代 | 零 Rust 依赖，降低门槛 |
| **LanceDB 记忆层** | ✅ SDK 参考 | ✅ 完整自研 | 纯 Python，10 行代码 |
| **SQL 规划/CTE 重写** | ✅ 方向参考 | 用 sqlglot 替代 | Rust Engine 无法自研，sqlglot 够用 |
| **意图分类** | ✅ 设计参考 | ✅ 完整自研 | WrenAI 的 Embedding 方案成本高，规则引擎更实用 |
| **CLI / Skill 系统** | ✅ 参考 | 不实现 | 这是给 AI Agent 用的，你的系统是给业务用户 |
| **MCP Server** | ✅ 参考 | ✅ 完整自研 | 协议是标准，WrenAI 的 MCP 已归档 |
| **UI / 前端** | ❌ 无 | ✅ 完整自研 | WrenAI 无原生 UI，只有 Streamlit 示例 |

### 1.2 详细模块对照表

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           模块维度对照                                   │
├────────────────────┬──────────────────────┬──────────────────────────────┤
│ 模块               │ WrenAI 参考价值       │ Micro-GenBI 实现方案        │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 意图分类           │ ★★★★★               │ ✅ 三层分类器（G1）         │
│ (IntentClassifier) │ WrenAI 4分类是核心  │ 规则(70%) + 小模型(30%)    │
│                    │ 设计，Embedding成本高│ 规则自研，小模型用 DeepSeek │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 语义检索           │ ★★★★☆               │ ✅ TF-IDF（G2）            │
│ (SemanticRetriever)│ Dense RAG 是核心思路 │ Phase2 TF-IDF, Phase3 Embed │
│                    │ Qdrant 是工程重点    │ LanceDB 向量自研            │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ MDL 语义层         │ ★★★★☆               │ ✅ schema.yaml（G1）        │
│ (SemanticManager)  │ MDL 五层是完整方案   │ 表别名 + 列描述 + 关系      │
│                    │ Metrics/Views/Cubes  │ 简化为 YAML，计算字段已够用  │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ SQL 生成           │ ★★★☆☆               │ ✅ 完整自研                │
│ (SQL Agent)        │ 主要参考 Prompt 思路  │ System Prompt + Few-shot   │
│                    │ Wren Engine 换不了   │ sqlglot 验证替代           │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ SQL 安全            │ ★★★★★               │ ✅ 完整自研                │
│ (SafetyValidator)  │ Wren Engine 核心功能 │ sqlglot AST 遍历           │
│                    │ 自研无法复制        │ 写操作拦截 + LIMIT 强制     │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ SQL 自愈           │ ★★★★☆               │ ✅ 完整自研                │
│ (Self-Correction)  │ 错误归因思路极有价值 │ 分层错误归因 + 修正 Prompt  │
│                    │ Prompt 模板可迁移   │ 3次重试，phase-aware        │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 记忆层             │ ★★★★☆               │ ✅ 完整自研                │
│ (Memory/LanceDB)  │ SDK 源码可直接迁移   │ query_history + schema_items│
│                    │ wren-pydantic 可用  │ 两集合自研，LanceDB 自管理  │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ Chart 生成         │ ★★★☆☆               │ ✅ 完整自研                │
│ (ChartEngine)     │ Vega-Lite 可参考    │ ECharts 替代，社区更活跃    │
│                    │ 图表推断思路可迁移  │ 规则推断 + LLM 生成双模式  │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 会话管理           │ ★★★☆☆               │ ✅ 完整自研                │
│ (HistoryManager)   │ 参考 session 结构   │ 多轮对话 + 上下文压缩       │
│                    │ 无太多可迁移        │ follow-up 重写自研          │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 异步任务           │ ★★★★★               │ ✅ 完整自研                │
│ (TaskTracker)     │ SSE + TaskState 思路│ 内存/Redis + SSE 流式推送  │
│                    │ 必须自研            │ 轮询 + 取消 + 进度追踪     │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ MCP Server        │ ★★★★★               │ ✅ 完整自研                │
│ (JSON-RPC 2.0)   │ WrenAI MCP 已归档   │ python-mcp SDK              │
│                    │ 协议是标准          │ tools/list + tools/call    │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ 多数据源           │ ★★★★★               │ ✅ 完整自研                │
│ (Database Connect) │ 22+ 连接器是金子    │ SQLAlchemy + 连接池工厂    │
│                    │ Profile 方案可迁移  │ Profile 方案直接用         │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ Cube 聚合         │ ★★★☆☆               │ 🔜 Phase 4                │
│                    │ 概念有价值         │ 指标定义 + 预聚合可后期加  │
├────────────────────┼──────────────────────┼──────────────────────────────┤
│ ACL / 访问控制    │ ★★★★☆               │ ✅ schema.yaml 内置         │
│                    │ 行级 ACL 是核心功能  │ role-based ACL 已覆盖      │
│                    │ WrenAI Engine 层    │ ACL 注入自研               │
└────────────────────┴──────────────────────┴──────────────────────────────┘
```

### 1.3 WrenAI wren-pydantic SDK 源码级借鉴清单

以下是 `WrenAI-wren-v0.7.0\sdk\wren-pydantic` 中**可直接迁移**（复制粘贴改包名）的模块：

| WrenAI 文件 | 借鉴价值 | 迁移方式 |
|------------|---------|---------|
| `_toolkit.py` | WrenToolkit 主入口模式 | ✅ 核心参考，直接改写 |
| `_providers/memory.py` | LanceDB Provider 实现 | ✅ 完整迁移，改表名 |
| `_providers/mdl_source.py` | MDL 读取方式 | ✅ 迁移读 YAML 逻辑 |
| `_providers/connection.py` | Profile 解析 + 3层fallback | ✅ 迁移 connection 逻辑 |
| `_models.py` | WrenQueryResult 等返回模型 | ✅ 直接复用或继承 |
| `_errors.py` | Phase-aware 错误映射 | ✅ 迁移错误归因逻辑 |
| `_tools_memory.py` | fetch / recall / store 工具 | ✅ 迁移工具定义方式 |
| `_toolset.py` | FunctionToolset 封装 | ✅ 迁移 Pydantic AI 适配 |

---

## 二、RESTful API 设计（Java / .NET 集成方案）

### 2.1 设计原则

1. **协议优先**：所有 API 走 JSON over HTTPS，无特殊要求
2. **幂等设计**：所有写操作（实际上是只读）支持重试
3. **版本化**：URL 路径包含版本号 `/api/v1/`
4. **可发现**：OpenAPI 3.0 文档，Java/.NET 均可自动生成客户端
5. **兼容 MCP**：API 设计参考 MCP 工具定义，保持概念对齐

### 2.2 API 完整规格

#### 2.2.1 核心接口

```yaml
openapi: 3.0.3
info:
  title: Micro-GenBI Text-to-SQL API
  version: 1.0.0
  description: |
    微分智能数据引擎 RESTful API。
    支持自然语言数据分析查询、Schema 管理、历史记录。
    
    认证方式：
    - Header: `X-API-Key: <your-api-key>`
    - Header: `X-User-Id: <user-id>` (用于行级 ACL)
    - Header: `X-User-Role: admin|user|readonly` (默认 user)

servers:
  - url: https://your-microgenbi-host.com
    description: 生产环境
  - url: https://staging-microgenbi-host.com
    description: 预发环境

paths:
  # ═══════════════════════════════════════════
  # 核心查询接口
  # ═══════════════════════════════════════════

  /api/v1/query:
    post:
      operationId: submitQuery
      summary: "提交数据分析查询（同步）"
      description: |
        同步模式：适合简单查询（<5秒）。复杂查询建议用异步接口。
        
        请求体：
        - query: 自然语言问题（必需）
        - session_id: 会话ID，用于多轮对话（可选，自动生成）
        - user_id: 用户ID，用于 ACL（可选，从 Header 读取）
        - role: 角色，admin|user|readonly（可选，从 Header 读取）
        - generate_chart: 是否生成图表（默认 true）
        - chart_type: 强制图表类型，bar|line|pie|table（可选，自动推断）
        
        返回内容：
        - sql: 生成的 SQL（可直接查看和审核）
        - data: 查询结果（JSON 数组）
        - columns: 列定义
        - row_count: 结果行数
        - chart: ECharts Options JSON（如果 generate_chart=true）
        - summary: 自然语言结果摘要
        - steps: 各步骤耗时（意图分类/语义检索/SQL生成/执行/图表）
        - session_id: 当前会话ID（后续追问用）
      tags: [Query]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/QueryRequest'
            example:
              query: "统计各部门上月报销总额"
              generate_chart: true
      responses:
        '200':
          description: 查询成功
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QueryResponse'
        '400':
          description: 参数错误
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '401':
          description: 认证失败
        '403':
          description: 权限不足
        '422':
          description: 查询无法处理（如非 TEXT_TO_SQL 意图）
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ErrorResponse'
        '504':
          description: 查询超时（默认 60s，可配置）

  /api/v1/query/async:
    post:
      operationId: submitQueryAsync
      summary: "提交数据分析查询（异步，返回 task_id）"
      description: |
        异步模式：适合复杂查询或需要长时执行的 SQL。
        返回 task_id 后，客户端通过 GET /api/v1/task/{task_id} 轮询状态。
        
        支持 SSE（Server-Sent Events）实时推送：
        GET /api/v1/task/{task_id}/stream
        
        适用场景：
        - 查询时间可能超过 10 秒
        - 需要实时显示执行步骤
        - 需要支持任务取消
      tags: [Query]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/QueryRequest'
      responses:
        '202':
          description: 已接受，任务排队中
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskSubmitResponse'
        '401':
          description: 认证失败

  /api/v1/task/{task_id}:
    get:
      operationId: getTaskStatus
      summary: "查询任务状态"
      description: |
        轮询接口。建议轮询间隔 1-2 秒。
        
        状态流转：
        pending → running → success
                             → failed
                             → cancelled
                             → timeout
        
        进度信息（current_step）：
        1. intent_classification - 意图分类
        2. schema_retrieval - Schema 检索
        3. sql_generation - SQL 生成
        4. sql_validation - SQL 安全验证
        5. sql_execution - SQL 执行
        6. chart_generation - 图表生成
      tags: [Task]
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
          example: "task_a1b2c3d4e5f6"
      responses:
        '200':
          description: 任务状态
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/TaskStatusResponse'
        '404':
          description: 任务不存在
    delete:
      operationId: cancelTask
      summary: "取消正在执行的任务"
      tags: [Task]
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: 取消成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  cancelled:
                    type: boolean
                    example: true
        '404':
          description: 任务不存在
        '409':
          description: 任务已完成，无法取消

  /api/v1/task/{task_id}/stream:
    get:
      operationId: streamTaskStatus
      summary: "SSE 流式推送任务状态"
      description: |
        Server-Sent Events 实时推送。
        客户端用 EventSource API 接收。
        
        EventSource 示例（JavaScript）：
        ```javascript
        const es = new EventSource('/api/v1/task/{task_id}/stream');
        es.addEventListener('progress', (e) => {
          const data = JSON.parse(e.data);
          console.log(data.step, data.progress);
        });
        es.addEventListener('result', (e) => {
          const result = JSON.parse(e.data);
          renderChart(result.chart);
        });
        es.addEventListener('done', () => es.close());
        ```
      tags: [Task]
      parameters:
        - name: task_id
          in: path
          required: true
          schema:
            type: string
      responses:
        '200':
          description: SSE 流
          content:
            text/event-stream:
              schema:
                type: string
        '404':
          description: 任务不存在

  # ═══════════════════════════════════════════
  # Schema 管理接口
  # ═══════════════════════════════════════════

  /api/v1/schema:
    get:
      operationId: getSchema
      summary: "获取数据库 Schema"
      description: |
        返回当前数据库的完整 Schema 信息。
        包含表名、列名、类型、主键、外键关系。
        
        支持过滤参数：
        - table_filter: 只返回指定表（逗号分隔）
        - include_relationships: 是否包含外键关系（默认 true）
        - include_descriptions: 是否包含业务描述（默认 true）
        
        用途：
        - 前端 Schema 管理面板
        - AI Agent 调试时查看可用表
        - Java/.NET 客户端做离线 Schema 缓存
      tags: [Schema]
      parameters:
        - name: table_filter
          in: query
          schema:
            type: string
          description: 逗号分隔的表名列表，如 "orders,customers"
          example: "orders,customers,products"
        - name: include_relationships
          in: query
          schema:
            type: boolean
            default: true
        - name: include_descriptions
          in: query
          schema:
            type: boolean
            default: true
      responses:
        '200':
          description: Schema 信息
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SchemaResponse'
        '401':
          description: 认证失败

    put:
      operationId: updateSchema
      summary: "更新 Schema 配置（表别名/业务描述/关系）"
      description: |
        更新 schema.yaml 配置。
        用于前端 Schema 管理面板的保存功能。
        
        支持局部更新（PATCH 语义）：
        - table_aliases: 表别名映射
        - semantic_descriptions: 表/列业务描述
        - relationships: 表间关系
        - calculated_fields: 计算字段
        
        注意：此接口修改的是 schema.yaml，不会修改数据库结构。
      tags: [Schema]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/SchemaUpdateRequest'
      responses:
        '200':
          description: 更新成功
          content:
            application/json:
              schema:
                type: object
                properties:
                  updated_at:
                    type: string
                    format: date-time
                  affected_tables:
                    type: array
                    items:
                      type: string
        '400':
          description: 配置格式错误
        '401':
          description: 认证失败
        '403':
          description: 只有 admin 角色可以修改 Schema

  /api/v1/schema/test-connection:
    post:
      operationId: testConnection
      summary: "测试数据库连接"
      description: |
        测试新的数据库连接配置是否可用。
        不会修改现有配置。
        
        返回：连接是否成功 + 探测到的数据库类型 + 表数量
      tags: [Schema]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ConnectionTestRequest'
      responses:
        '200':
          description: 测试结果
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ConnectionTestResponse'
        '400':
          description: 连接失败

  /api/v1/schema/extract:
    post:
      operationId: extractSchemaFromDB
      summary: "从数据库自动提取 Schema"
      description: |
        自动从数据库读取表结构，生成 schema.yaml 骨架。
        
        流程：
        1. 连接数据库
        2. 读取所有表的列信息（COLUMNS metadata）
        3. 读取主键/外键约束
        4. 尝试从列 COMMENT 提取枚举值
        5. 生成 YAML 骨架供人工审核
        
        返回生成的 YAML 内容，客户端可预览后再调用 PUT /api/v1/schema 保存。
      tags: [Schema]
      responses:
        '200':
          description: 提取结果
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SchemaExtractResponse'

  # ═══════════════════════════════════════════
  # 会话与历史接口
  # ═══════════════════════════════════════════

  /api/v1/session/{session_id}:
    get:
      operationId: getSession
      summary: "获取会话历史"
      description: |
        获取指定会话的所有对话记录。
        
        返回内容：
        - 对话列表（按时间顺序）
        - 每个条目包含：用户问题、生成的 SQL、执行结果摘要、图表配置
        - 只返回摘要，不返回全量数据（Context Hygiene 原则）
        
        用途：
        - 前端展示历史记录
        - 多轮对话上下文恢复
        - 审计日志
      tags: [Session]
      parameters:
        - name: session_id
          in: path
          required: true
          schema:
            type: string
          example: "sess_abc123"
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
            minimum: 1
            maximum: 100
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
      responses:
        '200':
          description: 会话历史
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SessionResponse'
        '404':
          description: 会话不存在

  /api/v1/session/{session_id}/continue:
    post:
      operationId: continueSession
      summary: "追问/继续会话"
      description: |
        在现有会话中继续追问。
        与 POST /api/v1/query 的区别：
        - 不传 session_id → 新会话
        - 传 session_id + 新 query → 继续该会话
        
        支持的追问模式：
        - "继续按这个趋势" → 沿用上次的时间范围和分析维度
        - "改成按月统计" → 替换时间粒度
        - "加上毛利率" → 在原查询基础上增加字段
        - "导出到 Excel" → 触发导出流程
      tags: [Session]
      parameters:
        - name: session_id
          in: path
          required: true
          schema:
            type: string
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ContinueRequest'
      responses:
        '200':
          description: 追问结果
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/QueryResponse'
        '404':
          description: 会话不存在
        '422':
          description: 追问无法理解，需要新会话

  /api/v1/sessions:
    get:
      operationId: listSessions
      summary: "列出所有会话"
      description: |
        获取当前用户的所有会话列表。
        
        支持分页和排序：
        - 按创建时间排序（默认，最新在前）
        - 按最后活跃时间排序
        - 支持按日期范围过滤
        
        注意：只返回会话元信息，不包含对话详情。
      tags: [Session]
      parameters:
        - name: limit
          in: query
          schema:
            type: integer
            default: 20
        - name: offset
          in: query
          schema:
            type: integer
            default: 0
        - name: sort_by
          in: query
          schema:
            type: string
            enum: [created_at, last_active_at]
            default: last_active_at
        - name: date_from
          in: query
          schema:
            type: string
            format: date
        - name: date_to
          in: query
          schema:
            type: string
            format: date
      responses:
        '200':
          description: 会话列表
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/SessionListResponse'

  # ═══════════════════════════════════════════
  # 导出接口
  # ═══════════════════════════════════════════

  /api/v1/export:
    post:
      operationId: exportData
      summary: "导出数据"
      description: |
        导出查询结果为文件。
        
        支持格式：
        - CSV: 逗号分隔，UTF-8 BOM（Excel 兼容）
        - Excel: .xlsx，保留类型
        - JSON: 标准 JSON 数组
        - SQL: INSERT INTO 语句（只读，无实际写入）
        
        导出方式：
        - download: 直接下载文件（推荐，小文件 <10MB）
        - async: 异步生成，返回 download_url（大文件）
      tags: [Export]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/ExportRequest'
      responses:
        '200':
          description: 导出成功（直接下载时）
          content:
            application/octet-stream:
              schema:
                type: string
                format: binary
        '202':
          description: 异步导出，任务排队
          content:
            application/json:
              schema:
                type: object
                properties:
                  task_id:
                    type: string
                  download_url:
                    type: string
                  expires_at:
                    type: string
                    format: date-time
        '400':
          description: 导出失败

  # ═══════════════════════════════════════════
  # 管理接口
  # ═══════════════════════════════════════════

  /api/v1/config/database:
    get:
      operationId: getDatabaseConfig
      summary: "获取数据库配置（不含密码）"
      description: |
        获取当前数据库连接配置。
        敏感信息（密码）不会返回，用 `***` 代替。
      tags: [Admin]
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/DatabaseConfig'
        '401':
          description: 认证失败
        '403':
          description: 只有 admin 角色可以查看

    put:
      operationId: updateDatabaseConfig
      summary: "更新数据库连接配置"
      tags: [Admin]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/DatabaseConfigUpdate'
      responses:
        '200':
          description: 更新成功
        '400':
          description: 连接测试失败
        '403':
          description: 只有 admin 角色

  /api/v1/config/llm:
    get:
      operationId: getLLMConfig
      summary: "获取 LLM 配置（不含 API Key）"
      tags: [Admin]
      responses:
        '200':
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/LLMConfig'

  /api/v1/health:
    get:
      operationId: healthCheck
      summary: "健康检查"
      description: |
        用于 Kubernetes/负载均衡 健康探测。
        
        返回内容：
        - status: healthy | degraded | unhealthy
        - database: connected | disconnected
        - llm: available | unavailable
        - uptime: 服务运行时间
        - version: 当前版本
      tags: [System]
      responses:
        '200':
          description: 服务正常
        '503':
          description: 服务异常
```

#### 2.2.2 数据模型（Schemas）

```yaml
components:
  schemas:
    # ── 请求模型 ──────────────────────────────────

    QueryRequest:
      type: object
      required: [query]
      properties:
        query:
          type: string
          minLength: 2
          maxLength: 1000
          description: 自然语言查询问题
          example: "统计各部门上月报销总额"
        session_id:
          type: string
          description: 会话ID（可选，不传则创建新会话）
          example: "sess_abc123"
        user_id:
          type: string
          description: 用户ID（用于 ACL，可从 Header 读取）
          example: "user_1001"
        role:
          type: string
          enum: [admin, user, readonly]
          default: user
        generate_chart:
          type: boolean
          default: true
          description: 是否自动生成图表
        chart_type:
          type: string
          enum: [bar, line, pie, scatter, table]
          description: 强制图表类型（可选，自动推断）
        max_execution_seconds:
          type: integer
          default: 60
          minimum: 5
          maximum: 300
          description: 最大执行超时（秒）

    TaskSubmitResponse:
      type: object
      properties:
        task_id:
          type: string
          example: "task_a1b2c3d4e5f6"
        session_id:
          type: string
        status:
          type: string
          enum: [pending]
        poll_url:
          type: string
          description: 轮询地址
          example: "/api/v1/task/task_a1b2c3d4e5f6"
        stream_url:
          type: string
          description: SSE 流地址
          example: "/api/v1/task/task_a1b2c3d4e5f6/stream"

    SchemaUpdateRequest:
      type: object
      properties:
        table_aliases:
          type: object
          additionalProperties:
            type: string
          example:
            orders: "订单表"
            customers: "客户表"
        semantic_descriptions:
          type: object
          description: 表/列的业务描述
        relationships:
          type: array
          items:
            type: object
            properties:
              from: { type: string }
              to: { type: string }
              via: { type: string }
              type:
                type: string
                enum: [many_to_one, one_to_many, many_to_many]
        calculated_fields:
          type: array
          items:
            type: object
            properties:
              name: { type: string }
              description: { type: string }
              expression: { type: string }

    ConnectionTestRequest:
      type: object
      required: [datasource, host, port, database]
      properties:
        datasource:
          type: string
          enum: [mysql, postgresql, mssql, sqlite, oracle, bigquery, snowflake, duckdb]
        host:
          type: string
          example: "localhost"
        port:
          type: integer
        database:
          type: string
        username:
          type: string
        password:
          type: string
          format: password
        ssl:
          type: boolean
          default: false

    ContinueRequest:
      type: object
      required: [query]
      properties:
        query:
          type: string
          example: "继续按这个趋势"
        generate_chart:
          type: boolean
          default: true

    ExportRequest:
      type: object
      required: [sql, format]
      properties:
        sql:
          type: string
          description: 要导出的 SQL（从历史记录中获取）
        format:
          type: string
          enum: [csv, excel, json, sql]
        filename:
          type: string
          description: 下载文件名（不含扩展名）
          example: "各部门报销统计_2026-05"
        mode:
          type: string
          enum: [download, async]
          default: download
          description: "download: 直接下载, async: 异步生成后返回 URL"

    # ── 响应模型 ──────────────────────────────────

    QueryResponse:
      type: object
      properties:
        task_id:
          type: string
          description: 任务ID（异步模式返回）
        session_id:
          type: string
        sql:
          type: string
          description: 生成的 SQL
          example: "SELECT dept_name, SUM(amount) FROM dept_expense WHERE ..."
        columns:
          type: array
          items:
            type: object
            properties:
              name: { type: string }
              type: { type: string }
              comment: { type: string }
          example:
            - { name: "dept_name", type: "varchar", comment: "部门名称" }
            - { name: "total_amount", type: "decimal", comment: "报销总额" }
        data:
          type: array
          items:
            type: object
          description: 查询结果（JSON 数组）
          example:
            - { dept_name: "销售部", total_amount: 456200 }
        row_count:
          type: integer
          example: 6
        truncated:
          type: boolean
          description: 是否被 LIMIT 截断
        summary:
          type: string
          description: 自然语言结果摘要
          example: "上月各部门报销总额已统计完成。销售部最高（456,200元），其次是市场部（298,500元）"
        chart:
          type: object
          description: ECharts Options JSON
          properties:
            type:
              type: string
              enum: [chart, table]
            chart_type:
              type: string
              enum: [bar, line, pie]
            options:
              type: object
              description: ECharts 5.x Options JSON（直接传给 echarts.init()）
              example: { tooltip: {}, xAxis: {}, series: [] }
        steps:
          type: object
          description: 各步骤耗时（毫秒）
          properties:
            intent_classification_ms:
              type: integer
            schema_retrieval_ms:
              type: integer
            sql_generation_ms:
              type: integer
            sql_validation_ms:
              type: integer
            sql_execution_ms:
              type: integer
            chart_generation_ms:
              type: integer
            total_ms:
              type: integer
        intent:
          type: string
          enum: [TEXT_TO_SQL, GENERAL, USER_GUIDE, MISLEADING_QUERY]
        model_used:
          type: string
          description: 本次使用的 LLM 模型
          example: "deepseek-chat"
        tokens_used:
          type: integer
          description: 本次消耗的 token 数量
        created_at:
          type: string
          format: date-time

    TaskStatusResponse:
      type: object
      properties:
        task_id:
          type: string
        status:
          type: string
          enum: [pending, running, success, failed, cancelled, timeout]
        progress:
          type: number
          format: float
          minimum: 0
          maximum: 1
          description: 进度 0.0 ~ 1.0
        current_step:
          type: string
          description: 当前步骤描述
          example: "正在执行 SQL 查询..."
        result:
          $ref: '#/components/schemas/QueryResponse'
          description: 执行成功时返回完整结果
        error:
          type: string
          description: 执行失败时的错误信息
        error_type:
          type: string
          enum: [SYNTAX, SEMANTIC, TIMEOUT, PERMISSION, MAX_RETRIES, UNKNOWN]
        error_sql:
          type: string
          description: 失败时的 SQL（如果有）
        created_at:
          type: string
          format: date-time
        started_at:
          type: string
          format: date-time
        completed_at:
          type: string
          format: date-time

    SchemaResponse:
      type: object
      properties:
        version:
          type: string
          example: "1.0"
        database_type:
          type: string
          example: "mysql"
        updated_at:
          type: string
          format: date-time
        tables:
          type: array
          items:
            type: object
            properties:
              name:
                type: string
                example: "orders"
              alias:
                type: string
                example: "订单表"
              description:
                type: string
              columns:
                type: array
                items:
                  type: object
                  properties:
                    name: { type: string }
                    type: { type: string }
                    nullable: { type: boolean }
                    primary_key: { type: boolean }
                    foreign_key:
                      type: object
                      properties:
                        table: { type: string }
                        column: { type: string }
                    comment: { type: string }
                    enum_values:
                      type: array
                      items:
                        type: string
                      description: 从 COMMENT 中提取的枚举值
              row_count:
                type: integer
                description: 表行数（可选，快照统计）
          example:
            - name: orders
              alias: 订单表
              columns:
                - name: id
                  type: int
                  primary_key: true
                - name: customer_id
                  type: int
                  foreign_key:
                    table: customers
                    column: id

    ConnectionTestResponse:
      type: object
      properties:
        success:
          type: boolean
        database_type:
          type: string
          example: "mysql"
        database_version:
          type: string
          example: "8.0.35"
        table_count:
          type: integer
          example: 12
        latency_ms:
          type: integer
          description: 连接延迟
        error:
          type: string
          description: 失败时的错误信息

    SchemaExtractResponse:
      type: object
      properties:
        yaml_content:
          type: string
          description: 生成的 YAML 内容
        table_count:
          type: integer
        column_count:
          type: integer
        relationship_count:
          type: integer
        warnings:
          type: array
          items:
            type: string
          description: 提取警告（如 COMMENT 缺失的列）

    SessionResponse:
      type: object
      properties:
        session_id:
          type: string
        created_at:
          type: string
          format: date-time
        last_active_at:
          type: string
          format: date-time
        entries:
          type: array
          items:
            type: object
            properties:
              id:
                type: string
              role:
                type: string
                enum: [user, assistant]
              query:
                type: string
                description: 用户问题
              intent:
                type: string
              sql:
                type: string
                description: 生成的 SQL
              result_summary:
                type: string
                description: 结果摘要（Context Hygiene 原则）
              chart_type:
                type: string
                description: 图表类型（有图表时）
              row_count:
                type: integer
              created_at:
                type: string
                format: date-time

    SessionListResponse:
      type: object
      properties:
        sessions:
          type: array
          items:
            type: object
            properties:
              session_id:
                type: string
              title:
                type: string
                description: 会话标题（从第一个问题提取前20字）
              created_at:
                type: string
                format: date-time
              last_active_at:
                type: string
                format: date-time
              entry_count:
                type: integer
              last_query:
                type: string
        total:
          type: integer
        has_more:
          type: boolean

    DatabaseConfig:
      type: object
      properties:
        datasource:
          type: string
        host:
          type: string
        port:
          type: integer
        database:
          type: string
        username:
          type: string
        password:
          type: string
          description: 始终返回 "***"
        ssl:
          type: boolean
        pool_size:
          type: integer
        connection_timeout_ms:
          type: integer

    LLMConfig:
      type: object
      properties:
        provider:
          type: string
          enum: [deepseek, openai, ollama, anthropic, azure_openai]
        model:
          type: string
          example: "deepseek-chat"
        api_base:
          type: string
          example: "https://api.deepseek.com"
        api_key:
          type: string
          description: 始终返回 "***"
        temperature:
          type: number
          default: 0.1
        max_tokens:
          type: integer
          default: 2000
        intent_model:
          type: string
          description: 意图分类专用模型（可选）
        retry_times:
          type: integer
          default: 3

    ErrorResponse:
      type: object
      properties:
        error:
          type: string
          description: 错误类型
          enum: [INVALID_REQUEST, UNAUTHORIZED, FORBIDDEN, NOT_FOUND,
                 QUERY_FAILED, TIMEOUT, INTENT_NOT_SQL, INTERNAL_ERROR]
        message:
          type: string
          description: 人类可读的错误描述
          example: "查询执行失败：表 'orders' 不存在"
        detail:
          type: string
          description: 详细调试信息（生产环境可关闭）
        sql:
          type: string
          description: 失败时的 SQL（如果有）
        suggestion:
          type: string
          description: 修复建议
          example: "请检查 Schema 配置，确保 'orders' 表已正确注册"

  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
      description: |
        API Key 认证。
        
        获取方式：
        1. 管理员在系统设置中生成 API Key
        2. 将 Key 配置到调用方的 Header 中
        
        格式：`X-API-Key: mgb_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx`
```

---

## 三、Java / .NET 集成方案

### 3.1 Java（Spring Boot）集成

#### 3.1.1 Maven 依赖

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-webflux-ui</artifactId>
    <version>2.3.0</version>
</dependency>
```

#### 3.1.2 客户端封装

```java
// MicroGenBIClient.java
package com.example.genbi;

import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.http.*;
import reactor.core.publisher.Mono;
import java.time.Duration;
import java.util.*;

@Component
public class MicroGenBIClient {

    private final WebClient client;

    public MicroGenBIClient(
            @Value("${microgenbi.base-url}") String baseUrl,
            @Value("${microgenbi.api-key}") String apiKey) {
        this.client = WebClient.builder()
                .baseUrl(baseUrl)
                .defaultHeader("X-API-Key", apiKey)
                .build();
    }

    // ── 同步查询 ─────────────────────────────────

    public MicroGenBIResponse query(String question) {
        return query(question, QueryOptions.builder().build());
    }

    public MicroGenBIResponse query(String question, QueryOptions opts) {
        Map<String, Object> body = new HashMap<>();
        body.put("query", question);
        if (opts.getSessionId() != null)
            body.put("session_id", opts.getSessionId());
        if (opts.getRole() != null)
            body.put("role", opts.getRole());
        body.put("generate_chart", opts.isGenerateChart());

        return client.post()
                .uri("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(MicroGenBIResponse.class)
                .block(Duration.ofSeconds(opts.getTimeoutSeconds()));
    }

    // ── 异步查询 + 轮询 ────────────────────────────

    public AsyncQueryHandle submitAsync(String question) {
        return submitAsync(question, QueryOptions.builder().build());
    }

    public AsyncQueryHandle submitAsync(String question, QueryOptions opts) {
        Map<String, Object> body = Map.of(
                "query", question,
                "generate_chart", opts.isGenerateChart()
        );

        TaskSubmitResponse submit = client.post()
                .uri("/api/v1/query/async")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(body)
                .retrieve()
                .bodyToMono(TaskSubmitResponse.class)
                .block();

        return new AsyncQueryHandle(submit.getTaskId(), submit.getSessionId(), this);
    }

    public TaskStatus pollTask(String taskId) {
        return client.get()
                .uri("/api/v1/task/{taskId}", taskId)
                .retrieve()
                .bodyToMono(TaskStatus.class)
                .block();
    }

    // ── Schema 管理 ────────────────────────────────

    public List<TableSchema> getSchema() {
        SchemaResponse resp = client.get()
                .uri("/api/v1/schema?include_relationships=true")
                .retrieve()
                .bodyToMono(SchemaResponse.class)
                .block();
        return resp.getTables();
    }

    public boolean testConnection(DatabaseConfig config) {
        ConnectionTestResponse resp = client.post()
                .uri("/api/v1/schema/test-connection")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(config)
                .retrieve()
                .bodyToMono(ConnectionTestResponse.class)
                .block();
        return resp.isSuccess();
    }

    // ── 导出 ─────────────────────────────────────

    public byte[] exportAsCsv(String sql) {
        return client.post()
                .uri("/api/v1/export")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue(Map.of("sql", sql, "format", "csv"))
                .accept(MediaType.APPLICATION_OCTET_STREAM)
                .retrieve()
                .bodyToMono(byte[].class)
                .block();
    }
}

// ── 查询选项 ───────────────────────────────────
@lombok.Builder
class QueryOptions {
    String sessionId;
    String role;           // admin, user, readonly
    boolean generateChart = true;
    String chartType;      // bar, line, pie, table
    int timeoutSeconds = 60;
}

// ── 异步查询句柄 ────────────────────────────────
class AsyncQueryHandle {
    private final String taskId;
    private final String sessionId;
    private final MicroGenBIClient client;
    private TaskStatus lastStatus;

    public AsyncQueryHandle(String taskId, String sessionId, MicroGenBIClient client) {
        this.taskId = taskId;
        this.sessionId = sessionId;
        this.client = client;
    }

    public TaskStatus poll() {
        this.lastStatus = client.pollTask(taskId);
        return lastStatus;
    }

    public boolean isDone() {
        if (lastStatus == null) poll();
        return lastStatus != null &&
                (lastStatus.getStatus() == TaskStatus.Status.SUCCESS
                || lastStatus.getStatus() == TaskStatus.Status.FAILED);
    }

    public TaskStatus waitForCompletion() {
        while (!isDone()) {
            try { Thread.sleep(1000); } catch (InterruptedException ignored) {}
        }
        return lastStatus;
    }

    public MicroGenBIResponse getResult() {
        if (lastStatus == null || lastStatus.getStatus() != TaskStatus.Status.SUCCESS)
            throw new IllegalStateException("Query not successful");
        return lastStatus.getResult();
    }
}
```

#### 3.1.3 在 Controller 中使用

```java
// DataQueryController.java
@RestController
@RequestMapping("/api/data")
@RequiredArgsConstructor
public class DataQueryController {

    private final MicroGenBIClient genbiClient;
    private final UserContext userContext;  // 从 Session/Token 获取当前用户

    @PostMapping("/query")
    public ApiResult<QueryResultVO> query(@RequestBody QueryDTO dto) {
        QueryOptions opts = QueryOptions.builder()
                .role(userContext.getRole())           // 自动注入用户角色
                .sessionId(dto.getSessionId())       // 传入则多轮对话
                .generateChart(true)
                .build();

        try {
            MicroGenBIResponse resp = genbiClient.query(dto.getQuestion(), opts);

            // 转换结果为前端 VO
            QueryResultVO vo = QueryResultVO.builder()
                    .sql(resp.getSql())
                    .data(resp.getData())
                    .columns(resp.getColumns())
                    .chartOptions(resp.getChart() != null
                            ? resp.getChart().getOptions() : null)
                    .summary(resp.getSummary())
                    .sessionId(resp.getSessionId())
                    .steps(resp.getSteps())
                    .build();

            return ApiResult.ok(vo);
        } catch (Exception e) {
            log.error("Micro-GenBI query failed", e);
            return ApiResult.fail("QUERY_FAILED", "查询失败: " + e.getMessage());
        }
    }

    // 导出接口
    @GetMapping("/export")
    public ResponseEntity<byte[]> export(
            @RequestParam String sessionId,
            @RequestParam(defaultValue = "csv") String format) {

        // 从会话历史获取 SQL
        SessionResponse session = genbiClient.getSession(sessionId);
        String lastSql = session.getEntries().getLast().getSql();

        byte[] data = genbiClient.exportAsCsv(lastSql);

        return ResponseEntity.ok()
                .header(HttpHeaders.CONTENT_DISPOSITION,
                        "attachment; filename=data_export." + format)
                .contentType(MediaType.APPLICATION_OCTET_STREAM)
                .body(data);
    }
}
```

#### 3.1.4 Spring Boot 配置

```yaml
# application.yml
microgenbi:
  base-url: http://localhost:8000
  api-key: ${MICRO_GENBI_API_KEY}  # 从环境变量读取
  timeout-seconds: 60

# 开启 OpenAPI UI
springdoc:
  api-docs:
    path: /api-docs
  swagger-ui:
    path: /swagger-ui.html
```

---

### 3.2 .NET (C# / WinForms / WPF / Blazor) 集成

#### 3.2.1 NuGet 依赖

```xml
<PackageReference Include="Microsoft.Extensions.Http" Version="8.0.0" />
<PackageReference Include="System.Text.Json" Version="8.0.0" />
<PackageReference Include="System.Reactive" Version="6.0.0" />  <!-- SSE 支持 -->
```

#### 3.2.2 .NET 客户端封装

```csharp
// MicroGenBIClient.cs
using System.Net.Http.Json;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace MicroGenBI.Client;

public class MicroGenBIClient : IDisposable
{
    private readonly HttpClient _http;
    private readonly string _apiKey;
    private readonly JsonSerializerOptions _jsonOpts;

    public MicroGenBIClient(string baseUrl, string apiKey)
    {
        _apiKey = apiKey;
        _http = new HttpClient { BaseAddress = new Uri(baseUrl) };
        _http.DefaultRequestHeaders.Add("X-API-Key", apiKey);
        _jsonOpts = new JsonSerializerOptions
        {
            PropertyNameCaseInsensitive = true,
            PropertyNamingPolicy = JsonNamingPolicy.CamelCase
        };
    }

    // ── 同步查询 ─────────────────────────────────

    public async Task<QueryResponse> QueryAsync(string question, QueryOptions? opts = null)
    {
        opts ??= new QueryOptions();
        var body = new Dictionary<string, object>
        {
            ["query"] = question,
            ["generate_chart"] = opts.GenerateChart
        };
        if (!string.IsNullOrEmpty(opts.SessionId))
            body["session_id"] = opts.SessionId;
        if (!string.IsNullOrEmpty(opts.Role))
            body["role"] = opts.Role;

        var resp = await _http.PostAsJsonAsync("/api/v1/query", body, _jsonOpts);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<QueryResponse>(_jsonOpts)
               ?? throw new InvalidOperationException("Failed to deserialize response");
    }

    // ── 异步查询 + 轮询 ────────────────────────────

    public async Task<AsyncQueryHandle> SubmitAsync(string question, QueryOptions? opts = null)
    {
        opts ??= new QueryOptions();
        var body = new { query = question, generate_chart = opts.GenerateChart };
        var resp = await _http.PostAsJsonAsync("/api/v1/query/async", body, _jsonOpts);
        resp.EnsureSuccessStatusCode();
        var submit = await resp.Content.ReadFromJsonAsync<TaskSubmitResponse>(_jsonOpts);
        return new AsyncQueryHandle(submit!.TaskId, submit.SessionId, _http, _jsonOpts);
    }

    // ── Schema 管理 ────────────────────────────────

    public async Task<SchemaResponse> GetSchemaAsync(bool includeRelationships = true)
    {
        var resp = await _http.GetAsync(
            $"/api/v1/schema?include_relationships={includeRelationships}");
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<SchemaResponse>(_jsonOpts)
               ?? throw new InvalidOperationException();
    }

    // ── 会话历史 ────────────────────────────────

    public async Task<SessionResponse> GetSessionAsync(string sessionId, int limit = 20)
    {
        var resp = await _http.GetAsync($"/api/v1/session/{sessionId}?limit={limit}");
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<SessionResponse>(_jsonOpts)
               ?? throw new InvalidOperationException();
    }

    // ── 导出 ────────────────────────────────────

    public async Task<byte[]> ExportAsync(string sql, string format = "csv")
    {
        var body = new { sql, format };
        var resp = await _http.PostAsJsonAsync("/api/v1/export", body, _jsonOpts);
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadAsByteArrayAsync();
    }

    // ── 健康检查 ────────────────────────────────

    public async Task<HealthResponse> HealthCheckAsync()
    {
        var resp = await _http.GetAsync("/api/v1/health");
        resp.EnsureSuccessStatusCode();
        return await resp.Content.ReadFromJsonAsync<HealthResponse>(_jsonOpts)
               ?? throw new InvalidOperationException();
    }

    public void Dispose() => _http.Dispose();
}

// ── 查询选项 ───────────────────────────────────

public class QueryOptions
{
    public string? SessionId { get; set; }
    public string? Role { get; set; }          // admin, user, readonly
    public bool GenerateChart { get; set; } = true;
    public string? ChartType { get; set; }     // bar, line, pie, table
    public int TimeoutSeconds { get; set; } = 60;
}

// ── 异步查询句柄 ────────────────────────────────

public class AsyncQueryHandle
{
    private readonly HttpClient _http;
    private readonly JsonSerializerOptions _jsonOpts;
    private TaskStatus? _lastStatus;

    public string TaskId { get; }
    public string SessionId { get; }

    public AsyncQueryHandle(string taskId, string sessionId,
                           HttpClient http, JsonSerializerOptions jsonOpts)
    {
        TaskId = taskId;
        SessionId = sessionId;
        _http = http;
        _jsonOpts = jsonOpts;
    }

    public async Task<TaskStatus> PollAsync()
    {
        var resp = await _http.GetAsync($"/api/v1/task/{TaskId}");
        resp.EnsureSuccessStatusCode();
        _lastStatus = await resp.Content.ReadFromJsonAsync<TaskStatus>(_jsonOpts);
        return _lastStatus!;
    }

    public bool IsDone => _lastStatus?.Status is "success" or "failed" or "cancelled";

    public async Task<TaskStatus> WaitForCompletionAsync(
        IProgress<int>? progress = null, CancellationToken ct = default)
    {
        while (!IsDone)
        {
            ct.ThrowIfCancellationRequested();
            var status = await PollAsync();
            progress?.Report((int)(status.Progress * 100));
            await Task.Delay(1000, ct);
        }
        return _lastStatus!;
    }

    public QueryResponse? GetResult()
    {
        if (_lastStatus?.Status != "success")
            throw new InvalidOperationException("Query not successful");
        return _lastStatus.Result;
    }
}
```

#### 3.2.3 WinForms 使用示例

```csharp
// DataQueryForm.cs
public partial class DataQueryForm : Form
{
    private MicroGenBIClient? _genbiClient;

    public DataQueryForm()
    {
        InitializeComponent();
        _genbiClient = new MicroGenBIClient(
            "http://localhost:8000",
            Environment.GetEnvironmentVariable("MICRO_GENBI_API_KEY") ?? ""
        );
    }

    private async void BtnQuery_Click(object sender, EventArgs e)
    {
        string question = txtQuestion.Text.Trim();
        if (string.IsNullOrEmpty(question)) return;

        btnQuery.Enabled = false;
        lblStatus.Text = "正在分析...";
        progressBar.Value = 0;

        try
        {
            // 同步查询（简单场景）
            var result = await _genbiClient!.QueryAsync(question);

            // 显示 SQL
            txtSql.Text = result.Sql;

            // 显示摘要
            txtSummary.Text = result.Summary;

            // 渲染图表（WinForms 用 WebBrowser 或 WebView2）
            if (result.Chart?.Options != null)
            {
                var chartJson = JsonSerializer.Serialize(result.Chart.Options);
                webChart.DocumentText = $@"
                    <html><head>
                    <script src='https://cdn.jsdelivr.net/npm/echarts@5.4.3/dist/echarts.min.js'></script>
                    </head><body>
                    <div id='chart' style='width:100%;height:400px;'></div>
                    <script>
                    var chart = echarts.init(document.getElementById('chart'));
                    chart.setOption({chartJson});
                    </script></body></html>";
            }
            else
            {
                // 显示数据表格
                dgvResult.DataSource = result.Data;
            }

            lblStatus.Text = $"完成 | {result.RowCount} 行 | 耗时 {result.Steps.TotalMs}ms";
        }
        catch (Exception ex)
        {
            MessageBox.Show($"查询失败: {ex.Message}", "错误",
                MessageBoxButtons.OK, MessageBoxIcon.Error);
            lblStatus.Text = "查询失败";
        }
        finally
        {
            btnQuery.Enabled = true;
        }
    }

    private async void BtnExport_Click(object sender, EventArgs e)
    {
        using var sfd = new SaveFileDialog
        {
            Filter = "CSV 文件|*.csv|Excel 文件|*.xlsx|JSON|*.json",
            FileName = $"导出数据_{DateTime.Now:yyyyMMdd_HHmmss}"
        };

        if (sfd.ShowDialog() != DialogResult.OK) return;

        var session = await _genbiClient!.GetSessionAsync(txtSessionId.Text);
        var lastSql = session.Entries.LastOrDefault()?.Sql;
        if (string.IsNullOrEmpty(lastSql))
        {
            MessageBox.Show("无历史查询可导出");
            return;
        }

        var format = Path.GetExtension(sfd.FileName).TrimStart('.').ToLower();
        var data = await _genbiClient.ExportAsync(lastSql, format);
        await File.WriteAllBytesAsync(sfd.FileName, data);
        MessageBox.Show("导出成功");
    }
}
```

#### 3.2.4 Blazor Server 使用示例

```razor
@* DataAssistant.razor *@
@page "/data-assistant"
@inject MicroGenBIClient GenBIClient

<div class="ai-assistant-panel">
    <div class="chat-messages">
        @foreach (var msg in messages)
        {
            <div class="message @(msg.IsUser ? "user" : "assistant")">
                @if (msg.IsUser)
                {
                    <div class="user-query">@msg.Query</div>
                }
                else
                {
                    <div class="assistant-response">
                        <pre class="sql-block">@msg.Sql</pre>
                        <div class="summary">@msg.Summary</div>
                        @if (msg.ChartOptions != null)
                        {
                            <div id="chart-@msg.Id" style="width:100%;height:300px;"></div>
                        }
                    </div>
                }
            </div>
        }

        @if (isLoading)
        {
            <div class="loading">
                <span>@statusMessage</span>
                <div class="progress-bar" style="width:@progress%"></div>
            </div>
        }
    </div>

    <div class="chat-input">
        <InputText @bind-Value="currentQuery" placeholder="输入你的数据问题..."
                   @onkeydown="HandleKeyDown" />
        <button @onclick="SendQuery" disabled="@isLoading">发送</button>
    </div>
</div>

@code {
    private string currentQuery = "";
    private bool isLoading = false;
    private string statusMessage = "";
    private int progress = 0;
    private List<ChatMessage> messages = new();

    private async Task SendQuery()
    {
        if (string.IsNullOrWhiteSpace(currentQuery)) return;

        var question = currentQuery;
        messages.Add(new ChatMessage { IsUser = true, Query = question });
        currentQuery = "";
        isLoading = true;
        statusMessage = "正在分析...";
        progress = 0;
        StateHasChanged();

        try
        {
            var handle = await GenBIClient.SubmitAsync(question);
            var result = await handle.WaitForCompletionAsync(
                new Progress<int>(p => progress = p));

            if (result.Status == "success" && result.Result != null)
            {
                messages.Add(new ChatMessage
                {
                    IsUser = false,
                    Sql = result.Result.Sql,
                    Summary = result.Result.Summary,
                    ChartOptions = result.Result.Chart?.Options,
                    SessionId = result.Result.SessionId
                });
            }
            else
            {
                messages.Add(new ChatMessage
                {
                    IsUser = false,
                    Summary = $"查询失败: {result.Error}"
                });
            }
        }
        catch (Exception ex)
        {
            messages.Add(new ChatMessage
            {
                IsUser = false,
                Summary = $"错误: {ex.Message}"
            });
        }
        finally
        {
            isLoading = false;
            StateHasChanged();
            // 渲染图表
            await JS.InvokeVoidAsync("renderAllCharts");
        }
    }

    private class ChatMessage
    {
        public bool IsUser { get; set; }
        public string? Query { get; set; }
        public string? Sql { get; set; }
        public string? Summary { get; set; }
        public object? ChartOptions { get; set; }
        public string? SessionId { get; set; }
        public Guid Id { get; set; } = Guid.NewGuid();
    }
}
```

---

## 四、前端原型扩展路线图

### 4.1 Tesla 风格系统扩展清单

基于 `prototype.html`，以下是需要增强的功能模块：

#### 高优先级（MVP 必做）

| 功能 | 当前状态 | 扩展目标 | 难度 |
|------|---------|---------|------|
| **执行步骤可视化** | 只有 mock 数据 | 真实 API 调用 + 5步进度指示（意图分析→Schema检索→SQL生成→验证→执行）| 中 |
| **Schema 管理面板** | 有静态数据 | 连接后端 API，支持展开/收起表结构，字段类型显示 | 中 |
| **错误状态展示** | 无 | 优雅的错误卡片（区分语法错误/表不存在/执行超时）| 低 |
| **图表交互增强** | 已有 ECharts | 增加图表类型切换按钮点击态、hover tooltip、图表下载为 PNG | 低 |
| **历史会话持久化** | 静态 mock | 调用 `/api/v1/sessions` 接口，SessionStorage 持久化 | 低 |

#### 中优先级（Phase 2）

| 功能 | 扩展目标 | 难度 |
|------|---------|------|
| **追问/继续会话** | 点击历史记录自动继续对话，follow-up 语义重写 | 中 |
| **相似查询推荐** | 基于历史查询向量相似度，推荐"你可能想问" | 中 |
| **SQL 审核模式** | 先生成 SQL，用户确认后才执行（toggle）| 低 |
| **导出功能** | CSV / Excel / JSON 导出，调用 `/api/v1/export` | 低 |
| **多轮对话上下文** | 侧边栏显示当前会话的对话历史树 | 中 |
| **数据库切换** | 顶部下拉框切换不同数据库连接 | 中 |

#### 低优先级（Phase 3+）

| 功能 | 扩展目标 | 难度 |
|------|---------|------|
| **实时 SSE 流** | 不用轮询，接入 `/api/v1/task/{id}/stream` SSE | 中 |
| **深色模式** | Tesla 风格白底，扩展 Dark Mode（Carbon Dark 主题）| 中 |
| **移动端适配** | 侧边栏可收起，图表响应式缩放 | 中 |
| **国际化** | 中文/English 切换（基于 vue-i18n 或原生）| 低 |
| **分享功能** | 生成分享链接（只读视图，可导出为图片）| 中 |

### 4.2 Tesla 风格 CSS 变量扩展

```css
/* 在现有 :root 基础上，增加以下变量 */

:root {
    /* 现有变量（保留）*/
    --blue: #3E6AE1;
    --blue-hover: #2f55b8;
    --white: #FFFFFF;
    --light-ash: #F4F4F4;
    --carbon: #171A20;
    --graphite: #393C41;
    --pewter: #5C5E62;
    --silver: #8E8E8E;
    --cloud: #EEEEEE;
    --pale-silver: #D0D1D2;

    /* ── 新增：交互反馈色 ─────────────────── */
    --success: #34C759;      /* Tesla 不用的绿色，用于成功状态 */
    --warning: #FF9500;      /* 警告橙 */
    --error: #FF3B30;        /* 错误红 */
    --info: #007AFF;         /* 信息蓝（略浅于 Electric Blue）*/

    /* ── 新增：图表色板 ─────────────────── */
    --chart-1: #3E6AE1;     /* Electric Blue */
    --chart-2: #E07B54;     /* Copper Orange */
    --chart-3: #56B8A0;     /* Sage Teal */
    --chart-4: #D4A843;     /* Amber Gold */
    --chart-5: #8B6FC0;     /* Violet */
    --chart-6: #5FA05F;     /* Forest Green */

    /* ── 新增：步骤指示器色 ─────────────────── */
    --step-pending: var(--cloud);
    --step-running: var(--blue);
    --step-success: var(--success);
    --step-error: var(--error);

    /* ── 新增：暗色模式变量 ─────────────────── */
    --dark-bg: #0D0D0F;
    --dark-surface: #1C1C1E;
    --dark-surface-2: #2C2C2E;
    --dark-text: #F5F5F7;
    --dark-text-secondary: #A1A1A6;
}

/* 步骤指示器样式 */
.step-item {
    display: flex;
    align-items: center;
    gap: 8px;
    padding: 6px 12px;
    border-radius: var(--r-btn);
    font-size: 13px;
    font-weight: 500;
    transition: all var(--t);
}

.step-item.pending {
    background: var(--light-ash);
    color: var(--silver);
}

.step-item.running {
    background: rgba(62, 106, 225, 0.1);
    color: var(--blue);
}

.step-item.success {
    background: rgba(52, 199, 89, 0.1);
    color: var(--success);
}

.step-item.error {
    background: rgba(255, 59, 48, 0.1);
    color: var(--error);
}

/* 错误卡片 */
.error-card {
    background: rgba(255, 59, 48, 0.06);
    border: 1px solid rgba(255, 59, 48, 0.2);
    border-radius: var(--r-card);
    padding: 14px 16px;
    display: flex;
    gap: 10px;
    align-items: flex-start;
}

.error-card-icon {
    width: 20px;
    height: 20px;
    background: var(--error);
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 11px;
    color: white;
    flex-shrink: 0;
    margin-top: 1px;
}

.error-card-content {
    flex: 1;
}

.error-card-title {
    font-size: 13px;
    font-weight: 500;
    color: var(--error);
    margin-bottom: 4px;
}

.error-card-message {
    font-size: 12px;
    color: var(--graphite);
    line-height: 1.5;
}

.error-card-suggestion {
    font-size: 12px;
    color: var(--pewter);
    margin-top: 6px;
    font-style: italic;
}
```

### 4.3 前端与后端联调接口映射

```javascript
// api.js - 前端 API 封装（对应后端 REST API）

const API_BASE = '/api/v1';  // 或配置为独立域名

const api = {
  // ── 查询接口 ─────────────────────────────────
  async query(question, options = {}) {
    const resp = await fetch(`${API_BASE}/query`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-API-Key': localStorage.getItem('microgenbi_api_key') || '',
        'X-User-Id': localStorage.getItem('user_id') || '',
        'X-User-Role': localStorage.getItem('user_role') || 'user',
      },
      body: JSON.stringify({
        query: question,
        session_id: options.sessionId || null,
        generate_chart: options.generateChart !== false,
        chart_type: options.chartType || null,
      }),
    });
    if (!resp.ok) {
      const err = await resp.json();
      throw new QueryError(err.error, err.message, err.detail);
    }
    return resp.json();
  },

  async queryAsync(question, options = {}) {
    const resp = await fetch(`${API_BASE}/query/async`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: question, generate_chart: true }),
    });
    const data = await resp.json();
    return {
      taskId: data.task_id,
      sessionId: data.session_id,
      pollUrl: data.poll_url,
      // 返回轮询函数
      poll: () => api.pollTask(data.task_id),
      streamUrl: data.stream_url,
    };
  },

  async pollTask(taskId) {
    const resp = await fetch(`${API_BASE}/task/${taskId}`);
    return resp.json();
  },

  // ── Schema 接口 ──────────────────────────────
  async getSchema() {
    const resp = await fetch(`${API_BASE}/schema?include_relationships=true`);
    return resp.json();
  },

  async testConnection(config) {
    const resp = await fetch(`${API_BASE}/schema/test-connection`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(config),
    });
    return resp.json();
  },

  // ── 会话接口 ────────────────────────────────
  async getSession(sessionId) {
    const resp = await fetch(`${API_BASE}/session/${sessionId}`);
    return resp.json();
  },

  async listSessions() {
    const resp = await fetch(`${API_BASE}/sessions`);
    return resp.json();
  },

  // ── 导出接口 ────────────────────────────────
  async exportData(sql, format = 'csv') {
    const resp = await fetch(`${API_BASE}/export`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ sql, format }),
    });
    return resp.blob();
  },
};

// ── 错误类 ───────────────────────────────────────
class QueryError extends Error {
  constructor(type, message, detail) {
    super(message);
    this.type = type;
    this.detail = detail;
  }

  get isRetryable() {
    return ['SYNTAX', 'SEMANTIC', 'TIMEOUT'].includes(this.type);
  }

  get userMessage() {
    const map = {
      SYNTAX: 'SQL 语法错误，请检查生成的语句',
      SEMANTIC: '表或列名不存在，请检查 Schema',
      TIMEOUT: '查询超时，请缩小查询范围',
      PERMISSION: '权限不足，请联系管理员',
      MAX_RETRIES: '查询多次失败，请简化问题',
      UNKNOWN: '未知错误',
    };
    return map[this.type] || this.message;
  }
}
```

---

## 五、完整部署架构

### 5.1 推荐架构图

```
                          ┌─────────────────────────────────────────────────────┐
                          │                    公网 / 内网                        │
                          └─────────────────────────┬───────────────────────────┘
                                                    │
                     ┌──────────────────────────────┼──────────────────────────┐
                     │                              │                          │
                     ▼                              ▼                          ▼
         ┌───────────────────────┐   ┌───────────────────────┐   ┌─────────────────┐
         │   Java Spring Boot     │   │   .NET WinForms/WPF    │   │   Blazor WASM   │
         │   (OA 管理系统)         │   │   (桌面客户端)          │   │   (Web 应用)    │
         │                        │   │                        │   │                 │
         │ MicroGenBIClient Bean  │   │ MicroGenBIClient C#   │   │ API Fetch/     │
         │ POST /api/v1/query     │   │ QueryAsync()          │   │ Blazor Interop  │
         └───────────┬───────────┘   └───────────┬───────────┘   └────────┬────────┘
                     │                           │                          │
                     └───────────────────────────┼──────────────────────────┘
                                                 │
                                    HTTPS + X-API-Key
                                                 │
                                                 ▼
                          ┌─────────────────────────────────────────────────────┐
                          │               Nginx / API Gateway                  │
                          │   - SSL 终结                                        │
                          │   - 限流 (rate_limit 100req/min per API-Key)       │
                          │   - IP 白名单 (可选)                               │
                          │   - 路径重写 / 负载均衡                            │
                          └──────────────────────────┬──────────────────────────┘
                                                     │
                     ┌───────────────────────────────┼───────────────────────┐
                     │                               │                       │
                     ▼                               ▼                       ▼
      ┌──────────────────────────┐  ┌──────────────────────────┐  ┌──────────────────┐
      │  Micro-GenBI Service      │  │  Micro-GenBI Service      │  │  Micro-GenBI     │
      │  (实例 1 - Python/FastAPI)│  │  (实例 2 - Python/FastAPI)│  │  Service (N...)  │
      │                          │  │                          │  │                  │
      │  FastAPI + Uvicorn        │  │  FastAPI + Uvicorn        │  │  ...             │
      │  - /api/v1/query         │  │  - /api/v1/query         │  │                  │
      │  - /api/v1/schema        │  │  - /api/v1/schema        │  │                  │
      │  - /api/v1/session       │  │  - /api/v1/session       │  │                  │
      │  - /api/v1/task          │  │  - /api/v1/task          │  │                  │
      │  - /api/v1/health        │  │  - /api/v1/health        │  │                  │
      └────────────┬─────────────┘  └────────────┬─────────────┘  └────────┬─────────┘
                   │                             │                          │
                   └─────────────────────────────┼──────────────────────────┘
                                               │
                              ┌────────────────┼────────────────┐
                              │                │                │
                              ▼                ▼                ▼
                   ┌────────────────┐ ┌────────────────┐ ┌─────────────────┐
                   │  MySQL/PG      │ │  LanceDB       │ │  Redis (可选)   │
                   │  (业务数据源)   │ │  (向量记忆)     │ │  (会话缓存)     │
                   │  仅 SELECT     │ │                │ │  (Phase 3)     │
                   └────────────────┘ └────────────────┘ └─────────────────┘
```

### 5.2 Docker Compose 一键部署

```yaml
# docker-compose.yml
version: '3.9'

services:
  # ── Micro-GenBI 后端服务 ──────────────────────
  micro-genbi:
    build:
      context: .
      dockerfile: docker/Dockerfile
    container_name: micro-genbi
    ports:
      - "8000:8000"
    environment:
      # 数据库配置
      - DATABASE_TYPE=mysql
      - DATABASE_HOST=${DB_HOST}
      - DATABASE_PORT=${DB_PORT}
      - DATABASE_NAME=${DB_NAME}
      - DATABASE_USER=${DB_USER}
      - DATABASE_PASSWORD=${DB_PASSWORD}
      - DATABASE_SSL=false
      
      # LLM 配置
      - LLM_PROVIDER=deepseek
      - LLM_API_KEY=${DEEPSEEK_API_KEY}
      - LLM_BASE_URL=https://api.deepseek.com
      - LLM_MODEL=deepseek-chat
      - LLM_TEMPERATURE=0.1
      - LLM_MAX_TOKENS=2000
      
      # Schema 配置
      - SCHEMA_YAML_PATH=/app/schema.yaml
      
      # 安全配置
      - API_KEY=${MICRO_GENBI_API_KEY}  # 管理员生成，用于 Java/.NET 调用
      - CORS_ORIGINS=https://your-java-app.com,https://your-net-app.com
      
      # 性能配置
      - MAX_EXECUTION_SECONDS=60
      - SQL_MAX_LIMIT=1000
      - MAX_CONCURRENT_QUERIES=10
      
      # LanceDB 配置
      - LANCEDB_PATH=/app/.memory
      
    volumes:
      - ./schema.yaml:/app/schema.yaml:ro
      - ./memory:/app/.memory
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/api/v1/health"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 40s
    deploy:
      resources:
        limits:
          cpus: '2'
          memory: 2G
        reservations:
          cpus: '0.5'
          memory: 512M

  # ── 推荐：Nginx 反向代理 ──────────────────────
  nginx:
    image: nginx:alpine
    container_name: micro-genbi-proxy
    ports:
      - "443:443"
      - "80:80"
    volumes:
      - ./docker/nginx.conf:/etc/nginx/nginx.conf:ro
      - ./docker/ssl:/etc/nginx/ssl:ro  # SSL 证书
    depends_on:
      - micro-genbi
    restart: unless-stopped

  # ── 可选：Redis 会话缓存（Phase 3）─────────────
  redis:
    image: redis:7-alpine
    container_name: micro-genbi-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    command: redis-server --appendonly yes
    restart: unless-stopped

volumes:
  redis_data:
```

### 5.3 Nginx 配置

```nginx
# docker/nginx.conf
events {
    worker_connections 1024;
}

http {
    # 限流配置
    limit_req_zone $binary_remote_addr zone=api_limit:10m rate=100r/m;
    limit_req_zone $http_x_api_key zone=apikey_limit:10m rate=1000r/m;

    # 上传大小限制
    client_max_body_size 10M;

    upstream micro_genbi {
        least_conn;
        server micro-genbi:8000 max_fails=3 fail_timeout=30s;
        # 水平扩展时添加更多 upstream
        # server micro-genbi-2:8000;
    }

    server {
        listen 443 ssl http2;
        server_name your-microgenbi-host.com;

        # SSL 配置
        ssl_certificate /etc/nginx/ssl/cert.pem;
        ssl_certificate_key /etc/nginx/ssl/key.pem;
        ssl_protocols TLSv1.2 TLSv1.3;
        ssl_ciphers HIGH:!aNULL:!MD5;

        # API 路由
        location /api/ {
            limit_req zone=apikey_limit burst=20 nodelay;
            
            proxy_pass http://micro_genbi;
            proxy_http_version 1.1;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
            
            # SSE 流支持
            proxy_buffering off;
            proxy_cache off;
            proxy_read_timeout 300s;
            
            # CORS（如果需要）
            add_header Access-Control-Allow-Origin $http_origin always;
            add_header Access-Control-Allow-Methods "GET, POST, OPTIONS" always;
            add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, X-User-Id, X-User-Role" always;
            
            if ($request_method = 'OPTIONS') {
                add_header Access-Control-Allow-Origin $http_origin;
                add_header Access-Control-Allow-Methods "GET, POST, OPTIONS";
                add_header Access-Control-Allow-Headers "Content-Type, X-API-Key, X-User-Id, X-User-Role";
                add_header Content-Length 0;
                add_header Content-Type text/plain;
                return 204;
            }
        }

        # OpenAPI 文档
        location /docs {
            proxy_pass http://micro_genbi;
            proxy_http_version 1.1;
        }

        # 健康检查（绕过限流）
        location /api/v1/health {
            limit_req off;
            proxy_pass http://micro_genbi;
            proxy_http_version 1.1;
        }

        # 静态文件（前端 SPA）
        location / {
            root /var/www/html;
            try_files $uri $uri/ /index.html;
        }
    }
}
```

### 5.4 环境变量配置

```bash
# .env 文件（不提交到 Git）
# ── 数据库配置 ────────────────────────────────
DB_HOST=localhost
DB_PORT=3306
DB_NAME=car_apply_record
DB_USER=genbi_readonly
DB_PASSWORD=your_secure_password_here

# ── Micro-GenBI 配置 ──────────────────────────
MICRO_GENBI_API_KEY=mgb_live_xxxxxxxxxxxxxxxxxxxxxxxxxxxx
# 生产环境生成方式：
# openssl rand -hex 32

# ── LLM 配置 ──────────────────────────────────
DEEPSEEK_API_KEY=sk-xxxxxxxxxxxxxxxxxxxxxxxxxxxx
LLM_PROVIDER=deepseek
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-chat
LLM_TEMPERATURE=0.1

# ── 安全配置 ──────────────────────────────────
CORS_ORIGINS=https://your-java-app.com,https://your-net-app.com
```

### 5.5 API Key 生成与分发策略

```python
# Micro-GenBI 内置 API Key 管理（admin 接口）
# POST /api/v1/admin/api-keys
# GET  /api/v1/admin/api-keys
# DELETE /api/v1/admin/api-keys/{key_id}

API Key 格式: mgb_live_<32位随机字符>
存储方式:  bcrypt 哈希后存数据库（不存明文）

权限分级:
- admin:  full access（所有接口，包括管理接口）
- service: query + schema（Java/.NET 集成用）
- readonly:  query only（只读报表嵌入）
```

---

## 六、实现优先级总览

```
Phase 1: MVP 核心闭环
═══════════════════════
  ✅ WrenAI 借鉴清单已明确（1.2 节）
  ✅ RESTful API 规格已设计（第二节）
  ✅ Java 客户端封装已提供（3.1 节）
  ✅ .NET 客户端封装已提供（3.2 节）
  ✅ Docker Compose 部署已提供（5.1 节）

Phase 2: 前后端联调
═══════════════════════
  🔜 对接 prototype.html → 真实后端 API
  🔜 执行步骤可视化（意图分析→SQL执行）
  🔜 Schema 管理面板（/api/v1/schema PUT）
  🔜 错误状态优雅展示
  🔜 导出功能（/api/v1/export）

Phase 3: 企业级增强
═══════════════════════
  📋 多轮对话上下文管理
  📋 相似查询推荐（LanceDB recall）
  📋 SQL 审核模式
  📋 Redis 会话缓存
  📋 MCP Server 接口
  📋 图表交互增强

Phase 4: 规模化
═══════════════════════
  📋 水平扩展（多实例 + Redis）
  📋 指标监控（Prometheus + Grafana）
  📋 SQL 执行日志审计
  📋 Cube 聚合层
  📋 多租户隔离
```

---

## 七、多模型支持与模型管理

### 7.1 设计目标

LLM 是 Text-to-SQL 系统质量的天花板。不同模型在不同场景下表现差异巨大，因此系统必须：

1. **可插拔**：任意 OpenAI-Compatible API 的推理模型都能接入
2. **可切换**：同一任务可切换不同模型，评估效果差异
3. **可配置**：每个模型有独立参数，支持按场景分配模型
4. **可观测**：记录每个模型的调用成本和质量指标

### 7.2 模型分类与角色

系统将 LLM 分为三个角色，不同任务使用不同模型：

```
┌─────────────────────────────────────────────────────────────────┐
│                     LLM 模型角色分层                              │
├────────────────────┬────────────────────────────────────────────┤
│ 意图分类模型        │ 小模型：意图分流（毫秒级，零 token 成本）      │
│ (Intent Model)    │ 推荐：Qwen2.5-1.5B / GPT-4o-mini / DeepSeek │
│                    │ 特点：速度快、成本低、够用就行                 │
├────────────────────┼────────────────────────────────────────────┤
│ SQL 生成模型        │ 主模型：SQL 生成（核心能力，决定准确率）         │
│ (Primary Model)   │ 推荐：Claude 4 Sonnet / GPT-4o / DeepSeek V3  │
│                    │ 特点：质量优先，成本其次                      │
├────────────────────┼────────────────────────────────────────────┤
│ SQL 修正模型        │ 小/主模型：自愈重试（简单修复，轻量即可）       │
│ (Correction Model) │ 推荐：与主模型相同，或用略低配版本             │
│                    │ 特点：可复用 Primary 模型                    │
├────────────────────┼────────────────────────────────────────────┤
│ 图表生成模型        │ 轻量模型：ECharts 配置生成                   │
│ (Chart Model)     │ 推荐：GPT-4o-mini / Qwen2.5-7B              │
│                    │ 特点：JSON 生成简单，廉价模型足够              │
├────────────────────┼────────────────────────────────────────────┤
│ 追问答复模型        │ 小模型：自然语言结果解释                      │
│ (Answer Model)     │ 推荐：GPT-4o-mini / Qwen2.5-7B              │
│                    │ 特点：格式化输出，廉价比主模型更优              │
└────────────────────┴────────────────────────────────────────────┘
```

### 7.3 模型配置文件

```yaml
# config/models.yaml
# 支持任意 OpenAI-Compatible API 的推理模型

providers:
  # ── Anthropic Claude ──────────────────────────
  anthropic:
    display_name: "Anthropic Claude"
    api_base: "https://api.anthropic.com"
    api_key_env: "ANTHROPIC_API_KEY"
    default_models:
      primary: "claude-sonnet-4-20250514"
      correction: "claude-sonnet-4-20250514"
      answer: "claude-haiku-4-20250514"
    timeout_seconds: 60

  # ── OpenAI ───────────────────────────────────
  openai:
    display_name: "OpenAI"
    api_base: "https://api.openai.com/v1"
    api_key_env: "OPENAI_API_KEY"
    default_models:
      primary: "gpt-4o"
      correction: "gpt-4o"
      chart: "gpt-4o-mini"
      answer: "gpt-4o-mini"
      intent: "gpt-4o-mini"
    timeout_seconds: 30

  # ── DeepSeek ─────────────────────────────────
  deepseek:
    display_name: "DeepSeek"
    api_base: "https://api.deepseek.com"
    api_key_env: "DEEPSEEK_API_KEY"
    default_models:
      primary: "deepseek-chat"
      correction: "deepseek-chat"
      chart: "deepseek-chat"
      answer: "deepseek-chat"
      intent: "deepseek-chat"
    timeout_seconds: 30

  # ── Azure OpenAI ─────────────────────────────
  azure_openai:
    display_name: "Azure OpenAI"
    api_base: "${AZURE_OPENAI_ENDPOINT}"  # 从环境变量读取
    api_key_env: "AZURE_OPENAI_KEY"
    api_version: "2024-06-01"
    default_models:
      primary: "gpt-4o"
      correction: "gpt-4o"
      chart: "gpt-4o-mini"
    timeout_seconds: 30

  # ── Ollama (本地) ────────────────────────────
  ollama:
    display_name: "Ollama (本地)"
    api_base: "http://localhost:11434/v1"
    api_key_env: ""  # Ollama 不需要 API Key
    default_models:
      primary: "qwen2.5:14b"
      correction: "qwen2.5:14b"
      chart: "qwen2.5:7b"
      answer: "qwen2.5:7b"
      intent: "qwen2.5:1.5b"  # 本地小模型做意图分类
    timeout_seconds: 120

  # ── 硅基流动 / Groq / 其他兼容 API ───────────
  siliconflow:
    display_name: "硅基流动"
    api_base: "https://api.siliconflow.cn/v1"
    api_key_env: "SILICONFLOW_API_KEY"
    default_models:
      primary: "Qwen/Qwen2.5-72B-Instruct"
      correction: "Qwen/Qwen2.5-14B-Instruct"
      intent: "Qwen/Qwen2.5-1.5B-Instruct"
    timeout_seconds: 60

  # ── 月之暗面 (Moonshot) ──────────────────────
  moonshot:
    display_name: "月之暗面 Moonshot"
    api_base: "https://api.moonshot.cn/v1"
    api_key_env: "MOONSHOT_API_KEY"
    default_models:
      primary: "moonshot-v1-128k"
      correction: "moonshot-v1-32k"
      chart: "moonshot-v1-32k"
    timeout_seconds: 30

  # ── 智谱 GLM ─────────────────────────────────
  zhipu:
    display_name: "智谱 AI (GLM)"
    api_base: "https://open.bigmodel.cn/api/paas/v4"
    api_key_env: "ZHIPU_API_KEY"
    default_models:
      primary: "glm-4-plus"
      correction: "glm-4-flash"
      chart: "glm-4-flash"
    timeout_seconds: 30

# ── 默认模型分配策略 ────────────────────────────────────────────
# 系统默认使用的模型组合（可按场景覆盖）
default_strategy:
  primary_model:
    provider: "deepseek"
    model: "deepseek-chat"
  intent_model:
    provider: "deepseek"
    model: "deepseek-chat"
  chart_model:
    provider: "openai"
    model: "gpt-4o-mini"
  answer_model:
    provider: "deepseek"
    model: "deepseek-chat"

# ── 模型能力评估矩阵（用于模型选择参考）────────────────────────────
# 评估维度：1-5 分
model_capabilities:
  "claude-sonnet-4-20250514":
    sql_accuracy: 5
    complex_join: 5
    chinese_understanding: 4
    cost_score: 3
    speed_score: 4

  "gpt-4o":
    sql_accuracy: 5
    complex_join: 5
    chinese_understanding: 5
    cost_score: 3
    speed_score: 4

  "deepseek-chat":
    sql_accuracy: 4
    complex_join: 4
    chinese_understanding: 5
    cost_score: 5
    speed_score: 4

  "qwen2.5:14b":
    sql_accuracy: 3
    complex_join: 3
    chinese_understanding: 5
    cost_score: 5
    speed_score: 3
```

### 7.4 Python LLM 客户端抽象

```python
# micro_genbi/llm/factory.py

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional, Literal
import os

# ── 模型配置 ────────────────────────────────────────────────────

@dataclass
class ModelConfig:
    provider: str                           # anthropic / openai / deepseek / ollama / ...
    model: str                            # 模型名称
    api_base: Optional[str] = None         # API 地址（覆盖默认）
    api_key: Optional[str] = None         # API Key（可从 env 读取）
    temperature: float = 0.1
    max_tokens: int = 2000
    timeout_seconds: int = 30
    extra_headers: dict = field(default_factory=dict)  # 特殊 Header

@dataclass
class ModelStrategy:
    """模型分配策略：不同任务用不同模型"""
    primary: ModelConfig      # SQL 生成（必须）
    intent: Optional[ModelConfig] = None       # 意图分类（可选，默认同 primary）
    correction: Optional[ModelConfig] = None      # SQL 修正（可选，默认同 primary）
    chart: Optional[ModelConfig = None]           # 图表生成（可选）
    answer: Optional[ModelConfig] = None          # 追问答复（可选）

# ── 统一接口 ────────────────────────────────────────────────────

class LLMClient(ABC):
    """所有 LLM 客户端的统一接口"""
    
    @abstractmethod
    async def generate(
        self,
        messages: list[dict],           # [{"role": "user", "content": "..."}]
        temperature: float = 0.1,
        max_tokens: int = 2000,
        stop: Optional[list[str]] = None,
    ) -> str:
        """同步生成文本，返回内容字符串"""
        pass

    @abstractmethod
    async def generate_structured(
        self,
        messages: list[dict],
        response_schema: dict,           # JSON Schema
    ) -> dict:
        """结构化输出（强制返回 JSON）"""
        pass

    @property
    @abstractmethod
    def provider_name(self) -> str:
        pass

# ── Anthropic Claude ────────────────────────────────────────────

class AnthropicClient(LLMClient):
    """Anthropic Claude SDK"""
    
    def __init__(self, config: ModelConfig):
        import anthropic
        self._client = anthropic.Anthropic(
            api_key=config.api_key or os.environ.get("ANTHROPIC_API_KEY"),
            base_url=config.api_base,
            timeout=config.timeout_seconds,
        )
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    async def generate(self, messages: list[dict], **kwargs) -> str:
        # 转换格式：OpenAI format → Anthropic format
        system = ""
        anthropic_msgs = []
        for msg in messages:
            if msg["role"] == "system":
                system = msg["content"]
            else:
                anthropic_msgs.append({
                    "role": msg["role"],
                    "content": msg["content"],
                })

        response = self._client.messages.create(
            model=self._model,
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
            temperature=kwargs.get("temperature", self._temperature),
            system=system,
            messages=anthropic_msgs,
        )
        return response.content[0].text

    async def generate_structured(self, messages: list[dict], response_schema: dict) -> dict:
        import json, anthropic
        
        # Claude 结构化输出：使用 JSON Schema 强制格式
        system = next((m["content"] for m in messages if m["role"] == "system"), "")
        anthropic_msgs = [m for m in messages if m["role"] != "system"]

        response = self._client.messages.create(
            model=self._model,
            max_tokens=4096,
            temperature=0.1,
            system=system + "\n\n你必须返回有效的 JSON，不能有其他内容。",
            messages=anthropic_msgs,
        )
        text = response.content[0].text.strip()
        # 提取 JSON
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    @property
    def provider_name(self) -> str:
        return "anthropic"

# ── OpenAI Compatible (通用) ───────────────────────────────────

class OpenAICompatibleClient(LLMClient):
    """
    通用 OpenAI-Compatible API 客户端。
    支持：OpenAI / DeepSeek / 硅基流动 / 智谱 / 月之暗面 / Ollama / Groq 等
    只需 API 符合 OpenAI SDK 格式即可。
    """
    
    def __init__(self, config: ModelConfig):
        try:
            from openai import AsyncOpenAI
        except ImportError:
            raise ImportError("请安装: pip install openai")
        
        self._client = AsyncOpenAI(
            api_key=config.api_key or os.environ.get("OPENAI_API_KEY", "dummy"),
            base_url=config.api_base,
            timeout=config.timeout_seconds,
            extra_headers=config.extra_headers or {},
        )
        self._model = config.model
        self._temperature = config.temperature
        self._max_tokens = config.max_tokens

    async def generate(self, messages: list[dict], **kwargs) -> str:
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=messages,
            temperature=kwargs.get("temperature", self._temperature),
            max_tokens=kwargs.get("max_tokens", self._max_tokens),
            stop=kwargs.get("stop"),
        )
        return response.choices[0].message.content or ""

    async def generate_structured(self, messages: list[dict], response_schema: dict) -> dict:
        import json
        
        # 方法1：使用 response_format（新版 API 支持）
        try:
            response = await self._client.chat.completions.create(
                model=self._model,
                messages=messages,
                response_format={"type": "json_schema", "json_schema": response_schema},
                temperature=0.1,
                max_tokens=4096,
            )
            text = response.choices[0].message.content or ""
            return json.loads(text.strip())
        except Exception:
            pass
        
        # 方法2：提示词约束（兼容所有 API）
        schema_str = json.dumps(response_schema, ensure_ascii=False)
        enhanced_messages = messages.copy()
        enhanced_messages.append({
            "role": "user",
            "content": f"\n\n【强制要求】你的回复必须是有效的 JSON，格式如下：\n{schema_str}\n不要输出任何其他内容。"
        })
        response = await self._client.chat.completions.create(
            model=self._model,
            messages=enhanced_messages,
            temperature=0.1,
            max_tokens=4096,
        )
        text = response.choices[0].message.content or ""
        if "```json" in text:
            text = text.split("```json")[1].split("```")[0]
        elif "```" in text:
            text = text.split("```")[1].split("```")[0]
        return json.loads(text.strip())

    @property
    def provider_name(self) -> str:
        return "openai-compatible"

# ── 模型工厂 ────────────────────────────────────────────────────

class LLMFactory:
    """
    统一工厂：从配置文件创建 LLM 客户端。
    支持从 YAML 配置文件加载。
    """
    
    _REGISTRY: dict[str, type[LLMClient]] = {
        "anthropic": AnthropicClient,
        "openai": OpenAICompatibleClient,
        "deepseek": OpenAICompatibleClient,
        "azure_openai": OpenAICompatibleClient,
        "ollama": OpenAICompatibleClient,
        "siliconflow": OpenAICompatibleClient,
        "moonshot": OpenAICompatibleClient,
        "zhipu": OpenAICompatibleClient,
    }

    @classmethod
    def create(cls, config: ModelConfig) -> LLMClient:
        provider = config.provider.lower()
        
        if provider not in cls._REGISTRY:
            available = ", ".join(cls._REGISTRY.keys())
            raise ValueError(
                f"不支持的 LLM Provider: {provider}。"
                f"支持的 Provider: {available}"
            )
        
        # 从环境变量读取 API Key
        if not config.api_key:
            env_var = cls._get_env_var_for_provider(provider)
            if env_var:
                config.api_key = os.environ.get(env_var, "")
        
        return cls._REGISTRY[provider](config)

    @classmethod
    def from_yaml(cls, yaml_path: str, role: str = "primary") -> LLMClient:
        """从 YAML 配置创建客户端"""
        import yaml
        with open(yaml_path) as f:
            cfg = yaml.safe_load(f)
        
        strategy = cfg.get("default_strategy", {})
        provider_cfg = cfg["providers"].get(strategy.get(f"{role}_model", {}).get("provider", "deepseek"))
        
        model_name = strategy.get(f"{role}_model", {}).get("model", "deepseek-chat")
        
        return cls.create(ModelConfig(
            provider=provider_cfg.get("display_name", "").lower().split()[0],
            model=model_name,
            api_base=provider_cfg.get("api_base"),
            api_key_env=provider_cfg.get("api_key_env"),
            timeout_seconds=provider_cfg.get("timeout_seconds", 30),
        ))

    @staticmethod
    def _get_env_var_for_provider(provider: str) -> Optional[str]:
        mapping = {
            "anthropic": "ANTHROPIC_API_KEY",
            "openai": "OPENAI_API_KEY",
            "deepseek": "DEEPSEEK_API_KEY",
            "azure_openai": "AZURE_OPENAI_KEY",
            "ollama": None,
            "siliconflow": "SILICONFLOW_API_KEY",
            "moonshot": "MOONSHOT_API_KEY",
            "zhipu": "ZHIPU_API_KEY",
        }
        return mapping.get(provider)

# ── 模型选择器（自动选最优模型）──────────────────────────────────

class ModelRouter:
    """
    根据任务类型自动路由到最合适的模型。
    
    策略：
    - 意图分类：优先本地/廉价模型
    - SQL 生成：优先质量（Primary Model）
    - SQL 修正：与 Primary 相同
    - 图表生成：可复用 Primary 或用廉价版
    - 追问答复：廉价模型即可
    """
    
    def __init__(self, strategy: ModelStrategy):
        self._strategy = strategy

    async def get_intent_model(self) -> LLMClient:
        cfg = self._strategy.intent or self._strategy.primary
        return LLMFactory.create(cfg)

    async def get_primary_model(self) -> LLMClient:
        return LLMFactory.create(self._strategy.primary)

    async def get_correction_model(self) -> LLMClient:
        cfg = self._strategy.correction or self._strategy.primary
        return LLMFactory.create(cfg)

    async def get_chart_model(self) -> LLMClient:
        cfg = self._strategy.chart or self._strategy.primary
        return LLMFactory.create(cfg)

    async def get_answer_model(self) -> LLMClient:
        cfg = self._strategy.answer or self._strategy.primary
        return LLMFactory.create(cfg)
```

### 7.5 模型质量评估与自动切换

```python
# micro_genbi/llm/evaluator.py

@dataclass
class ModelEvaluation:
    """模型质量评估记录"""
    model_id: str              # provider:model
    date: str
    total_queries: int         # 总查询数
    success_count: int          # 成功数
    sql_accuracy: float         # SQL 执行成功率
    avg_latency_ms: float
    avg_cost: float             # 平均成本（USD）
    user_satisfaction: float    # 用户满意度（1-5）
    correction_rate: float      # 需要修正的比例

class ModelEvaluator:
    """
    持续评估各模型质量，自动推荐最优模型组合。
    
    评估维度：
    1. SQL 准确率：SQL 执行是否成功
    2. 修正率：需要多少次 Self-Correction 才能成功
    3. 延迟：P50 / P95 / P99 响应时间
    4. 成本：每次查询的平均 Token 成本
    5. 用户反馈：用户是否认可结果
    """
    
    def __init__(self, db_path: str = "./.microgenbi/evaluations.db"):
        self._db_path = db_path
        self._con = sqlite3.connect(db_path)
        self._create_tables()

    def record_query(
        self,
        model_id: str,
        query: str,
        generated_sql: str,
        execution_success: bool,
        correction_count: int,
        latency_ms: float,
        tokens_used: int,
    ):
        import datetime
        self._con.execute("""
            INSERT INTO query_records 
            (model_id, query, sql, success, corrections, latency_ms, tokens, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (model_id, query, generated_sql, execution_success,
              correction_count, latency_ms, tokens_used, datetime.datetime.now().isoformat()))
        self._con.commit()

    def get_best_model_for_task(self, task: str) -> str:
        """根据历史数据推荐最优模型"""
        rows = self._con.execute("""
            SELECT model_id, 
                   COUNT(*) as total,
                   AVG(CASE WHEN corrections = 0 THEN 1.0 ELSE 0.0 END) as zero_correction_rate,
                   AVG(latency_ms) as avg_latency
            FROM query_records
            WHERE task_type = ?
            GROUP BY model_id
            ORDER BY zero_correction_rate DESC, avg_latency ASC
            LIMIT 1
        """, (task,)).fetchall()
        return rows[0][0] if rows else None

    def get_usage_stats(self, model_id: str, days: int = 30) -> ModelEvaluation:
        rows = self._con.execute("""
            SELECT 
                COUNT(*) as total,
                SUM(CASE WHEN success THEN 1 ELSE 0 END) as successes,
                AVG(latency_ms) as avg_latency,
                AVG(corrections) as avg_corrections,
                AVG(tokens * 0.00001) as est_cost
            FROM query_records
            WHERE model_id = ?
              AND created_at > datetime('now', ?)
        """, (model_id, f"-{days} days")).fetchone()
        
        return ModelEvaluation(
            model_id=model_id,
            date=datetime.datetime.now().strftime("%Y-%m-%d"),
            total_queries=rows[0],
            success_count=rows[1] or 0,
            sql_accuracy=rows[1] / rows[0] if rows[0] > 0 else 0,
            avg_latency_ms=rows[2] or 0,
            avg_cost=rows[4] or 0,
            correction_rate=rows[3] or 0,
            user_satisfaction=0,  # 需要从用户反馈接口获取
        )
```

---

## 八、细粒度读写权限控制与写操作安全

### 8.1 权限分层架构

系统权限分为四个独立维度，每个维度独立控制：

```
┌─────────────────────────────────────────────────────────────────┐
│                     四维权限控制体系                               │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  维度 1: 运营权限 (Operation Permission)                         │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ NONE      ← 不允许任何 SQL 操作                           │   │
│  │ READ      ← 只读查询（默认）                              │   │
│  │ READ_WRITE ← 读写（需额外审批）                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  维度 2: 表级权限 (Table Permission)                            │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 全表白名单 / 表黑名单 / 精确到单表的读/写权限             │   │
│  │ 例：orders:rw, customers:r, products:-, secret: NONE    │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  维度 3: 操作类型权限 (Action Permission)                        │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ SELECT ✓  │  INSERT ✗  │  UPDATE ✗  │  DELETE ✗         │   │
│  │ CREATE TABLE ✗  │  DROP ✗  │  TRUNCATE ✗               │   │
│  │ ALTER ✗  │  GRANT ✗   │  LOAD ✗                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  维度 4: 额度限制 (Quota Permission)                             │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ 每小时最大查询数 / 每次最大扫描行数 / 每日最大 Token 消耗   │   │
│  │ 表级写入审批阈值 / 危险操作二次确认                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 8.2 权限配置模型

```python
# micro_genbi/security/permissions.py

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

class OperationLevel(Enum):
    NONE = "none"      # 无任何操作权限
    READ = "read"     # 只读（默认）
    READ_WRITE = "read_write"  # 读写（需审批）

class ActionType(Enum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    TRUNCATE = "TRUNCATE"
    DROP = "DROP"
    ALTER = "ALTER"
    CREATE = "CREATE"
    GRANT = "GRANT"
    REVOKE = "REVOKE"
    LOAD_DATA = "LOAD_DATA"
    INTO_OUTFILE = "INTO_OUTFILE"
    BENCHMARK = "BENCHMARK"
    SLEEP = "SLEEP"

# ── 单表权限 ────────────────────────────────────────────────────

@dataclass
class TablePermission:
    """单张表的读写权限"""
    table_name: str                    # 表名（支持通配符 orders_*）
    allow_select: bool = True
    allow_insert: bool = False
    allow_update: bool = False
    allow_delete: bool = False
    allowed_columns: Optional[list[str]] = None  # 列级白名单，None=全部
    denied_columns: Optional[list[str]] = None   # 列级黑名单
    max_rows_per_write: int = 100      # 单次写入最大行数
    require_approval: bool = True       # 是否需要审批（写操作）
    conditions: Optional[str] = None  # 行级条件（如 "status = 'active'"）

# ── 用户/角色权限配置 ─────────────────────────────────────────────

@dataclass
class PermissionProfile:
    """权限配置模板"""
    name: str                          # admin / data_analyst / developer / readonly / ...
    
    # 运营级别
    operation_level: OperationLevel = OperationLevel.READ
    
    # 允许的操作类型（只读=仅SELECT，读写=全操作）
    allowed_actions: set[ActionType] = field(
        default_factory=lambda: {ActionType.SELECT}
    )
    
    # 表级权限列表（精确匹配优先于通配符）
    table_permissions: list[TablePermission] = field(default_factory=list)
    
    # 表级黑名单（无论其他配置，一律拒绝）
    blocked_tables: set[str] = field(default_factory=set)
    
    # 表级白名单（不在列表中则默认拒绝）
    use_whitelist_mode: bool = False
    
    # 额度限制
    quota: "QuotaLimit" = field(default_factory=lambda: QuotaLimit())

    def can_select_table(self, table: str) -> bool:
        if table in self.blocked_tables:
            return False
        if self.use_whitelist_mode:
            return any(p.table_name == table and p.allow_select for p in self.table_permissions)
        return True

    def can_write_table(self, table: str, action: ActionType) -> bool:
        if self.operation_level != OperationLevel.READ_WRITE:
            return False
        if table in self.blocked_tables:
            return False
        if action not in self.allowed_actions:
            return False
        return True

    def requires_approval(self, table: str, action: ActionType) -> bool:
        for p in self.table_permissions:
            if p.table_name == table:
                if action == ActionType.INSERT and p.allow_insert:
                    return p.require_approval
                if action == ActionType.UPDATE and p.allow_update:
                    return p.require_approval
                if action == ActionType.DELETE and p.allow_delete:
                    return p.require_approval
        return False

@dataclass
class QuotaLimit:
    """额度限制"""
    max_queries_per_hour: int = 100
    max_tokens_per_day: int = 100_000_000
    max_rows_per_query: int = 1000          # SELECT 结果行数上限
    max_write_rows_per_hour: int = 100     # 写入行数上限
    max_concurrent_queries: int = 5
    require_manual_approval_above: int = 1000  # 超过此行数需人工审批

# ── 预定义权限模板 ────────────────────────────────────────────────

PERMISSION_TEMPLATES: dict[str, PermissionProfile] = {
    "readonly": PermissionProfile(
        name="readonly",
        operation_level=OperationLevel.READ,
        allowed_actions={ActionType.SELECT},
        use_whitelist_mode=True,
        table_permissions=[
            TablePermission("orders", allow_select=True),
            TablePermission("customers", allow_select=True),
            TablePermission("products", allow_select=True),
        ],
        blocked_tables={"employees_salary", "user_credentials"},
    ),
    
    "data_analyst": PermissionProfile(
        name="data_analyst",
        operation_level=OperationLevel.READ,
        allowed_actions={ActionType.SELECT},
        use_whitelist_mode=True,
        table_permissions=[
            TablePermission("orders", allow_select=True),
            TablePermission("customers", allow_select=True),
            TablePermission("products", allow_select=True),
            TablePermission("dept_expense", allow_select=True),
            TablePermission("car_apply_record", allow_select=True),
        ],
        blocked_tables={"employees_salary", "user_credentials"},
    ),
    
    "developer": PermissionProfile(
        name="developer",
        operation_level=OperationLevel.READ_WRITE,
        allowed_actions={ActionType.SELECT, ActionType.INSERT, ActionType.UPDATE},
        use_whitelist_mode=True,
        table_permissions=[
            TablePermission("orders", allow_select=True, allow_insert=True, allow_update=True,
                           denied_columns=["total_amount", "status"]),  # 禁止修改金额和状态
            TablePermission("customers", allow_select=True, allow_insert=True),
            TablePermission("*", allow_select=True),  # 其他表只读
        ],
        blocked_tables={"employees_salary", "user_credentials"},
        quota=QuotaLimit(max_write_rows_per_hour=500, require_manual_approval_above=100),
    ),
    
    "admin": PermissionProfile(
        name="admin",
        operation_level=OperationLevel.READ_WRITE,
        allowed_actions={
            ActionType.SELECT, ActionType.INSERT, ActionType.UPDATE,
            ActionType.DELETE, ActionType.CREATE, ActionType.DROP, ActionType.ALTER,
        },
        blocked_tables=set(),  # 无黑名单
        use_whitelist_mode=False,  # 黑名单模式
    ),
}
```

### 8.3 权限配置文件

```yaml
# config/permissions.yaml
# 系统级权限配置

permission_version: "1.0"

# ── 预定义角色 ────────────────────────────────────────────────

roles:
  readonly:
    description: "只读分析师 - 仅允许查询指定表"
    operation_level: read
    allowed_actions: [SELECT]
    use_whitelist_mode: true
    blocked_tables:
      - employees_salary
      - user_credentials
      - audit_logs
    tables:
      - name: orders
        allow_select: true
      - name: customers
        allow_select: true
      - name: products
        allow_select: true

  data_analyst:
    description: "数据分析员 - 查询为主，可访问大部分表"
    operation_level: read
    allowed_actions: [SELECT]
    use_whitelist_mode: true
    blocked_tables:
      - employees_salary
      - user_credentials
    tables:
      - name: orders
        allow_select: true
      - name: customers
        allow_select: true
      - name: products
        allow_select: true
      - name: dept_expense
        allow_select: true
      - name: car_apply_record
        allow_select: true

  developer:
    description: "开发人员 - 可读写部分表，限制危险列"
    operation_level: read_write
    allowed_actions: [SELECT, INSERT, UPDATE]
    use_whitelist_mode: true
    blocked_tables:
      - employees_salary
      - user_credentials
    tables:
      - name: orders
        allow_select: true
        allow_insert: true
        allow_update: true
        denied_columns:        # 禁止修改的列
          - total_amount
          - status
          - created_at
      - name: customers
        allow_select: true
        allow_insert: true
        allow_update: true
        denied_columns:
          - created_at
      - name: "*"            # 其他表只读
        allow_select: true
    quotas:
      max_write_rows_per_hour: 500
      require_manual_approval_above: 100

  admin:
    description: "管理员 - 全部权限（仅内部使用）"
    operation_level: read_write
    allowed_actions: [SELECT, INSERT, UPDATE, DELETE, CREATE, DROP, ALTER]
    use_whitelist_mode: false
    blocked_tables: []

# ── 表级默认权限（未匹配角色时的兜底规则）─────────────────────────

default_table_permissions:
  SELECT: "*"           # 默认允许 SELECT
  INSERT: []            # 默认禁止 INSERT
  UPDATE: []
  DELETE: []

# ── 全局安全策略 ────────────────────────────────────────────────

global_policy:
  # 危险操作零容忍（无论什么角色都禁止）
  always_blocked_actions:
    - DROP DATABASE
    - DROP TABLE
    - TRUNCATE
    - GRANT
    - REVOKE
    - INTO OUTFILE
    - LOAD_FILE
    - BENCHMARK
    - SLEEP

  # 危险函数（sqlglot AST 检查）
  always_blocked_functions:
    - BENCHMARK
    - SLEEP
    - GET_LOCK
    - RELEASE_LOCK
    - LOAD_FILE
    - LOAD_DATA
    - INTO OUTFILE

  # 默认 LIMIT
  default_select_limit: 1000
  max_select_limit: 10000
  max_write_rows: 1000

  # 审批流程（写操作）
  approval_workflow:
    enabled: true
    auto_approve_below: 10       # 10 行以下自动审批
    require_manual_above: 100    # 100 行以上强制人工审批
    approvers:
      - role: admin
      - role: data_owner

  # 数据库连接（只读账号）
  read_only_connection: true     # 强制使用只读数据库账号
  write_connection_requires_explicit: true  # 写操作需显式开启
```

### 8.4 多租户权限隔离

```python
# micro_genbi/security/tenant_isolation.py

@dataclass
class TenantContext:
    """多租户上下文"""
    tenant_id: str           # 租户 ID
    user_id: str              # 用户 ID
    role: str                 # 权限角色
    profile: PermissionProfile  # 权限配置
    session_id: str           # 会话 ID
    ip_address: str           # 来源 IP
    user_agent: str           # 来源 UA
    created_at: datetime

class TenantIsolationMiddleware:
    """
    多租户隔离中间件。
    每个请求携带租户上下文，权限检查在执行前进行。
    """
    
    def __init__(self, permission_loader: "PermissionLoader"):
        self._loader = permission_loader
        self._cache: dict[str, PermissionProfile] = {}

    async def resolve_context(self, request) -> TenantContext:
        """从请求中解析租户上下文"""
        # 优先级：Header → Cookie → Token → 默认
        tenant_id = (
            request.headers.get("X-Tenant-Id") or
            request.headers.get("X-Org-Id") or
            "default"
        )
        user_id = (
            request.headers.get("X-User-Id") or
            request.headers.get("X-Client-Id") or
            "anonymous"
        )
        role = request.headers.get("X-User-Role", "readonly")
        api_key = request.headers.get("X-API-Key")

        # API Key 校验（独立于用户角色）
        if api_key:
            key_profile = await self._loader.load_by_api_key(api_key)
            if key_profile:
                role = key_profile.name

        profile = await self._loader.load_profile(role, tenant_id)
        
        return TenantContext(
            tenant_id=tenant_id,
            user_id=user_id,
            role=role,
            profile=profile,
            session_id=request.headers.get("X-Session-Id", ""),
            ip_address=self._get_client_ip(request),
            user_agent=request.headers.get("User-Agent", ""),
            created_at=datetime.datetime.now(),
        )
```

### 8.5 写操作安全检查器（核心）

```python
# micro_genbi/security/write_guard.py

class WriteOperationGuard:
    """
    写操作安全守卫 — 写操作的最后一道防线。
    
    设计原则：纵深防御，写操作必须通过以下所有检查：
    
    检查层级 1: AST 词法分析（零通过则拒绝）
    检查层级 2: 语义权限验证（零通过则拒绝）
    检查层级 3: 行数额度控制
    检查层级 4: 审批流程（可选）
    检查层级 5: 数据库连接验证
    检查层级 6: 双重确认（危险操作）
    """

    def __init__(
        self,
        permission_loader: "PermissionLoader",
        audit_logger: "AuditLogger",
    ):
        self._loader = permission_loader
        self._audit = audit_logger

    async def guard_write(
        self,
        sql: str,
        context: TenantContext,
        action: ActionType,
    ) -> "WriteGuardResult":
        """
        守卫写操作，返回检查结果。
        必须通过所有层级才能执行。
        """
        
        # ── Layer 1: AST 解析 + 危险操作检测 ──────────────────
        safety_result = await self._layer1_ast_check(sql, action)
        if not safety_result.allowed:
            await self._audit.log_denied(
                context=context,
                sql=sql,
                reason=safety_result.reason,
                layer=1,
            )
            return WriteGuardResult(
                allowed=False,
                reason=safety_result.reason,
                layer=1,
            )

        # ── Layer 2: 表/列权限验证 ────────────────────────────
        auth_result = await self._layer2_permission_check(sql, action, context)
        if not auth_result.allowed:
            await self._audit.log_denied(
                context=context,
                sql=sql,
                reason=auth_result.reason,
                layer=2,
            )
            return WriteGuardResult(
                allowed=False,
                reason=auth_result.reason,
                layer=2,
            )

        # ── Layer 3: 额度检查 ────────────────────────────────
        quota_result = await self._layer3_quota_check(context)
        if not quota_result.allowed:
            await self._audit.log_quota_exceeded(context, quota_result)
            return WriteGuardResult(
                allowed=False,
                reason=f"额度超限：{quota_result.reason}",
                layer=3,
            )

        # ── Layer 4: 审批流程 ───────────────────────────────
        approval_result = await self._layer4_approval_check(sql, action, context)
        if approval_result.require_manual_approval:
            # 返回待审批状态，不立即执行
            return WriteGuardResult(
                allowed=False,
                reason="需要管理员审批",
                layer=4,
                require_approval=True,
                approval_id=approval_result.approval_id,
            )

        # ── Layer 5: 数据库连接验证 ───────────────────────────
        if not self._verify_write_connection():
            return WriteGuardResult(
                allowed=False,
                reason="数据库只读连接，无法执行写操作",
                layer=5,
            )

        # ── Layer 6: 危险操作双重确认 ────────────────────────
        danger_result = self._layer6_danger_check(sql, action)
        if danger_result.is_high_risk:
            # 返回需要确认状态
            return WriteGuardResult(
                allowed=False,
                reason="危险操作需二次确认",
                layer=6,
                require_confirmation=True,
                danger_assessment=danger_result,
            )

        # ── 全部通过 ────────────────────────────────────────
        await self._audit.log_allowed(context=context, sql=sql, action=action)
        return WriteGuardResult(allowed=True)

    # ── Layer 1: AST 危险检测 ────────────────────────────────

    async def _layer1_ast_check(
        self, sql: str, action: ActionType
    ) -> SafetyCheckResult:
        """AST 层：检测危险操作和函数"""
        import sqlglot
        from sqlglot import exp

        # 1.1 危险关键词正则预检（快）
        danger_keywords = [
            r"\bDROP\b", r"\bTRUNCATE\b", r"\bGRANT\b", r"\bREVOKE\b",
            r"\bINTO\s+OUTFILE\b", r"\bLOAD\s+FILE\b", r"\bBENCHMARK\b",
            r"\bSLEEP\s*\(", r"\bGET_LOCK\b", r"\bRELEASE_LOCK\b",
        ]
        for pattern in danger_keywords:
            if re.search(pattern, sql, re.IGNORECASE):
                return SafetyCheckResult(
                    allowed=False,
                    reason=f"检测到危险关键词：{pattern}",
                    blocked_keyword=pattern,
                )

        # 1.2 sqlglot AST 深度检测（准）
        try:
            for node in sqlglot.parse(sql, dialect=self._dialect):
                for blocked_type in [
                    exp.Drop, exp.Truncate, exp.Alter, exp.Create,
                    exp.Grant, exp.Revoke,
                ]:
                    if node.find_all(blocked_type):
                        return SafetyCheckResult(
                            allowed=False,
                            reason=f"AST 检测到禁止操作：{blocked_type.__name__}",
                        )
                
                # 检测 INTO OUTFILE / LOAD DATA
                for func in node.find_all(exp.Anonymous):
                    if func.name.upper() in {
                        "INTO_OUTFILE", "LOAD_FILE", "LOAD_DATA_INFILE",
                        "BENCHMARK", "SLEEP", "GET_LOCK", "RELEASE_LOCK",
                    }:
                        return SafetyCheckResult(
                            allowed=False,
                            reason=f"检测到危险函数：{func.name}",
                        )

                # 递归检查所有子查询和 CTE
                for subquery in node.find_all(exp.Subquery):
                    sub_sql = subquery.sql(dialect=self._dialect)
                    result = await self._layer1_ast_check(sub_sql, action)
                    if not result.allowed:
                        return result

        except Exception as e:
            return SafetyCheckResult(
                allowed=False,
                reason=f"SQL 解析失败，无法执行：{str(e)}",
            )

        return SafetyCheckResult(allowed=True)

    # ── Layer 2: 权限验证 ────────────────────────────────────

    async def _layer2_permission_check(
        self,
        sql: str,
        action: ActionType,
        context: TenantContext,
    ) -> SafetyCheckResult:
        """表/列级权限验证"""
        import sqlglot
        from sqlglot import exp

        profile = context.profile

        # 2.1 运营级别检查
        if action not in profile.allowed_actions:
            return SafetyCheckResult(
                allowed=False,
                reason=f"操作 {action.value} 不在允许列表中",
            )

        # 2.2 提取所有涉及的表
        referenced_tables = set()
        try:
            for node in sqlglot.parse(sql, dialect=self._dialect):
                for table in node.find_all(exp.Table):
                    referenced_tables.add(table.name.lower())
        except Exception:
            return SafetyCheckResult(
                allowed=False,
                reason="无法解析 SQL 表引用",
            )

        # 2.3 表级白名单/黑名单检查
        for table in referenced_tables:
            if not profile.can_select_table(table):
                return SafetyCheckResult(
                    allowed=False,
                    reason=f"表 {table} 不在权限范围内",
                )
            
            if not profile.can_write_table(table, action):
                return SafetyCheckResult(
                    allowed=False,
                    reason=f"无权限对表 {table} 执行 {action.value}",
                )

        # 2.4 列级权限检查（UPDATE/INSERT）
        if action in (ActionType.UPDATE, ActionType.INSERT):
            for table, denied_cols in self._extract_denied_columns(sql, action):
                table_perm = next(
                    (p for p in profile.table_permissions if p.table_name == table),
                    None
                )
                if table_perm and table_perm.denied_columns:
                    referenced_cols = set(denied_cols)
                    overlap = referenced_cols & set(table_perm.denied_columns)
                    if overlap:
                        return SafetyCheckResult(
                            allowed=False,
                            reason=f"禁止修改列：{overlap}",
                        )

        # 2.5 行级条件检查（ACL 注入）
        # 已有的 ACL 注入在 SQL 执行层进行，这里做最终验证
        return SafetyCheckResult(allowed=True)

    # ── Layer 6: 危险操作双重确认 ───────────────────────────

    @dataclass
    class DangerAssessment:
        is_high_risk: bool
        risk_score: float      # 0.0 ~ 1.0
        risk_factors: list[str]
        estimated_affected_rows: Optional[int] = None

    def _layer6_danger_check(
        self, sql: str, action: ActionType
    ) -> DangerAssessment:
        """评估操作危险等级，触发双重确认"""
        risk_factors = []
        risk_score = 0.0

        # 无 WHERE 的 UPDATE / DELETE → 极高风险
        if action in (ActionType.UPDATE, ActionType.DELETE):
            if not re.search(r"\bWHERE\b", sql, re.IGNORECASE):
                risk_factors.append("无 WHERE 条件的 UPDATE/DELETE")
                risk_score += 0.5

        # 批量操作
        if action == ActionType.INSERT:
            values_count = len(re.findall(r"\),\s*\(", sql, re.IGNORECASE)) + 1
            if values_count > 10:
                risk_factors.append(f"批量插入 {values_count} 行")
                risk_score += 0.3

        # 涉及金额/余额字段
        danger_fields = ["amount", "balance", "salary", "password", "credential"]
        for field in danger_fields:
            if field in sql.lower():
                risk_factors.append(f"涉及敏感字段：{field}")
                risk_score += 0.2

        return self.DangerAssessment(
            is_high_risk=risk_score >= 0.5,
            risk_score=risk_score,
            risk_factors=risk_factors,
        )

@dataclass
class WriteGuardResult:
    allowed: bool
    reason: str = ""
    layer: int = 0                          # 在哪一层失败
    require_approval: bool = False         # 需要审批
    approval_id: Optional[str] = None      # 审批单 ID
    require_confirmation: bool = False     # 需要二次确认
    danger_assessment: Optional[WriteOperationGuard.DangerAssessment] = None
```

### 8.6 审批工作流

```python
# micro_genbi/security/approval.py

class WriteApprovalWorkflow:
    """
    写操作审批工作流。
    
    流程：
    1. 写操作被 WriteGuard 拦截
    2. 创建审批单（状态：pending）
    3. 通知审批人（可选：Webhook / 邮件 / 内部消息）
    4. 审批人通过 API 审批或拒绝
    5. 通过后执行写操作，结果通知申请人
    """

    async def create_approval(
        self,
        sql: str,
        context: TenantContext,
        action: ActionType,
        estimated_rows: int,
    ) -> ApprovalRequest:
        approval_id = f"apr_{uuid.uuid4().hex[:12]}"
        request = ApprovalRequest(
            id=approval_id,
            sql=sql,
            action=action.value,
            requester_id=context.user_id,
            tenant_id=context.tenant_id,
            requested_at=datetime.datetime.now(),
            status="pending",
            estimated_rows=estimated_rows,
            danger_score=0,  # 来自 WriteGuard
            reason="",  # 用户填写的申请理由
            approvers=[],  # 自动分配的审批人
        )
        await self._db.save(request)
        await self._notify_approvers(request)
        return request

    async def approve(self, approval_id: str, approver_id: str) -> bool:
        request = await self._db.load(approval_id)
        if request.status != "pending":
            return False
        if approver_id not in request.approvers:
            return False
        
        # 执行写操作
        result = await self._execute_write(request.sql, request.context)
        
        request.status = "approved"
        request.approved_at = datetime.datetime.now()
        request.approved_by = approver_id
        request.execution_result = result
        await self._db.save(request)
        
        await self._notify_requester(request)
        return True

    async def reject(self, approval_id: str, approver_id: str, reason: str) -> bool:
        request = await self._db.load(approval_id)
        request.status = "rejected"
        request.rejected_at = datetime.datetime.now()
        request.rejected_by = approver_id
        request.rejection_reason = reason
        await self._db.save(request)
        await self._notify_requester(request)
        return True
```

### 8.7 REST API 权限管理接口

```yaml
# 新增权限管理 API 端点

paths:
  # ── 权限配置管理 ─────────────────────────────────

  /api/v1/admin/roles:
    get:
      operationId: listRoles
      summary: "列出所有权限角色"
      tags: [Admin]
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                properties:
                  roles:
                    type: array
                    items:
                      $ref: '#/components/schemas/PermissionProfile'

    post:
      operationId: createRole
      summary: "创建新的权限角色"
      tags: [Admin]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              $ref: '#/components/schemas/PermissionProfile'
      responses:
        '201':
          description: 创建成功
        '400':
          description: 配置格式错误
        '403':
          description: 只有 admin 可以操作

  /api/v1/admin/roles/{role_name}:
    put:
      operationId: updateRole
      summary: "更新角色权限配置"
      tags: [Admin]
    delete:
      operationId: deleteRole
      summary: "删除角色（不可删除预定义角色）"
      tags: [Admin]

  # ── 审批管理 ─────────────────────────────────

  /api/v1/approvals:
    get:
      operationId: listPendingApprovals
      summary: "列出待审批的写操作申请"
      description: "审批人查看自己待审批的申请列表"
      tags: [Approval]
      parameters:
        - name: status
          in: query
          schema:
            type: string
            enum: [pending, approved, rejected]
          default: pending
      responses:
        '200':
          content:
            application/json:
              schema:
                type: object
                properties:
                  approvals:
                    type: array
                    items:
                      $ref: '#/components/schemas/ApprovalRequest'

  /api/v1/approvals/{approval_id}:
    post:
      operationId: decideApproval
      summary: "审批通过或拒绝"
      tags: [Approval]
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              required: [decision]
              properties:
                decision:
                  type: string
                  enum: [approve, reject]
                reason:
                  type: string
                  description: "拒绝时必须填写理由"
      responses:
        '200':
          description: 审批完成
        '404':
          description: 审批单不存在
        '403':
          description: 不是该申请的审批人"
```

### 8.8 Java / .NET 权限配置示例

```java
// Java: 权限配置（调用方）
public class MicroGenBIWriteExample {

    public void insertOrder(MicroGenBIClient client, Order order) {
        // 写操作需要特定 Header
        var headers = new HttpHeaders();
        headers.set("X-User-Role", "developer");    // developer 角色允许 INSERT
        headers.set("X-API-Key", apiKey);

        // 构建写操作请求
        var request = new WriteRequest();
        request.setSql(String.format(
            "INSERT INTO orders (customer_id, total_amount) VALUES (%d, %.2f)",
            order.getCustomerId(), order.getTotalAmount()
        ));
        request.setAction("INSERT");
        request.setReason("批量导入订单数据");

        // 提交写操作（返回审批单 ID 或执行结果）
        var response = client.write(request, headers);
        
        if (response.requireApproval()) {
            // 等待审批（可轮询或 WebSocket 通知）
            String approvalId = response.getApprovalId();
            System.out.println("写操作需审批，审批单ID: " + approvalId);
            // 通知管理员审批...
        } else if (response.isExecuted()) {
            System.out.println("写入成功，影响行数: " + response.getAffectedRows());
        }
    }
}
```

```csharp
// C#: 权限示例
public class WriteOperationExample {

    public async Task SubmitWriteRequest(string sql, string reason)
    {
        var headers = new Dictionary<string, string>
        {
            ["X-User-Role"] = "developer",
            ["X-API-Key"] = _apiKey,
        };

        var response = await _client.PostAsync("/api/v1/write", new
        {
            sql = sql,
            action = "INSERT",
            reason = reason,
        }, headers);

        if (response.RequireApproval)
        {
            Console.WriteLine($"需要审批: {response.ApprovalId}");
            // 发送内部通知给审批人...
        }
    }
}
```

---

### 附录：文档结构索引

```
Micro-GenBI-Integration.md 完整结构：

  一、WrenAI 借鉴 vs 自研：边界矩阵
     1.1 总体原则
     1.2 详细模块对照表
     1.3 WrenAI SDK 源码借鉴清单

  二、RESTful API 设计（Java / .NET 集成方案）
     2.1 设计原则
     2.2 API 完整规格（14 个端点）

  三、Java / .NET 集成方案
     3.1 Java (Spring Boot) 集成
     3.2 .NET (C#) 集成

  四、前端原型扩展路线图
     4.1 高优先级（MVP 必做）
     4.2 中优先级（Phase 2）
     4.3 低优先级（Phase 3+）
     4.4 Tesla 风格 CSS 扩展
     4.5 前端 API 封装

  五、完整部署架构
     5.1 架构图
     5.2 Docker Compose
     5.3 Nginx 配置
     5.4 环境变量
     5.5 API Key 管理

  六、实现优先级总览

▶ 七、多模型支持与模型管理（新增）
     7.1 设计目标
     7.2 模型分类与角色
     7.3 模型配置文件（YAML）
     7.4 Python LLM 客户端抽象
     7.5 模型质量评估与自动切换

▶ 八、细粒度读写权限控制与写操作安全（新增）
     8.1 权限分层架构（四维）
     8.2 权限配置模型（Python）
     8.3 权限配置文件（YAML）
     8.4 多租户权限隔离
     8.5 写操作安全检查器（核心，6层防御）
     8.6 审批工作流
     8.7 REST API 权限管理接口
     8.8 Java / .NET 权限配置示例

---

## 九、PRD 模式整合状态与补充功能

### 9.1 PRD 五大模式整合现状

`GenBI_Integration_PRD.md` 定义了 5 大 Claude Code 架构模式，以下是逐一核对：

| PRD 模式 | 状态 | 说明 |
|---------|------|------|
| **模式一：Prompt Cache Economics** | ✅ **已集成** | 见 `Micro-GenBI-Plan.md` 中的 `PromptAssembler` 和 `_build_prompt()` — Static Prefix（System Prompt + DDL + Schema）固定不变，Dynamic Tail（History）动态追加 |
| **模式二：Blast Radius Permission** | ✅ **已集成** | 见 Section 8 — 物理层只读账号 + 词法层 sqlglot AST 拦截（6层防御） |
| **模式三：Hook Governance Layer** | ❌ **未集成** | 业务字典注入 — PRD 中描述为"PreToolUse Hook"，当前方案中仅有 schema.yaml 静态配置，缺少**动态字典查询注入**机制 |
| **模式四：Context Hygiene System** | ⚠️ **部分集成** | PRD 中描述：PostToolUse Hook 截断 + 图表 JSON，方案中仅在 `ChartEngine` 和 `AskHistoryManager` 中隐式处理，**缺少显式 Hook 框架** |
| **模式五：Behavior Institutionalization** | ⚠️ **部分集成** | LIMIT 1000 在 `SafetyValidator` 中已实现，`SELECT *` 禁止在 prompt 中要求但**缺少 sqlglot AST 检测** |

### 9.2 缺失功能 1：Hook Governance Layer（钩子治理）

PRD 描述：用户说"公车私用"，AI 不知道对应数据库里的字典值。需要 PreToolUse Hook 自动注入业务字典。

```python
# micro_genbi/pipeline/hooks.py

from dataclasses import dataclass, field
from typing import Optional, Callable
from abc import ABC, abstractmethod
import re

# ── Hook 基类 ─────────────────────────────────────────────────

class PreToolUseHook(ABC):
    """执行前钩子抽象基类"""
    
    @abstractmethod
    async def before_tool_use(self, context: "HookContext") -> "HookContext":
        """在工具执行前修改上下文。返回修改后的上下文。"""
        pass

class PostToolUseHook(ABC):
    """执行后钩子抽象基类"""
    
    @abstractmethod
    async def after_tool_use(
        self,
        context: "HookContext",
        result: "ToolResult",
    ) -> "HookResult":
        """
        在工具执行后处理结果。
        返回给 Agent 的内容（截断/摘要）和给前端的内容（图表/表格）。
        """
        pass

@dataclass
class HookContext:
    """Hook 上下文，在所有 Hook 间传递"""
    query: str                          # 用户原始问题
    rewritten_query: str                # 重写后的查询（可能注入了字典）
    intent: str                         # 意图分类结果
    schema_context: str                 # Schema 上下文
    history_context: str                 # 多轮对话上下文
    user_role: str                     # 用户角色
    user_id: str                       # 用户 ID
    additional_context: dict = field(default_factory=dict)  # 额外注入的上下文

@dataclass
class ToolResult:
    """工具执行结果"""
    success: bool
    data: list[dict] = None
    columns: list[str] = None
    row_count: int = 0
    error: str = None

@dataclass
class HookResult:
    """Hook 执行后的结果"""
    # 返回给 LLM 的上下文（截断后）
    llm_summary: str                     # "查询成功，返回 10,000 行数据"
    # 返回给前端的内容
    chart_options: Optional[dict] = None
    table_data: Optional[list[dict]] = None
    # 追加到上下文的文本（给下一个 LLM 调用用）
    injected_context: str = ""
    # 是否截断了数据
    truncated: bool = False
    truncated_count: int = 0

# ── 字典注入 Hook（模式三核心实现）─────────────────────────────

class DictionaryInjectionHook(PreToolUseHook):
    """
    PreToolUse Hook：自动将业务黑话转换为数据库字典值。

    痛点：用户说"公车私用"，AI 不知道对应数据库里的字典值。
    解决：当检测到业务关键词时，自动从后端字典表查询映射，
          注入为 Additional Context。

    注入效果：
    原始问题："查询公车私用的订单"
    注入后：  "查询 type='private' AND purpose='公车私用' 的订单"
    """

    def __init__(
        self,
        db_executor: "DBExecutor",
        dictionary_cache: dict = None,  # 预加载字典
    ):
        self._db = db_executor
        self._cache = dictionary_cache or {}  # 内存缓存

        # ── 业务黑话正则匹配（可配置化）─────────────────────
        self._keyword_patterns = {
            # 报销相关
            r"公车私用": {"field": "expense_type", "mapping": {"私用": "private", "公用": "business"}},
            r"差旅": {"field": "expense_type", "mapping": {"差旅": "travel", "出差": "travel"}},
            r"招待": {"field": "expense_type", "mapping": {"招待": "entertainment"}},
            r"采购": {"field": "expense_type", "mapping": {"采购": "procurement"}},

            # 订单相关
            r"待支付|未支付": {"field": "status", "mapping": {"待支付": "pending", "未支付": "pending"}},
            r"已完成": {"field": "status", "mapping": {"已完成": "completed"}},
            r"已取消": {"field": "status", "mapping": {"已取消": "cancelled"}},

            # 客户相关
            r"高价值|VIP|优质": {"field": "customer_tier", "mapping": {"高价值": "premium", "VIP": "premium"}},
            r"新客户|新增客户": {"field": "customer_type", "mapping": {"新客户": "new"}},

            # 部门相关（从数据库字典表动态加载）
            r"销售部|销售部门": {"field": "dept_name", "dynamic": True},
            r"技术部|研发部": {"field": "dept_name", "dynamic": True},
        }

    async def before_tool_use(self, context: HookContext) -> HookContext:
        """检测业务关键词，自动注入字典映射"""
        query = context.query
        injected_items = []

        for pattern, config in self._keyword_patterns.items():
            if re.search(pattern, query):
                field = config["field"]

                # 动态：从数据库字典表加载
                if config.get("dynamic"):
                    mapping = await self._load_dynamic_mapping(field)
                else:
                    mapping = config["mapping"]

                # 构建注入文本
                for keyword, db_value in mapping.items():
                    if keyword in query:
                        injected_items.append(
                            f"/* 字典注入 [{field}]：{keyword} → {db_value} */"
                        )

                        # 同时注入 Additional Context
                        if "dictionary_injection" not in context.additional_context:
                            context.additional_context["dictionary_injection"] = {}
                        context.additional_context["dictionary_injection"][field] = {
                            "keyword": keyword,
                            "db_value": db_value,
                        }

        if injected_items:
            # 追加到重写后的查询中
            context.rewritten_query = (
                f"{' '.join(injected_items)}\n{query}"
            )
            context.additional_context["injected_keywords"] = injected_items

        return context

    async def _load_dynamic_mapping(self, field: str) -> dict[str, str]:
        """从数据库字典表动态加载映射"""
        if field in self._cache:
            return self._cache[field]

        # 从数据库字典表查询（示例）
        # 实际实现：从 schema.yaml 配置的字典表读取
        try:
            sql = f"""
                SELECT keyword, db_value
                FROM data_dictionary
                WHERE field_name = '{field}'
            """
            rows = await self._db.execute_raw(sql)
            mapping = {row["keyword"]: row["db_value"] for row in rows}
            self._cache[field] = mapping
            return mapping
        except Exception:
            return {}

# ── 数据截断 Hook（模式四核心实现）─────────────────────────────

class DataTruncationHook(PostToolUseHook):
    """
    PostToolUse Hook：将海量数据截断并生成图表/表格。
    
    核心原则（Context Hygiene）：
    - 全量数据**绝不**进入 LLM 对话上下文
    - 返回给 LLM 的只是一条精简摘要
    - 全量数据转为图表 JSON 传给前端
    """

    # 阈值配置
    FULL_RESULT_THRESHOLD = 10       # 10 行以下 → 全量返回
    CHART_THRESHOLD = 10            # 10 行以上 → 图表生成
    LLM_CONTEXT_TRUNCATE = 5        # 传给 LLM 上下文的最大行数

    def __init__(
        self,
        chart_engine: "ChartEngine",
        llm_client: "LLMClient",
    ):
        self._chart = chart_engine
        self._llm = llm_client

    async def after_tool_use(
        self,
        context: HookContext,
        result: ToolResult,
    ) -> HookResult:
        """截断数据，生成图表/表格，返回精简摘要"""

        if not result.success:
            return HookResult(llm_summary=f"查询失败：{result.error}")

        data = result.data or []
        columns = result.columns or []
        row_count = result.row_count
        truncated = len(data) >= 1000  # 被 LIMIT 截断

        # ── 情况 1: 10 行以下 → 直接返回 ──────────────────
        if len(data) <= self.FULL_RESULT_THRESHOLD:
            return HookResult(
                llm_summary=f"查询成功，返回 {row_count} 行数据：\n"
                           + self._format_sample(data[:5]),
                table_data=data,
                truncated=truncated,
                truncated_count=row_count - len(data),
            )

        # ── 情况 2: 10 行以上 → 生成图表 ──────────────────
        chart_result = await self._chart.generate_echarts_options(
            query=context.query,
            sql=context.additional_context.get("generated_sql", ""),
            data=data,
            columns=columns,
        )

        # 截断原始数据用于传给 LLM（Context Hygiene）
        sample_data = data[:self.LLM_CONTEXT_TRUNCATE]

        # 生成 LLM 摘要（用 LLM 生成自然语言摘要）
        llm_summary = await self._generate_llm_summary(
            query=context.query,
            row_count=row_count,
            sample=sample_data,
            columns=columns,
        )

        return HookResult(
            llm_summary=llm_summary,
            chart_options=chart_result.get("options"),
            table_data=data,  # 前端保留全量
            truncated=truncated,
            truncated_count=row_count - len(data),
            injected_context=self._build_injected_context(data, columns),
        )

    async def _generate_llm_summary(
        self,
        query: str,
        row_count: int,
        sample: list[dict],
        columns: list[str],
    ) -> str:
        """用 LLM 生成自然语言摘要（传少量样本即可）"""
        prompt = {
            "system": "你是一个数据分析助手。根据以下查询结果的摘要，用 1-2 句话简洁地描述结果。不要输出其他内容。",
            "user": (
                f"问题：{query}\n"
                f"总行数：{row_count}\n"
                f"列名：{columns}\n"
                f"数据摘要（前5行）：{sample}"
            ),
        }
        summary = await self._llm.generate(prompt, temperature=0.1, max_tokens=100)
        return f"查询成功，共 {row_count} 行数据。前端已渲染图表。\n\n{sample}\n\nLLM 摘要：{summary}"

    @staticmethod
    def _format_sample(data: list[dict]) -> str:
        if not data:
            return "(空结果)"
        cols = list(data[0].keys())
        header = " | ".join(cols)
        rows = [" | ".join(str(row.get(c, "")) for c in cols) for row in data[:5]]
        return f"\n{header}\n" + "\n".join(rows)

    @staticmethod
    def _build_injected_context(data: list[dict], columns: list[str]) -> str:
        """构建传给下一个 LLM 调用的精简上下文"""
        if not data:
            return "/* 查询结果为空 */"
        sample = data[:3]
        return (
            "/* 参考数据（前 3 行）：\n"
            + "\n".join(
                f"/* {row}" for row in DataTruncationHook._format_sample(sample).split("\n")
            )
            + "\n*/"
        )

# ── Hook Pipeline（编排所有 Hook）───────────────────────────────

class HookPipeline:
    """
    Hook 流水线：按顺序执行所有 PreHook → Tool → 所有 PostHook。
    PRD 中的"PreToolUse Hook"和"PostToolUse Hook"在这里组装。
    """

    def __init__(self):
        self._pre_hooks: list[PreToolUseHook] = []
        self._post_hooks: list[PostToolUseHook] = []

    def add_pre_hook(self, hook: PreToolUseHook):
        self._pre_hooks.append(hook)

    def add_post_hook(self, hook: PostToolUseHook):
        self._post_hooks.append(hook)

    async def execute(
        self,
        context: HookContext,
        tool_func: Callable,
    ) -> HookResult:
        # ── Step 1: 所有 PreHook 依次执行 ──────────────────
        current_context = context
        for hook in self._pre_hooks:
            current_context = await hook.before_tool_use(current_context)

        # ── Step 2: 执行实际的 Tool（SQL 执行）───────────────
        tool_result = await tool_func(current_context)

        # ── Step 3: 所有 PostHook 依次执行 ─────────────────
        current_result = tool_result
        final_hook_result = None
        for hook in self._post_hooks:
            hook_result = await hook.after_tool_use(current_context, current_result)
            current_result = hook_result  # 最后一个 PostHook 的结果作为最终结果
            if final_hook_result is None:
                final_hook_result = hook_result

        return final_hook_result or HookResult(llm_summary="执行完成")
```

### 9.3 缺失功能 2：SELECT * 检测与 Prompt 铁律强化

```python
# micro_genbi/pipeline/sql_style_guard.py

class SQLStyleGuard:
    """
    模式五强化实现：SQL 编写铁律强制检查。
    
    铁律：
    1. 禁止 SELECT * — 必须显式列出字段
    2. 禁止无 LIMIT 的查询
    3. 禁止不带 ORDER BY 的 TOP/LIMIT（可能导致结果不稳定）
    4. 禁止在 WHERE 中使用函数包裹列（如 WHERE YEAR(date) = 2024）
    """

    async def validate(self, sql: str) -> "StyleCheckResult":
        violations = []

        # 1. 检测 SELECT *
        if re.search(r"\bSELECT\s+\*\b", sql, re.IGNORECASE):
            violations.append(StyleViolation(
                rule="no_select_star",
                severity="error",
                message="禁止使用 SELECT *，必须显式列出需要的字段名",
                suggestion="SELECT id, name, status FROM orders",
            ))

        # 2. 检测无 LIMIT（通过 sqlglot AST 检查）
        tree = sqlglot.parse_one(sql, dialect=self._dialect)
        if not tree.find(exp.Limit):
            violations.append(StyleViolation(
                rule="require_limit",
                severity="warning",
                message="建议添加 LIMIT 子句防止扫描过多数据",
                suggestion="添加 LIMIT 1000",
            ))

        # 3. 检测无 ORDER BY 的 TOP/LIMIT（可能导致非确定性结果）
        has_order = bool(tree.find(exp.Order))
        has_limit = bool(tree.find(exp.Limit))
        if has_limit and not has_order and self._dialect in ("mssql",):
            violations.append(StyleViolation(
                rule="recommend_order_by",
                severity="warning",
                message="LIMIT 在没有 ORDER BY 时结果不稳定，建议添加 ORDER BY",
            ))

        # 4. 检测 WHERE 中对列使用函数包裹
        for node in tree.find_all(exp.Filter):
            if isinstance(node.this, exp.Anonymous):
                violations.append(StyleViolation(
                    rule="no_function_on_column",
                    severity="warning",
                    message=f"WHERE 条件中对列使用函数 {node.this.name}() 会导致索引失效",
                    suggestion="使用日期范围条件替代，如 date >= '2024-01-01'",
                ))

        has_errors = any(v.severity == "error" for v in violations)
        return StyleCheckResult(
            passed=not has_errors,
            violations=violations,
            sql=sql,
        )
```

### 9.4 建议新增功能

经过全面分析，以下 6 项功能值得补充到系统中：

#### 9.4.1 SQL 执行日志与审计追溯

**设计目标**：所有查询（无论成功/失败/拒绝）全部记录，用于合规审计、问题排查、安全告警。

**存储策略**：
- 近 30 天：高速存储（SQLite / PostgreSQL）
- 30 天以上：自动归档到对象存储（OSS / S3）

```python
# micro_genbi/security/audit.py

import sqlite3
import json
import hashlib
import asyncio
import threading
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# ── 数据模型 ─────────────────────────────────────────────────────

class ExecutionResult(str, Enum):
    SUCCESS = "SUCCESS"       # SQL 执行成功
    FAILED = "FAILED"        # SQL 执行失败（语法/语义/超时）
    DENIED = "DENIED"        # 被安全检查拒绝
    PENDING = "PENDING"      # 执行中
    CANCELLED = "CANCELLED"   # 被用户取消

@dataclass
class AuditLogEntry:
    """审计日志条目 — 所有字段均为不可变或强制初始化"""
    log_id: str
    created_at: datetime
    user_id: str
    role: str
    tenant_id: str
    ip_address: str
    session_id: str
    user_agent: str

    # 查询信息
    query: str                           # 用户原始问题
    rewritten_query: str = ""            # 字典注入后的重写问题
    intent: str = ""                    # 意图分类结果

    # SQL 信息
    generated_sql: str = ""             # 生成的 SQL（脱敏后）
    sql_hash: str = ""                  # SQL 的 SHA256 哈希（追溯用）
    sql_dialect: str = ""              # 数据库方言

    # 执行结果
    execution_result: ExecutionResult = ExecutionResult.PENDING
    error_type: str = ""               # SYNTAX / SEMANTIC / TIMEOUT / PERMISSION
    denied_reason: str = ""            # 拒绝原因（DENIED 时）
    denied_at_layer: int = 0           # 在哪一层被拒绝（1-6）
    denied_sql: str = ""               # 被拒绝的 SQL（用于调试）

    # 性能数据
    latency_ms: int = 0
    sql_planning_ms: int = 0
    sql_execution_ms: int = 0
    tokens_used: int = 0
    model_used: str = ""

    # 数据统计
    row_count: int = 0                 # 返回行数
    rows_scanned: int = 0             # 扫描行数（从 EXPLAIN 获取）
    truncated: bool = False            # 是否被 LIMIT 截断

    # 危险评估
    danger_score: float = 0.0         # 0.0~1.0，WriteGuard 评估
    is_write_operation: bool = False   # 是否为写操作
    required_approval: bool = False    # 是否触发了审批流程

    # 关联追踪
    parent_log_id: str = ""           # 追问/follow-up 的父日志 ID
    correction_count: int = 0          # Self-Correction 重试次数
    task_id: str = ""

    def __post_init__(self):
        if not self.log_id:
            import uuid
            self.log_id = f"aud_{datetime.now().strftime('%Y%m%d')}_{uuid.uuid4().hex[:16]}"
        if not self.created_at:
            self.created_at = datetime.now()
        if self.generated_sql and not self.sql_hash:
            self.sql_hash = hashlib.sha256(
                self.generated_sql.encode("utf-8")
            ).hexdigest()[:16]

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["execution_result"] = self.execution_result.value
        return d

# ── 告警模型 ────────────────────────────────────────────────────

@dataclass
class SecurityAlert:
    alert_id: str
    alert_type: str             # "abnormal_volume" / "sql_injection" / "mass_data_export" / ...
    severity: str               # "low" / "medium" / "high" / "critical"
    triggered_at: datetime
    summary: str
    detail: dict
    affected_users: list[str]
    related_log_ids: list[str]
    status: str = "new"         # new / acknowledged / resolved / false_positive

# ── 审计日志存储 ────────────────────────────────────────────────

class AuditLogStore:
    """
    审计日志存储层。
    使用 SQLite 作为高速存储，支持归档到 S3/OSS。
    """

    def __init__(
        self,
        db_path: str = "./.microgenbi/audit.db",
        archive_after_days: int = 30,
        archive_batch_size: int = 1000,
    ):
        self._db_path = db_path
        self._archive_after_days = archive_after_days
        self._archive_batch_size = archive_batch_size
        self._con = sqlite3.connect(db_path, check_same_thread=False)
        self._write_lock = threading.Lock()
        self._ensure_tables()

    def _ensure_tables(self):
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS audit_logs (
                log_id TEXT PRIMARY KEY,
                created_at TEXT NOT NULL,
                user_id TEXT NOT NULL,
                role TEXT NOT NULL,
                tenant_id TEXT NOT NULL,
                ip_address TEXT,
                session_id TEXT,
                user_agent TEXT,
                query TEXT NOT NULL,
                rewritten_query TEXT,
                intent TEXT,
                generated_sql TEXT,
                sql_hash TEXT,
                sql_dialect TEXT,
                execution_result TEXT NOT NULL,
                error_type TEXT,
                denied_reason TEXT,
                denied_at_layer INTEGER,
                denied_sql TEXT,
                latency_ms INTEGER,
                sql_planning_ms INTEGER,
                sql_execution_ms INTEGER,
                tokens_used INTEGER,
                model_used TEXT,
                row_count INTEGER,
                rows_scanned INTEGER,
                truncated INTEGER,
                danger_score REAL,
                is_write_operation INTEGER,
                required_approval INTEGER,
                parent_log_id TEXT,
                correction_count INTEGER DEFAULT 0,
                task_id TEXT,
                archived INTEGER DEFAULT 0
            )
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_user
            ON audit_logs(user_id, created_at)
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_created
            ON audit_logs(created_at, execution_result)
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS idx_audit_sql_hash
            ON audit_logs(sql_hash)
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS security_alerts (
                alert_id TEXT PRIMARY KEY,
                alert_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                triggered_at TEXT NOT NULL,
                summary TEXT,
                detail TEXT,
                affected_users TEXT,
                related_log_ids TEXT,
                status TEXT DEFAULT 'new'
            )
        """)
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS archived_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                log_data TEXT,
                archived_at TEXT
            )
        """)
        self._con.commit()

    def save(self, entry: AuditLogEntry):
        """保存单条日志（线程安全）"""
        with self._write_lock:
            self._con.execute(
                """
                INSERT OR REPLACE INTO audit_logs
                (log_id, created_at, user_id, role, tenant_id, ip_address,
                 session_id, user_agent, query, rewritten_query, intent,
                 generated_sql, sql_hash, sql_dialect, execution_result,
                 error_type, denied_reason, denied_at_layer, denied_sql,
                 latency_ms, sql_planning_ms, sql_execution_ms, tokens_used,
                 model_used, row_count, rows_scanned, truncated,
                 danger_score, is_write_operation, required_approval,
                 parent_log_id, correction_count, task_id)
                VALUES
                (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                 ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    entry.log_id, entry.created_at.isoformat(),
                    entry.user_id, entry.role, entry.tenant_id,
                    entry.ip_address, entry.session_id, entry.user_agent,
                    entry.query, entry.rewritten_query, entry.intent,
                    entry.generated_sql, entry.sql_hash, entry.sql_dialect,
                    entry.execution_result.value, entry.error_type,
                    entry.denied_reason, entry.denied_at_layer, entry.denied_sql,
                    entry.latency_ms, entry.sql_planning_ms, entry.sql_execution_ms,
                    entry.tokens_used, entry.model_used, entry.row_count,
                    entry.rows_scanned, int(entry.truncated),
                    entry.danger_score, int(entry.is_write_operation),
                    int(entry.required_approval), entry.parent_log_id,
                    entry.correction_count, entry.task_id,
                )
            )
            self._con.commit()

    def query(
        self,
        user_id: str = None,
        tenant_id: str = None,
        time_from: datetime = None,
        time_to: datetime = None,
        execution_result: str = None,
        sql_hash: str = None,
        intent: str = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AuditLogEntry]:
        """多条件查询审计日志"""
        conditions = ["archived = 0"]
        params = []

        if user_id:
            conditions.append("user_id = ?")
            params.append(user_id)
        if tenant_id:
            conditions.append("tenant_id = ?")
            params.append(tenant_id)
        if time_from:
            conditions.append("created_at >= ?")
            params.append(time_from.isoformat())
        if time_to:
            conditions.append("created_at <= ?")
            params.append(time_to.isoformat())
        if execution_result:
            conditions.append("execution_result = ?")
            params.append(execution_result)
        if sql_hash:
            conditions.append("sql_hash = ?")
            params.append(sql_hash)
        if intent:
            conditions.append("intent = ?")
            params.append(intent)

        where = " AND ".join(conditions)
        rows = self._con.execute(
            f"""
            SELECT * FROM audit_logs
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [limit, offset],
        ).fetchall()

        return [self._row_to_entry(r) for r in rows]

    def get_daily_stats(self, date: str) -> dict:
        """获取某日的统计摘要"""
        row = self._con.execute("""
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN execution_result = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                SUM(CASE WHEN execution_result = 'FAILED' THEN 1 ELSE 0 END) as failed,
                SUM(CASE WHEN execution_result = 'DENIED' THEN 1 ELSE 0 END) as denied,
                SUM(tokens_used) as total_tokens,
                AVG(latency_ms) as avg_latency,
                SUM(row_count) as total_rows,
                COUNT(DISTINCT user_id) as unique_users
            FROM audit_logs
            WHERE date(created_at) = ?
              AND archived = 0
        """, (date,)).fetchone()

        return {
            "date": date,
            "total": row[0] or 0,
            "success": row[1] or 0,
            "failed": row[2] or 0,
            "denied": row[3] or 0,
            "total_tokens": row[4] or 0,
            "avg_latency_ms": round(row[5] or 0, 1),
            "total_rows": row[6] or 0,
            "unique_users": row[7] or 0,
            "success_rate": round((row[1] or 0) / max(row[0] or 1, 1) * 100, 1),
        }

    def _row_to_entry(self, row: sqlite3.Row) -> AuditLogEntry:
        cols = [d[0] for d in self._con.execute(
            "PRAGMA table_info(audit_logs)"
        ).fetchall()]
        data = dict(zip(cols, row))
        return AuditLogEntry(
            log_id=data["log_id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            user_id=data["user_id"],
            role=data["role"],
            tenant_id=data["tenant_id"],
            ip_address=data.get("ip_address") or "",
            session_id=data.get("session_id") or "",
            user_agent=data.get("user_agent") or "",
            query=data["query"],
            rewritten_query=data.get("rewritten_query") or "",
            intent=data.get("intent") or "",
            generated_sql=data.get("generated_sql") or "",
            sql_hash=data.get("sql_hash") or "",
            sql_dialect=data.get("sql_dialect") or "",
            execution_result=ExecutionResult(data.get("execution_result", "PENDING")),
            error_type=data.get("error_type") or "",
            denied_reason=data.get("denied_reason") or "",
            denied_at_layer=data.get("denied_at_layer") or 0,
            denied_sql=data.get("denied_sql") or "",
            latency_ms=data.get("latency_ms") or 0,
            sql_planning_ms=data.get("sql_planning_ms") or 0,
            sql_execution_ms=data.get("sql_execution_ms") or 0,
            tokens_used=data.get("tokens_used") or 0,
            model_used=data.get("model_used") or "",
            row_count=data.get("row_count") or 0,
            rows_scanned=data.get("rows_scanned") or 0,
            truncated=bool(data.get("truncated")),
            danger_score=data.get("danger_score") or 0.0,
            is_write_operation=bool(data.get("is_write_operation")),
            required_approval=bool(data.get("required_approval")),
            parent_log_id=data.get("parent_log_id") or "",
            correction_count=data.get("correction_count") or 0,
            task_id=data.get("task_id") or "",
        )

# ── 安全告警引擎 ─────────────────────────────────────────────

class SecurityAlertEngine:
    """
    安全告警引擎。
    定期扫描审计日志，检测异常模式，生成告警。
    """

    # 告警规则定义
    RULES = [
        {
            "id": "abnormal_volume",
            "name": "异常查询量",
            "description": "单个用户在 1 小时内查询量超过阈值",
            "severity": "medium",
            "check": lambda stats: stats["queries_per_hour"] > 500,
            "threshold": 500,
            "window_hours": 1,
        },
        {
            "id": "mass_export",
            "name": "大量数据导出",
            "description": "单次查询返回行数超过阈值",
            "severity": "high",
            "check": lambda stats: stats["max_row_count"] > 5000,
            "threshold": 5000,
        },
        {
            "id": "high_failure_rate",
            "name": "高失败率",
            "description": "用户在 1 小时内的查询失败率超过 50%",
            "severity": "high",
            "check": lambda stats: (
                stats["failure_rate"] > 0.5 and stats["total"] > 10
            ),
        },
        {
            "id": "after_hours_access",
            "name": "非工作时间访问",
            "description": "在非工作时间（22:00-07:00）有查询活动",
            "severity": "low",
            "check": lambda stats: stats["after_hours_count"] > 0,
        },
        {
            "id": "repeated_sql",
            "name": "重复 SQL 执行",
            "description": "同一 SQL 被 5 个以上不同用户执行",
            "severity": "medium",
            "check": lambda stats: stats["sql_unique_users"] > 5,
            "threshold": 5,
        },
        {
            "id": "write_attempt",
            "name": "写操作尝试",
            "description": "有写操作被拒绝",
            "severity": "high",
            "check": lambda stats: stats["denied_writes"] > 0,
        },
        {
            "id": "select_star_frequent",
            "name": "频繁使用 SELECT *",
            "description": "SELECT * 使用率超过 20%",
            "severity": "low",
            "check": lambda stats: stats["select_star_rate"] > 0.2,
            "threshold": 0.2,
        },
    ]

    def __init__(self, audit_store: AuditLogStore):
        self._store = audit_store

    async def run_check(self) -> list[SecurityAlert]:
        """执行所有安全检查，返回触发的告警"""
        import uuid
        alerts = []
        now = datetime.now()
        today = now.strftime("%Y-%m-%d")
        yesterday = (now - timedelta(days=1)).strftime("%Y-%m-%d")

        # 统计今日 + 昨日
        for date in [today, yesterday]:
            stats = await self._compute_stats(date)

            for rule in self.RULES:
                try:
                    if rule["check"](stats):
                        alert = SecurityAlert(
                            alert_id=f"alrt_{uuid.uuid4().hex[:12]}",
                            alert_type=rule["id"],
                            severity=rule["severity"],
                            triggered_at=now,
                            summary=rule["description"],
                            detail={"date": date, "stats": stats, "rule": rule["id"]},
                            affected_users=stats.get("top_users", [])[:5],
                            related_log_ids=[],
                        )
                        alerts.append(alert)

                        # 保存告警到数据库
                        self._save_alert(alert)

                except Exception as e:
                    logger.warning(f"Alert rule {rule['id']} failed: {e}")

        return alerts

    async def _compute_stats(self, date: str) -> dict:
        """计算指定日期的安全统计"""
        rows = self._store.query(
            time_from=datetime.fromisoformat(f"{date} 00:00:00"),
            time_to=datetime.fromisoformat(f"{date} 23:59:59"),
            limit=100000,
        )

        if not rows:
            return {}

        # 按用户聚合
        user_stats = defaultdict(lambda: {
            "total": 0, "failed": 0, "denied": 0,
            "tokens": 0, "max_row_count": 0, "after_hours": 0,
        })

        sql_users = defaultdict(set)
        denied_writes = 0

        for log in rows:
            uid = log.user_id
            user_stats[uid]["total"] += 1
            if log.execution_result == ExecutionResult.FAILED:
                user_stats[uid]["failed"] += 1
            if log.execution_result == ExecutionResult.DENIED:
                user_stats[uid]["denied"] += 1
            user_stats[uid]["tokens"] += log.tokens_used
            user_stats[uid]["max_row_count"] = max(
                user_stats[uid]["max_row_count"], log.row_count
            )
            # 非工作时间检测（22:00-07:00）
            hour = log.created_at.hour
            if hour >= 22 or hour < 7:
                user_stats[uid]["after_hours"] += 1
            if log.generated_sql:
                sql_users[log.generated_sql].add(uid)
            if log.is_write_operation and log.execution_result == ExecutionResult.DENIED:
                denied_writes += 1

        # SELECT * 统计
        select_star_count = sum(
            1 for log in rows
            if log.generated_sql and "SELECT *" in log.generated_sql.upper()
        )

        # 最大查询量（单用户小时）
        hourly_volumes = defaultdict(int)
        for log in rows:
            hour_key = log.created_at.strftime("%Y-%m-%d %H")
            hourly_volumes[(log.user_id, hour_key)] += 1

        top_users = sorted(
            user_stats.keys(),
            key=lambda u: user_stats[u]["total"],
            reverse=True
        )[:10]

        return {
            "total": len(rows),
            "success": sum(1 for r in rows if r.execution_result == ExecutionResult.SUCCESS),
            "failed": sum(1 for r in rows if r.execution_result == ExecutionResult.FAILED),
            "denied": sum(1 for r in rows if r.execution_result == ExecutionResult.DENIED),
            "queries_per_hour": max(hourly_volumes.values()) if hourly_volumes else 0,
            "max_row_count": max(log.row_count for log in rows),
            "failure_rate": sum(1 for r in rows if r.execution_result == ExecutionResult.FAILED) / max(len(rows), 1),
            "after_hours_count": sum(s["after_hours"] for s in user_stats.values()),
            "sql_unique_users": max(len(users) for users in sql_users.values()) if sql_users else 0,
            "denied_writes": denied_writes,
            "select_star_rate": select_star_count / max(len(rows), 1),
            "top_users": top_users,
        }

    def _save_alert(self, alert: SecurityAlert):
        self._store._con.execute("""
            INSERT OR REPLACE INTO security_alerts
            (alert_id, alert_type, severity, triggered_at, summary,
             detail, affected_users, related_log_ids, status)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            alert.alert_id, alert.alert_type, alert.severity,
            alert.triggered_at.isoformat(), alert.summary,
            json.dumps(alert.detail, ensure_ascii=False),
            json.dumps(alert.affected_users),
            json.dumps(alert.related_log_ids),
            alert.status,
        ))
        self._store._con.commit()

# ── REST API 接口 ─────────────────────────────────────────────

"""
GET  /api/v1/admin/audit/logs
     ?user_id=&tenant_id=&from=&to=&result=&intent=&limit=&offset=
     → 返回审计日志列表（分页）

GET  /api/v1/admin/audit/logs/{log_id}
     → 返回单条日志详情

GET  /api/v1/admin/audit/stats
     ?date=2026-05-22
     → 返回每日统计摘要

GET  /api/v1/admin/audit/alerts
     ?severity=high&status=new
     → 返回安全告警列表

POST /api/v1/admin/audit/alerts/{alert_id}/acknowledge
     → 确认告警

POST /api/v1/admin/audit/alerts/{alert_id}/resolve
     → 标记告警为已解决
"""
```

#### 9.4.2 Prompt 版本管理与灰度回滚

**设计目标**：Prompt 模板版本化管理 + 灰度流量控制 + 一键回滚。避免 Prompt 改动影响线上质量。

```python
# micro_genbi/llm/prompt_manager.py

import sqlite3
import json
import hashlib
import uuid
import difflib
import random
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── 数据模型 ───────────────────────────────────────────────────

@dataclass
class PromptVersion:
    version_id: str
    version_number: int         # 自动递增版本号（v1, v2, v3...）
    created_at: datetime
    created_by: str            # 创建人
    changelog: str             # 变更说明
    is_active: bool = False    # 是否当前生效
    traffic_split: float = 0.0  # 灰度流量比例（0.0~1.0）

    # 各角色 Prompt 模板
    system_prompt: str = ""
    sql_generation_template: str = ""
    correction_template: str = ""
    chart_template: str = ""
    intent_template: str = ""
    answer_template: str = ""

    # 质量指标（激活后自动统计）
    accuracy_rate: float = 0.0    # 一次成功率
    correction_rate: float = 0.0  # 修正率
    avg_latency_ms: float = 0.0

    # 元数据
    parent_version_id: str = ""   # 基于哪个版本创建
    tags: list[str] = field(default_factory=list)  # 标签：stable, testing, rollback

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        return d

# ── 版本存储 ────────────────────────────────────────────────

class PromptVersionStore:
    """
    Prompt 版本持久化存储。
    使用 SQLite 存储版本历史，JSON 存储模板内容。
    """

    def __init__(self, db_path: str = "./.microgenbi/prompt_versions.db"):
        self._db_path = db_path
        self._con = sqlite3.connect(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        self._con.execute("""
            CREATE TABLE IF NOT EXISTS prompt_versions (
                version_id TEXT PRIMARY KEY,
                version_number INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                created_by TEXT NOT NULL,
                changelog TEXT,
                is_active INTEGER DEFAULT 0,
                traffic_split REAL DEFAULT 0.0,
                accuracy_rate REAL DEFAULT 0.0,
                correction_rate REAL DEFAULT 0.0,
                avg_latency_ms REAL DEFAULT 0.0,
                parent_version_id TEXT,
                tags TEXT DEFAULT '[]',
                templates_json TEXT NOT NULL,
                FOREIGN KEY (parent_version_id)
                    REFERENCES prompt_versions(version_id)
            )
        """)
        self._con.execute("""
            CREATE INDEX IF NOT EXISTS idx_active
            ON prompt_versions(is_active)
        """)
        self._con.commit()

    def save(self, version: PromptVersion):
        templates = json.dumps({
            "system_prompt": version.system_prompt,
            "sql_generation_template": version.sql_generation_template,
            "correction_template": version.correction_template,
            "chart_template": version.chart_template,
            "intent_template": version.intent_template,
            "answer_template": version.answer_template,
        }, ensure_ascii=False)

        self._con.execute("""
            INSERT OR REPLACE INTO prompt_versions
            (version_id, version_number, created_at, created_by, changelog,
             is_active, traffic_split, accuracy_rate, correction_rate,
             avg_latency_ms, parent_version_id, tags, templates_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            version.version_id, version.version_number,
            version.created_at.isoformat(), version.created_by,
            version.changelog, int(version.is_active),
            version.traffic_split, version.accuracy_rate,
            version.correction_rate, version.avg_latency_ms,
            version.parent_version_id, json.dumps(version.tags),
            templates,
        ))
        self._con.commit()

    def get(self, version_id: str) -> Optional[PromptVersion]:
        row = self._con.execute(
            "SELECT * FROM prompt_versions WHERE version_id = ?",
            (version_id,)
        ).fetchone()
        return self._row_to_version(row) if row else None

    def get_active(self) -> Optional[PromptVersion]:
        row = self._con.execute(
            "SELECT * FROM prompt_versions WHERE is_active = 1 LIMIT 1"
        ).fetchone()
        return self._row_to_version(row) if row else None

    def list_all(self, limit: int = 50) -> list[PromptVersion]:
        rows = self._con.execute(
            "SELECT * FROM prompt_versions ORDER BY version_number DESC LIMIT ?",
            (limit,)
        ).fetchall()
        return [self._row_to_version(r) for r in rows]

    def get_by_number(self, number: int) -> Optional[PromptVersion]:
        row = self._con.execute(
            "SELECT * FROM prompt_versions WHERE version_number = ?",
            (number,)
        ).fetchone()
        return self._row_to_version(row) if row else None

    def get_next_version_number(self) -> int:
        row = self._con.execute(
            "SELECT MAX(version_number) FROM prompt_versions"
        ).fetchone()
        return (row[0] or 0) + 1

    def deactivate_all(self):
        self._con.execute(
            "UPDATE prompt_versions SET is_active = 0, traffic_split = 0"
        )
        self._con.commit()

    def _row_to_version(self, row: sqlite3.Row) -> PromptVersion:
        cols = [d[0] for d in self._con.execute(
            "PRAGMA table_info(prompt_versions)").fetchall()]
        data = dict(zip(cols, row))
        templates = json.loads(data["templates_json"])
        return PromptVersion(
            version_id=data["version_id"],
            version_number=data["version_number"],
            created_at=datetime.fromisoformat(data["created_at"]),
            created_by=data["created_by"],
            changelog=data.get("changelog") or "",
            is_active=bool(data["is_active"]),
            traffic_split=data.get("traffic_split") or 0.0,
            accuracy_rate=data.get("accuracy_rate") or 0.0,
            correction_rate=data.get("correction_rate") or 0.0,
            avg_latency_ms=data.get("avg_latency_ms") or 0.0,
            parent_version_id=data.get("parent_version_id") or "",
            tags=json.loads(data.get("tags") or "[]"),
            system_prompt=templates.get("system_prompt", ""),
            sql_generation_template=templates.get("sql_generation_template", ""),
            correction_template=templates.get("correction_template", ""),
            chart_template=templates.get("chart_template", ""),
            intent_template=templates.get("intent_template", ""),
            answer_template=templates.get("answer_template", ""),
        )

# ── Prompt 管理器 ────────────────────────────────────────────

class PromptManager:
    """
    Prompt 版本管理器。

    工作流：
    1. create_version() → 基于当前版本创建新版本（草稿）
    2. activate_version() → 小流量灰度（可指定 0%~100%）
    3. 观察质量指标（accuracy_rate / correction_rate）
    4. 全量上线（traffic_split=1.0）或回滚（rollback）
    """

    # 默认模板（系统初始版本）
    DEFAULT_TEMPLATES = {
        "system_prompt": """你是一个专业的 SQL 数据分析助手。...""",
        "sql_generation_template": "生成 SQL 的模板...",
        "correction_template": "修正 SQL 的模板...",
        "chart_template": "生成图表配置的模板...",
        "intent_template": "意图分类的模板...",
        "answer_template": "生成自然语言答复的模板...",
    }

    def __init__(self, store: PromptVersionStore = None):
        self._store = store or PromptVersionStore()
        # 确保存在 v1 默认版本
        if not self._store.list_all(limit=1):
            self._init_default_version()

    def _init_default_version(self):
        v = PromptVersion(
            version_id=f"pv_{uuid.uuid4().hex[:12]}",
            version_number=1,
            created_at=datetime.now(),
            created_by="system",
            changelog="初始版本",
            is_active=True,
            traffic_split=1.0,
            tags=["stable", "default"],
            **self.DEFAULT_TEMPLATES,
        )
        self._store.save(v)

    async def create_version(
        self,
        created_by: str,
        changelog: str,
        templates: dict,
        parent_version_id: str = None,
    ) -> PromptVersion:
        """
        从当前激活版本创建新版本。
        新版本默认不激活，需要显式调用 activate_version()。
        """
        active = self._store.get_active()
        parent_id = parent_version_id or (active.version_id if active else "")

        version = PromptVersion(
            version_id=f"pv_{uuid.uuid4().hex[:12]}",
            version_number=self._store.get_next_version_number(),
            created_at=datetime.now(),
            created_by=created_by,
            changelog=changelog,
            parent_version_id=parent_id,
            **templates,
        )
        self._store.save(version)
        logger.info(f"Created prompt version {version.version_id} (v{version.version_number})")
        return version

    async def activate_version(
        self,
        version_id: str,
        traffic_split: float = 1.0,
    ) -> PromptVersion:
        """
        激活指定版本。
        - traffic_split = 0.1 → 10% 流量使用新版本（灰度）
        - traffic_split = 1.0 → 100% 流量使用新版本（全量）
        """
        # 如果当前有激活版本，先取消激活
        active = self._store.get_active()
        if active:
            active.is_active = False
            active.traffic_split = 0.0
            self._store.save(active)

        new_active = self._store.get(version_id)
        if not new_active:
            raise ValueError(f"Version {version_id} not found")

        new_active.is_active = True
        new_active.traffic_split = traffic_split
        self._store.save(new_active)

        logger.info(
            f"Activated version {version_id} (v{new_active.version_number})"
            f" with {traffic_split * 100:.0f}% traffic"
        )
        return new_active

    async def rollback(self, target_version_id: str = None) -> PromptVersion:
        """
        回滚到指定版本（或上一个版本）。
        """
        if target_version_id:
            target = self._store.get(target_version_id)
        else:
            # 回滚到上一个版本（version_number - 1）
            active = self._store.get_active()
            if not active:
                raise ValueError("No active version to rollback from")
            target = self._store.get_by_number(active.version_number - 1)
            if not target:
                raise ValueError("No previous version to rollback to")

        return await self.activate_version(target.version_id, traffic_split=1.0)

    def compare_versions(self, v1_id: str, v2_id: str) -> dict:
        """
        对比两个版本的 Prompt 差异（diff）。
        """
        v1 = self._store.get(v1_id)
        v2 = self._store.get(v2_id)
        if not v1 or not v2:
            raise ValueError("Version not found")

        diff = {}
        template_fields = [
            "system_prompt", "sql_generation_template",
            "correction_template", "chart_template",
            "intent_template", "answer_template",
        ]

        for field in template_fields:
            old_text = getattr(v1, field) or ""
            new_text = getattr(v2, field) or ""

            if old_text != new_text:
                differ = difflib.unified_diff(
                    old_text.splitlines(keepends=True),
                    new_text.splitlines(keepends=True),
                    fromfile=f"v{v1.version_number}",
                    tofile=f"v{v2.version_number}",
                    lineterm="",
                )
                diff[field] = {
                    "changed": True,
                    "lines_added": new_text.count("\n") - old_text.count("\n"),
                    "unified_diff": "".join(differ),
                }
            else:
                diff[field] = {"changed": False}

        return {
            "v1": {"id": v1.version_id, "number": v1.version_number},
            "v2": {"id": v2.version_id, "number": v2.version_number},
            "diff": diff,
            "v1_metrics": {
                "accuracy_rate": v1.accuracy_rate,
                "correction_rate": v1.correction_rate,
                "avg_latency_ms": v1.avg_latency_ms,
            },
            "v2_metrics": {
                "accuracy_rate": v2.accuracy_rate,
                "correction_rate": v2.correction_rate,
                "avg_latency_ms": v2.avg_latency_ms,
            },
        }

    def should_use_version(self, version: PromptVersion) -> bool:
        """
        根据灰度流量比例，决定是否使用指定版本。
        用于 AskService 中的流量路由。
        """
        if not version.is_active or version.traffic_split >= 1.0:
            return True
        if version.traffic_split <= 0.0:
            return False
        return random.random() < version.traffic_split

    async def update_metrics(
        self,
        version_id: str,
        accuracy_rate: float = None,
        correction_rate: float = None,
        avg_latency_ms: float = None,
    ):
        """从审计日志统计中更新版本质量指标"""
        version = self._store.get(version_id)
        if not version:
            return
        if accuracy_rate is not None:
            version.accuracy_rate = accuracy_rate
        if correction_rate is not None:
            version.correction_rate = correction_rate
        if avg_latency_ms is not None:
            version.avg_latency_ms = avg_latency_ms
        self._store.save(version)

# ── Prompt 服务（运行时使用）─────────────────────────────────────

class PromptService:
    """
    运行时 Prompt 服务。
    封装 PromptManager，提供渲染模板变量的能力。
    """

    def __init__(self, manager: PromptManager = None):
        self._manager = manager or PromptManager()

    async def get_active_version(self) -> PromptVersion:
        return self._manager._store.get_active()

    async def render_sql_prompt(
        self,
        question: str,
        schema_context: str,
        history_context: str = "",
        dialect: str = "mysql",
    ) -> dict[str, str]:
        """渲染 SQL 生成 Prompt"""
        version = await self.get_active_version()
        if not version:
            raise RuntimeError("No active prompt version")

        system = version.system_prompt.format(dialect=dialect) + "\n\n" + schema_context

        user = f"""## 用户问题
{question}

## 多轮对话历史（参考）
{history_context or '(无历史记录)'}

请生成 SQL。"""

        return {"system": system, "user": user}

    async def render_correction_prompt(
        self,
        question: str,
        failed_sql: str,
        error: str,
        schema_context: str,
        attempt: int,
    ) -> dict[str, str]:
        """渲染 SQL 修正 Prompt"""
        version = await self.get_active_version()
        template = version.correction_template

        return {
            "system": template.format(schema=schema_context),
            "user": f"问题: {question}\n失败的SQL: {failed_sql}\n错误: {error}\n第 {attempt} 次修正。",
        }
```

**REST API 接口**：
```yaml
GET  /api/v1/admin/prompts/versions          # 列出所有版本
POST /api/v1/admin/prompts/versions         # 创建新版本
GET  /api/v1/admin/prompts/versions/{id}   # 查看单版本
POST /api/v1/admin/prompts/versions/{id}/activate
     # body: { "traffic_split": 0.1 }      # 灰度激活
POST /api/v1/admin/prompts/versions/{id}/rollback  # 回滚
GET  /api/v1/admin/prompts/versions/{id}/compare/{other_id}  # 对比
```


#### 9.4.3 查询结果缓存（Query Cache）

**设计目标**：相同语义的问题复用查询结果，减少 LLM 调用次数和数据库压力。

```python
# micro_genbi/service/query_cache.py

import redis
import json
import hashlib
import re
import logging
import asyncio
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── 缓存条目模型 ──────────────────────────────────────────

@dataclass
class CacheEntry:
    """缓存条目"""
    question_hash: str          # 问题的语义哈希
    normalized_question: str      # 归一化后的问题文本
    result_json: str            # 查询结果的 JSON 序列化
    generated_sql: str           # 生成时用的 SQL
    row_count: int             # 结果行数
    chart_options: str = ""     # ECharts Options JSON
    summary: str = ""          # 自然语言摘要
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0       # 访问次数（用于热度排序）
    ttl_seconds: int = 3600     # 过期时间（秒）
    is_stale: bool = False      # 是否已过期

    @property
    def is_expired(self) -> bool:
        return datetime.now() > (self.created_at + timedelta(seconds=self.ttl_seconds))

    def to_dict(self) -> dict:
        return {
            "question_hash": self.question_hash,
            "normalized_question": self.normalized_question,
            "result_json": self.result_json,
            "generated_sql": self.generated_sql,
            "row_count": self.row_count,
            "chart_options": self.chart_options,
            "summary": self.summary,
            "created_at": self.created_at.isoformat(),
            "last_accessed": self.last_accessed.isoformat(),
            "access_count": self.access_count,
            "ttl_seconds": self.ttl_seconds,
        }

# ── 缓存后端 ────────────────────────────────────────────────

class CacheBackend(ABC):
    """缓存后端抽象"""

    @abstractmethod
    async def get(self, key: str) -> Optional[CacheEntry]: ...

    @abstractmethod
    async def set(self, key: str, entry: CacheEntry) -> None: ...

    @abstractmethod
    async def delete(self, key: str) -> None: ...

    @abstractmethod
    async def clear(self) -> None: ...

    @abstractmethod
    async def keys(self) -> list[str]: ...

class MemoryCacheBackend(CacheBackend):
    """纯内存缓存（Redis 不可用时降级）"""

    def __init__(self, max_size: int = 1000):
        self._cache: dict[str, CacheEntry] = {}
        self._max_size = max_size
        self._access_order: list[str] = []  # LRU 顺序

    async def get(self, key: str) -> Optional[CacheEntry]:
        entry = self._cache.get(key)
        if entry is None:
            return None
        if entry.is_expired:
            await self.delete(key)
            return None
        # 更新访问信息
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        return entry

    async def set(self, key: str, entry: CacheEntry) -> None:
        # LRU 淘汰
        if len(self._cache) >= self._max_size and key not in self._cache:
            oldest_key = self._access_order.pop(0)
            del self._cache[oldest_key]
        self._cache[key] = entry
        if key not in self._access_order:
            self._access_order.append(key)

    async def delete(self, key: str) -> None:
        self._cache.pop(key, None)
        if key in self._access_order:
            self._access_order.remove(key)

    async def clear(self) -> None:
        self._cache.clear()
        self._access_order.clear()

    async def keys(self) -> list[str]:
        return list(self._cache.keys())


class RedisCacheBackend(CacheBackend):
    """Redis 缓存后端（生产环境推荐）"""

    def __init__(self, url: str, key_prefix: str = "mgb:cache:"):
        self._redis = redis.from_url(url, decode_responses=True)
        self._prefix = key_prefix

    def _make_key(self, hash_key: str) -> str:
        return f"{self._prefix}{hash_key}"

    async def get(self, key: str) -> Optional[CacheEntry]:
        raw = self._redis.get(self._make_key(key))
        if not raw:
            return None
        data = json.loads(raw)
        entry = CacheEntry(
            question_hash=data["question_hash"],
            normalized_question=data["normalized_question"],
            result_json=data["result_json"],
            generated_sql=data.get("generated_sql", ""),
            row_count=data.get("row_count", 0),
            chart_options=data.get("chart_options", ""),
            summary=data.get("summary", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            ttl_seconds=data.get("ttl_seconds", 3600),
        )
        if entry.is_expired:
            await self.delete(key)
            return None
        # 更新访问
        entry.access_count += 1
        entry.last_accessed = datetime.now()
        self._redis.setex(
            self._make_key(key), entry.ttl_seconds,
            json.dumps(entry.to_dict(), ensure_ascii=False)
        )
        return entry

    async def set(self, key: str, entry: CacheEntry) -> None:
        self._redis.setex(
            self._make_key(key), entry.ttl_seconds,
            json.dumps(entry.to_dict(), ensure_ascii=False)
        )

    async def delete(self, key: str) -> None:
        self._redis.delete(self._make_key(key))

    async def clear(self) -> None:
        keys = self._redis.keys(f"{self._prefix}*")
        if keys:
            self._redis.delete(*keys)

    async def keys(self) -> list[str]:
        return [k.replace(self._prefix, "")
                for k in self._redis.keys(f"{self._prefix}*")]

# ── 语义哈希 ────────────────────────────────────────────────

class QuestionNormalizer:
    """
    问题归一化：将不同表述的相同问题归一为同一哈希。
    
    归一化策略：
    1. 去除标点符号
    2. 转小写
    3. 去除多余空格
    4. 归一化时间表达（"今天"="2026-05-22"）
    5. 去除无关修饰词
    """

    # 归一化时间词
    TIME_PATTERNS = [
        (r"今天", datetime.now().strftime("%Y-%m-%d")),
        (r"昨天", (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")),
        (r"本周", (datetime.now() - timedelta(days=datetime.now().weekday())).strftime("%Y-%m-%d")),
        (r"本月", datetime.now().strftime("%Y-%m-01")),
        (r"上月", (datetime.now().replace(day=1) - timedelta(days=1)).strftime("%Y-%m-01")),
        (r"最近\s*(\d+)\s*天", lambda m: (
            (datetime.now() - timedelta(days=int(m.group(1)))).strftime("%Y-%m-%d")
        )),
    ]

    def normalize(self, question: str) -> str:
        q = question.strip()
        # 去除标点
        q = re.sub(r"[^\w\s\u4e00-\u9fff]", " ", q)
        # 转小写
        q = q.lower()
        # 归一化时间词
        for pattern, replacement in self.TIME_PATTERNS:
            if callable(replacement):
                q = re.sub(pattern, replacement, q)
            else:
                q = re.sub(pattern, replacement, q)
        # 去除多余空格
        q = re.sub(r"\s+", " ", q).strip()
        return q

    def make_key(self, question: str) -> str:
        normalized = self.normalize(question)
        return f"qcache:{hashlib.md5(normalized.encode('utf-8')).hexdigest()}"

# ── 查询缓存管理器 ────────────────────────────────────────

class QueryCache:
    """
    查询结果缓存管理器。
    
    缓存策略：
    - Key: 问题的语义哈希
    - TTL: 默认 1 小时（可配置）
    - 不缓存：含 NOW() / CURRENT_DATE 的实时查询
    - 命中率统计：按天统计每个问题的访问次数
    
    适用场景：
    - 管理看板：每天被看 N 次的核心指标
    - 固定报表：每周/月重复查询
    - FAQ 类问题：员工反复查询的政策规定
    """

    # 不缓存的问题模式（含实时函数）
    REALTIME_PATTERNS = [
        r"\bNOW\(\)",
        r"\bCURRENT_DATE\b",
        r"\bCURDATE\(\)",
        r"\bGETDATE\(\)",
        r"\bSYSDATE\b",
        r"\bSYSTIMESTAMP\b",
        r"\bTODAY\(\)",
    ]

    def __init__(
        self,
        redis_url: str = None,
        default_ttl: int = 3600,
        enable_cache: bool = True,
    ):
        if redis_url and enable_cache:
            self._backend = RedisCacheBackend(redis_url)
        else:
            self._backend = MemoryCacheBackend()
        self._normalizer = QuestionNormalizer()
        self._default_ttl = default_ttl
        self._enable = enable_cache

        # 命中率统计（内存，不进 Redis）
        self._hit_stats: dict[str, int] = defaultdict(int)
        self._miss_count = 0

    async def get(self, question: str) -> Optional[CacheEntry]:
        """根据问题获取缓存结果"""
        if not self._enable:
            return None

        # 跳过实时查询
        if self._is_realtime_query(question):
            return None

        key = self._normalizer.make_key(question)
        entry = await self._backend.get(key)

        if entry:
            self._hit_stats[key] += 1
            logger.debug(f"Cache HIT: {question[:30]}...")
            return entry
        else:
            self._miss_count += 1
            logger.debug(f"Cache MISS: {question[:30]}...")
            return None

    async def set(
        self,
        question: str,
        result_data: list[dict],
        generated_sql: str,
        row_count: int,
        chart_options: dict = None,
        summary: str = "",
        ttl_seconds: int = None,
    ):
        """缓存查询结果"""
        if not self._enable:
            return

        # 不缓存含实时函数的问题
        if self._is_realtime_query(question):
            return

        key = self._normalizer.make_key(question)
        entry = CacheEntry(
            question_hash=key,
            normalized_question=self._normalizer.normalize(question),
            result_json=json.dumps(result_data, ensure_ascii=False),
            generated_sql=generated_sql,
            row_count=row_count,
            chart_options=json.dumps(chart_options, ensure_ascii=False) if chart_options else "",
            summary=summary,
            created_at=datetime.now(),
            last_accessed=datetime.now(),
            access_count=1,
            ttl_seconds=ttl_seconds or self._default_ttl,
        )
        await self._backend.set(key, entry)

    async def invalidate(self, question: str = None, pattern: str = None):
        """
        主动失效缓存。
        - question: 失效特定问题
        - pattern: 失效匹配模式的所有缓存（如按表名失效）
        """
        if question:
            key = self._normalizer.make_key(question)
            await self._backend.delete(key)
        if pattern:
            # 按表名失效（如数据变更后）
            for key in await self._backend.keys():
                entry = await self._backend.get(key)
                if entry and pattern.upper() in entry.generated_sql.upper():
                    await self._backend.delete(key)

    async def get_stats(self) -> dict:
        """获取缓存统计"""
        total_requests = self._miss_count + sum(self._hit_stats.values())
        hit_count = sum(self._hit_stats.values())
        hit_rate = hit_count / total_requests if total_requests > 0 else 0.0

        # Redis 统计
        if isinstance(self._backend, RedisCacheBackend):
            info = self._backend._redis.info("stats")
            redis_keys = await self._backend.keys()
        else:
            info = {}
            redis_keys = await self._backend.keys()

        return {
            "enabled": self._enable,
            "total_requests": total_requests,
            "hit_count": hit_count,
            "miss_count": self._miss_count,
            "hit_rate": round(hit_rate * 100, 2),
            "cached_queries": len(redis_keys),
            "top_queries": sorted(
                self._hit_stats.items(),
                key=lambda x: x[1],
                reverse=True,
            )[:10],
            "backend": type(self._backend).__name__,
        }

    async def clear(self):
        """清空所有缓存"""
        await self._backend.clear()
        self._hit_stats.clear()
        self._miss_count = 0

    def _is_realtime_query(self, question: str) -> bool:
        """判断是否为实时查询（含时间函数，不应缓存）"""
        return any(
            re.search(p, question.upper())
            for p in self.REALTIME_PATTERNS
        )

# ── 与 AskService 集成 ────────────────────────────────────

class CachedAskService:
    """
    带缓存的 AskService 封装。
    在原 AskService 外层包一层缓存逻辑。
    """

    def __init__(self, ask_service, cache: QueryCache):
        self._ask = ask_service
        self._cache = cache

    async def ask(self, question: str, **kwargs) -> dict:
        # Step 1: 查缓存
        cached = await self._cache.get(question)
        if cached:
            return {
                "sql": cached.generated_sql,
                "data": json.loads(cached.result_json),
                "columns": list(json.loads(cached.result_json)[0].keys()) if json.loads(cached.result_json) else [],
                "row_count": cached.row_count,
                "chart": json.loads(cached.chart_options) if cached.chart_options else None,
                "summary": cached.summary,
                "cached": True,
            }

        # Step 2: 缓存未命中，执行真实查询
        result = await self._ask.ask(question, **kwargs)

        # Step 3: 写入缓存
        await self._cache.set(
            question=question,
            result_data=result.get("data", []),
            generated_sql=result.get("sql", ""),
            row_count=result.get("row_count", 0),
            chart_options=result.get("chart", {}),
            summary=result.get("summary", ""),
        )

        return {**result, "cached": False}
```


#### 9.4.4 SQL 执行计划解释（Query Plan Explanation）

**设计目标**：让用户理解查询为何慢、何时扫全表、是否缺索引。

```python
# micro_genbi/service/query_explainer.py

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

# ── 数据模型 ────────────────────────────────────────────────

class ScanType(str, Enum):
    INDEX_SCAN = "index_scan"         # 索引扫描（快）
    INDEX_RANGE_SCAN = "index_range_scan"  # 索引范围扫描
    SEQ_SCAN = "seq_scan"             # 全表扫描（慢）
    BITMAP_HEAP_SCAN = "bitmap_heap_scan"  # 位图扫描
    UNKNOWN = "unknown"

@dataclass
class PlanNode:
    """执行计划中的一个节点"""
    node_type: str          # "Seq Scan" / "Index Scan" / "Hash Join" ...
    relation: str          # 表名
    alias: str = ""
    estimated_rows: int = 0
    estimated_cost: float = 0.0
    actual_rows: int = 0
    actual_loops: int = 0
    filter: str = ""       # WHERE 过滤条件
    index_name: str = ""   # 使用的索引名
    scan_type: ScanType = ScanType.UNKNOWN
    warnings: list[str] = field(default_factory=list)
    children: list["PlanNode"] = field(default_factory=list)

@dataclass
class QueryPlanExplanation:
    """人类可读的执行计划解释"""
    plan_nodes: list[PlanNode]
    total_estimated_rows: int
    total_estimated_cost: float
    estimated_time_ms: float   # 估算耗时（毫秒）
    scan_types: dict[str, int] # 各扫描类型数量
    warnings: list[str]        # 全局警告
    human_readable: str        # 人类可读描述
    suggestions: list[str]     # 优化建议

# ── 执行计划解释器 ────────────────────────────────────────────

class QueryPlanExplainer:
    """
    SQL 执行计划解释器。
    
    支持的数据库：
    - PostgreSQL: 使用 EXPLAIN (FORMAT JSON)
    - MySQL: 使用 EXPLAIN FORMAT=JSON
    - SQLite: 使用 EXPLAIN QUERY PLAN
    """

    DIALECT_EXPLAIN = {
        "postgresql": "EXPLAIN (FORMAT JSON, ANALYZE) {sql}",
        "mysql": "EXPLAIN FORMAT=JSON {sql}",
        "sqlite": "EXPLAIN QUERY PLAN {sql}",
        "mssql": "SET SHOWPLAN_JSON ON; {sql}",
        "clickhouse": "EXPLAIN QUERY PLAN {sql}",
    }

    def __init__(self, db_connection):
        self._db = db_connection
        self._dialect = getattr(db_connection, "_dialect", "postgresql")

    async def explain(self, sql: str) -> QueryPlanExplanation:
        """
        执行 EXPLAIN 并返回人类可读的解释。
        """
        try:
            if self._dialect == "postgresql":
                return await self._explain_postgresql(sql)
            elif self._dialect == "mysql":
                return await self._explain_mysql(sql)
            elif self._dialect == "sqlite":
                return await self._explain_sqlite(sql)
            else:
                return await self._explain_generic(sql)
        except Exception as e:
            logger.warning(f"EXPLAIN failed for dialect {self._dialect}: {e}")
            return self._make_fallback_explanation(sql, str(e))

    async def _explain_postgresql(self, sql: str) -> QueryPlanExplanation:
        """PostgreSQL EXPLAIN (FORMAT JSON, ANALYZE)"""
        explain_sql = f"EXPLAIN (FORMAT JSON, ANALYZE, BUFFERS) {sql}"
        raw = await self._db.fetchone(explain_sql)

        # raw[0] is the JSON string
        data = json.loads(raw[0])[0]
        plan = data.get("Plan", {})

        nodes = self._parse_postgres_plan(plan)
        total_cost = plan.get("Total Cost", 0)
        est_rows = plan.get("Plan Rows", 0)

        return QueryPlanExplanation(
            plan_nodes=nodes,
            total_estimated_rows=est_rows,
            total_estimated_cost=total_cost,
            estimated_time_ms=self._cost_to_ms(total_cost),
            scan_types=self._count_scan_types(nodes),
            warnings=self._collect_warnings(nodes),
            human_readable=self._format_human(nodes, est_rows, total_cost),
            suggestions=self._generate_suggestions(nodes, total_cost, est_rows),
        )

    async def _explain_mysql(self, sql: str) -> QueryPlanExplanation:
        """MySQL EXPLAIN FORMAT=JSON"""
        explain_sql = f"EXPLAIN FORMAT=JSON {sql}"
        raw = await self._db.fetchone(explain_sql)
        data = json.loads(raw[0])

        return self._parse_mysql_explain(data)

    async def _explain_sqlite(self, sql: str) -> QueryPlanExplanation:
        """SQLite EXPLAIN QUERY PLAN"""
        explain_sql = f"EXPLAIN QUERY PLAN {sql}"
        rows = await self._db.fetchall(explain_sql)

        nodes = []
        total_rows = 0
        warnings = []

        for row in rows:
            detail = row[3] if len(row) > 3 else str(row)
            scan_type = self._detect_scan_type_from_detail(detail)
            if scan_type == ScanType.SEQ_SCAN:
                warnings.append(f"全表扫描: {detail}")

            nodes.append(PlanNode(
                node_type=detail.split(" ")[0] if detail else "UNKNOWN",
                relation=detail,
                estimated_rows=0,
                scan_type=scan_type,
                warnings=[],
            ))
            total_rows += 1

        return QueryPlanExplanation(
            plan_nodes=nodes,
            total_estimated_rows=total_rows,
            total_estimated_cost=0,
            estimated_time_ms=0,
            scan_types={"sqlite_scan": total_rows},
            warnings=warnings,
            human_readable=f"SQLite 将执行 {total_rows} 个步骤。详情：\n" +
                           "\n".join(r[3] for r in rows if len(r) > 3),
            suggestions=["使用索引加速查询" if "SCAN" in str(r) else "" for r in rows],
        )

    async def _explain_generic(self, sql: str) -> QueryPlanExplanation:
        """兜底的通用解释（基于 SQL 静态分析）"""
        warnings = []
        suggestions = []

        sql_upper = sql.upper()

        if "SELECT *" in sql_upper:
            warnings.append("使用了 SELECT *，建议指定字段以利用索引")
        if not re.search(r"\b(WHERE|JOIN)\b", sql_upper) and "SELECT" in sql_upper:
            warnings.append("无 WHERE 或 JOIN 条件，可能导致全表扫描")

        # 检测是否有合理的 LIMIT
        if not re.search(r"\bLIMIT\s+\d+", sql_upper, re.IGNORECASE):
            warnings.append("建议添加 LIMIT 限制返回行数")

        return QueryPlanExplanation(
            plan_nodes=[],
            total_estimated_rows=0,
            total_estimated_cost=0,
            estimated_time_ms=0,
            scan_types={},
            warnings=warnings,
            human_readable=(
                "当前数据库引擎不支持 EXPLAIN。以下为静态分析警告：\n" +
                "\n".join(f"  ⚠ {w}" for w in warnings)
            ),
            suggestions=suggestions,
        )

    def _parse_postgres_plan(self, plan: dict) -> list[PlanNode]:
        """解析 PostgreSQL JSON 计划"""
        nodes = []

        def walk(p: dict, parent_cost: float = 0):
            node_type = p.get("Node Type", "Unknown")
            rel_name = p.get("Relation Name", "")
            alias = p.get("Alias", "")
            est_rows = p.get("Plan Rows", 0)
            actual_rows = p.get("Actual Rows", 0)
            total_cost = p.get("Total Cost", 0)
            filter_cond = p.get("Filter", "")
            index_name = p.get("Index Name", "")

            # 判断扫描类型
            scan_type = ScanType.UNKNOWN
            warnings = []
            if "Seq Scan" in node_type:
                scan_type = ScanType.SEQ_SCAN
                warnings.append(f"全表扫描: {rel_name}（预计 {est_rows} 行）")
            elif "Index Scan" in node_type:
                scan_type = ScanType.INDEX_SCAN
            elif "Index Only Scan" in node_type:
                scan_type = ScanType.INDEX_RANGE_SCAN
            elif "Bitmap Heap Scan" in node_type:
                scan_type = ScanType.BITMAP_HEAP_SCAN
                warnings.append(f"位图扫描: {rel_name}（可能需优化）")

            # 警告：cost 为 0 或成本异常高
            if total_cost > 10000:
                warnings.append(f"高成本操作: {node_type} cost={total_cost}")

            node = PlanNode(
                node_type=node_type,
                relation=rel_name,
                alias=alias,
                estimated_rows=est_rows,
                estimated_cost=total_cost,
                actual_rows=actual_rows,
                actual_loops=p.get("Actual Loops", 0),
                filter=filter_cond,
                index_name=index_name,
                scan_type=scan_type,
                warnings=warnings,
                children=[],
            )

            # 递归处理子节点
            if "Plans" in p:
                for child in p["Plans"]:
                    child_node = walk(child, total_cost)
                    node.children.append(child_node)

            nodes.append(node)
            return node

        walk(plan)
        return nodes

    def _detect_scan_type_from_detail(self, detail: str) -> ScanType:
        detail_upper = detail.upper()
        if "INDEX" in detail_upper:
            return ScanType.INDEX_SCAN
        elif "SCAN TABLE" in detail_upper:
            return ScanType.SEQ_SCAN
        return ScanType.UNKNOWN

    def _count_scan_types(self, nodes: list[PlanNode]) -> dict[str, int]:
        counts = {}
        def count(n: PlanNode):
            st = n.scan_type.value
            counts[st] = counts.get(st, 0) + 1
            for child in n.children:
                count(child)
        for node in nodes:
            count(node)
        return counts

    def _collect_warnings(self, nodes: list[PlanNode]) -> list[str]:
        warnings = []
        def collect(n: PlanNode):
            warnings.extend(n.warnings)
            for child in n.children:
                collect(child)
        for node in nodes:
            collect(node)
        return warnings

    def _cost_to_ms(self, cost: float) -> float:
        """PostgreSQL cost 单位转换为毫秒估算"""
        # PostgreSQL cost_unit ≈ seq_page_cost (default 1.0)
        # 假设 seq_page_cost = 1ms（实际取决于硬件）
        return round(cost, 1)

    def _format_human(
        self,
        nodes: list[PlanNode],
        total_rows: int,
        total_cost: float,
    ) -> str:
        if not nodes:
            return "无法解析执行计划"

        lines = []
        scan_types = self._count_scan_types(nodes)

        # 概览
        lines.append(f"📊 执行计划概览")
        lines.append(f"   预计扫描行数：{total_rows:,}")
        lines.append(f"   估算成本：{total_cost:.1f}")
        lines.append(f"   估算耗时：约 {self._cost_to_ms(total_cost):.0f}ms")
        lines.append("")

        # 扫描类型统计
        if scan_types:
            lines.append("🔍 扫描方式分布：")
            type_names = {
                "seq_scan": "全表扫描",
                "index_scan": "索引扫描",
                "index_range_scan": "索引范围扫描",
                "bitmap_heap_scan": "位图扫描",
            }
            for stype, count in scan_types.items():
                name = type_names.get(stype, stype)
                icon = "🔴" if stype == "seq_scan" else "🟡" if stype == "bitmap_heap_scan" else "🟢"
                lines.append(f"   {icon} {name} × {count}")
            lines.append("")

        # 详细节点
        def format_node(n: PlanNode, depth: int = 0):
            indent = "   " * depth
            icon = "🔴" if n.scan_type == ScanType.SEQ_SCAN else \
                   "🟡" if n.scan_type == ScanType.BITMAP_HEAP_SCAN else "🟢"
            if n.relation:
                lines.append(
                    f"{indent}{icon} {n.node_type} [{n.relation}]"
                    f"  ~{n.estimated_rows:,}行"
                    f"  cost={n.estimated_cost:.1f}"
                )
            else:
                lines.append(f"{indent}{icon} {n.node_type}  cost={n.estimated_cost:.1f}")

            for child in n.children:
                format_node(child, depth + 1)

        lines.append("📋 详细计划：")
        for root in nodes:
            format_node(root)

        return "\n".join(lines)

    def _generate_suggestions(
        self,
        nodes: list[PlanNode],
        total_cost: float,
        total_rows: int,
    ) -> list[str]:
        suggestions = []
        scan_types = self._count_scan_types(nodes)

        # 全表扫描建议
        seq_scans = scan_types.get(ScanType.SEQ_SCAN.value, 0)
        if seq_scans > 0:
            suggestions.append(
                f"检测到 {seq_scans} 次全表扫描。"
                "建议：为 WHERE/JOIN/ORDER BY 涉及的列创建索引。"
            )

        # 大量行扫描建议
        if total_rows > 100000:
            suggestions.append(
                f"预计扫描 {total_rows:,} 行，查询可能较慢。"
                "建议：增加 WHERE 条件过滤，或使用分区表。"
            )

        # 高成本建议
        if total_cost > 10000:
            suggestions.append(
                f"查询成本较高（{total_cost:.0f}）。"
                "建议：检查是否有多表 JOIN 缺少连接条件。"
            )

        if not suggestions:
            suggestions.append("执行计划看起来合理，暂无需优化。")

        return suggestions

    def _make_fallback_explanation(self, sql: str, error: str) -> QueryPlanExplanation:
        return QueryPlanExplanation(
            plan_nodes=[],
            total_estimated_rows=0,
            total_estimated_cost=0,
            estimated_time_ms=0,
            scan_types={},
            warnings=[f"执行计划获取失败: {error}"],
            human_readable=f"无法获取执行计划（{error}）。请检查 SQL 语法。",
            suggestions=["检查 SQL 语法是否正确"],
        )

# ── REST API 接口 ─────────────────────────────────────────

"""
POST /api/v1/query/explain
     body: { "sql": "SELECT ...", "dialect": "postgresql" }
     → 返回人类可读的执行计划解释

GET  /api/v1/query/explain/{task_id}
     → 异步查询的执行计划（任务 ID 模式）
"""
```

#### 9.4.5 中文 Prompt 模板优化（针对国产模型）

DeepSeek、Qwen、通义等国产模型在中文语义理解上有优势，但需要针对性调优 Prompt：

```python
# micro_genbi/llm/prompts_zh.py

# ── 中文优化 System Prompt（通用）────────────────────────────

ZH_SQL_SYSTEM_PROMPT = """你是一个专业的 SQL 数据分析助手，擅长将自然语言问题转换为精确的 SQL 查询。

【数据库信息】
- 数据库类型：{dialect}
- 所有表名和列名使用双引号包裹，如 "table_name"
- 数字常量不使用引号，字符串常量使用单引号
- 日期格式：'YYYY-MM-DD'
- 时间戳格式：'YYYY-MM-DD HH:MI:SS'

【输出要求】
1. 只生成 SELECT 查询，禁止任何写操作（INSERT/UPDATE/DELETE/DROP/TRUNCATE）
2. 必须包含 LIMIT（默认 1000）
3. 禁止使用 SELECT *，必须列出需要的字段
4. 使用清晰的列别名（AS），推荐使用中文别名提高可读性
5. GROUP BY 后出现的字段必须在 SELECT 中出现，或使用聚合函数包裹
6. 所有字段名、表名使用双引号，避免关键字冲突

【分析问题技巧】
- "各部门" → 使用 GROUP BY "dept_name"
- "最近一个月" → WHERE "created_at" >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
- "同比上月" → 计算 (本期 - 上期) / 上期 * 100
- "Top 10" → ORDER BY ... DESC LIMIT 10
- "包含某词" → LIKE '%关键词%' 或 ILIKE（PostgreSQL）
- "去重计数" → COUNT(DISTINCT "column")
- "每月统计" → DATE_FORMAT("date_col", '%Y-%m') 或 TO_CHAR(date_col, 'YYYY-MM')
- "某列最大值对应行" → SELECT * ORDER BY "col" DESC LIMIT 1

【字段别名规范】
使用中文别名，让结果更易读：
SELECT
    "dept_name" AS "部门",
    SUM("amount") AS "报销总额",
    COUNT(DISTINCT "employee_id") AS "员工人数",
    AVG("amount") AS "平均金额"
...

请根据以下问题生成 SQL："""

# ── 中文 few-shot 示例 ──────────────────────────────────────

ZH_SQL_EXAMPLES = [
    {
        "intent": "count_aggregate",
        "input": "各部门上月的报销总额是多少？",
        "output": """```sql
SELECT
    "dept_name" AS "部门",
    SUM("amount") AS "报销总额",
    COUNT(*) AS "报销笔数",
    AVG("amount") AS "平均单笔金额"
FROM "dept_expense"
WHERE "submit_date" >= DATE_SUB(CURDATE(), INTERVAL 1 MONTH)
  AND "submit_date" < DATE_FORMAT(CURDATE(), '%Y-%m-01')
GROUP BY "dept_name"
ORDER BY SUM("amount") DESC
LIMIT 1000
```"""
    },
    {
        "intent": "count_aggregate",
        "input": "本月新增了多少客户？",
        "output": """```sql
SELECT
    COUNT(*) AS "新增客户数"
FROM "customers"
WHERE "created_at" >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
  AND "created_at" < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
```"""
    },
    {
        "intent": "time_trend",
        "input": "过去7天每天的订单量是多少？",
        "output": """```sql
SELECT
    DATE("order_date") AS "日期",
    COUNT(*) AS "订单数",
    SUM("total_amount") AS "订单总额"
FROM "orders"
WHERE "order_date" >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
  AND "order_date" < CURDATE() + INTERVAL 1 DAY
GROUP BY DATE("order_date")
ORDER BY DATE("order_date") ASC
LIMIT 1000
```"""
    },
    {
        "intent": "top_n",
        "input": "销售额最高的前10名商品是什么？",
        "output": """```sql
SELECT
    "product_name" AS "商品名称",
    "category" AS "类别",
    SUM("quantity") AS "销售数量",
    SUM("sales_amount") AS "销售额"
FROM "sales"
GROUP BY "product_name", "category"
ORDER BY SUM("sales_amount") DESC
LIMIT 10
```"""
    },
    {
        "intent": "comparison",
        "input": "各部门本月销售额相比上月增长了百分之多少？",
        "output": """```sql
SELECT
    "dept_name" AS "部门",
    SUM(CASE
        WHEN "sale_date" >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
         AND "sale_date" < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
        THEN "amount" ELSE 0 END
    ) AS "本月销售额",
    SUM(CASE
        WHEN "sale_date" >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
         AND "sale_date" < DATE_FORMAT(CURDATE(), '%Y-%m-01')
        THEN "amount" ELSE 0 END
    ) AS "上月销售额",
    ROUND(
        (SUM(CASE WHEN "sale_date" >= DATE_FORMAT(CURDATE(), '%Y-%m-01')
                   AND "sale_date" < DATE_ADD(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
              THEN "amount" ELSE 0 END)
        - SUM(CASE WHEN "sale_date" >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
                    AND "sale_date" < DATE_FORMAT(CURDATE(), '%Y-%m-01')
              THEN "amount" ELSE 0 END))
        / NULLIF(SUM(CASE WHEN "sale_date" >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
                           AND "sale_date" < DATE_FORMAT(CURDATE(), '%Y-%m-01')
                      THEN "amount" ELSE 0 END), 0) * 100,
        2
    ) AS "环比增长率"
FROM "sales"
WHERE "sale_date" >= DATE_SUB(DATE_FORMAT(CURDATE(), '%Y-%m-01'), INTERVAL 1 MONTH)
GROUP BY "dept_name"
ORDER BY "本月销售额" DESC
LIMIT 1000
```"""
    },
    {
        "intent": "rank",
        "input": "销售业绩排名第三的地区是哪个？",
        "output": """```sql
SELECT "region" AS "地区", SUM("sales") AS "销售额"
FROM "regional_sales"
GROUP BY "region"
ORDER BY SUM("sales") DESC
LIMIT 1 OFFSET 2
```"""
    },
]

# ── 修正 Prompt（中文）────────────────────────────────────────

ZH_CORRECTION_PROMPT = """你是一个 SQL 修正助手。以下 SQL 执行失败，请分析错误并修正。

【错误信息】
{error}

【失败的 SQL】
```sql
{failed_sql}
```

【数据库类型】
{dialect}

【Schema 信息】
{schema}

【要求】
1. 只修改有问题的部分，不要改变查询逻辑
2. 禁止将 SELECT 改为其他操作
3. 只输出修正后的 SQL（包含 ```sql ...```）
4. 如无法修正，说明原因

修正后的 SQL："""

# ── DeepSeek 特定优化 ───────────────────────────────────────

DEEPSEEK_SQL_SYSTEM_PROMPT = ZH_SQL_SYSTEM_PROMPT + """

【DeepSeek 特定优化】
- DeepSeek 对中文理解很好，可以更自然地表达需求
- 善用 DeepSeek 的数学推理能力处理"占比"、"增长率"等计算
- 示例："占比" → 某值 / 总值 * 100 AS "占比%"
- 生成的 SQL 风格偏简洁，不要过度嵌套子查询
"""

# ── 通义千问特定优化 ─────────────────────────────────────────

QIANWEN_SQL_SYSTEM_PROMPT = ZH_SQL_SYSTEM_PROMPT + """

【通义千问特定优化】
- 通义千问擅长中文语义理解，可使用更口语化的描述
- 生成的 SQL 推荐加上清晰的注释（-- 注释）
- 注意通义在处理复杂 JOIN 时可能生成多表笛卡尔积，需检查
"""

# ── Prompt 模板注册表 ────────────────────────────────────────

ZH_PROMPT_REGISTRY = {
    "default": ZH_SQL_SYSTEM_PROMPT,
    "deepseek": DEEPSEEK_SQL_SYSTEM_PROMPT,
    "qianwen": QIANWEN_SQL_SYSTEM_PROMPT,
    "qwen": QIANWEN_SQL_SYSTEM_PROMPT,  # 别名
    "kimi": ZH_SQL_SYSTEM_PROMPT,        # Kimi 默认用通用中文模板
    "doubao": ZH_SQL_SYSTEM_PROMPT,      # 豆包用通用中文模板
}

def get_zh_prompt_template(model_name: str) -> str:
    """根据模型名获取对应的中文 Prompt 模板"""
    name_lower = model_name.lower()
    for key, template in ZH_PROMPT_REGISTRY.items():
        if key in name_lower or name_lower in key:
            return template
    return ZH_PROMPT_REGISTRY["default"]
```


#### 9.4.6 可观测性：SQL 质量评分与监控面板

**设计目标**：全面监控 SQL 生成质量、延迟、Token 消耗，以数据驱动持续优化。

```
┌─────────────────────────────────────────────────────────────────┐
│  SQL 质量评分 = f(准确率, 修正率, 用户满意度, 执行时间)              │
│                                                                   │
│  维度 1: 准确率 = 一次生成就成功的 SQL 比例                        │
│  维度 2: 修正率 = 需要 Self-Correction 的比例                     │
│  维度 3: 用户满意度 = 用户是否追问（追问多 = 质量差）              │
│  维度 4: 执行效率 = P95 执行时间                                  │
│                                                                   │
│  告警规则：                                                      │
│  · 准确率 < 80% → 告警                                          │
│  · 某表查询失败率 > 20% → 告警（schema 可能过时）                  │
│  · P95 执行时间 > 5s → 告警（可能缺索引）                        │
│  · Token 消耗异常增长 → 告警（Prompt 可能进入死循环）             │
└─────────────────────────────────────────────────────────────────┘
```

```python
# micro_genbi/observability/dashboard.py

import sqlite3
import json
import asyncio
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date
from typing import Optional
from enum import Enum
from collections import defaultdict
import statistics

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────────────

@dataclass
class SQLQualityMetrics:
    """每日 SQL 质量指标"""
    date: str                    # 日期 YYYY-MM-DD
    total_queries: int          # 当日总查询数
    success_count: int          # 成功数
    failed_count: int           # 失败数
    denied_count: int           # 拒绝数
    success_rate: float         # 准确率（一次成功率）
    correction_rate: float      # 修正率（需要修正的比例）
    avg_latency_ms: float       # 平均延迟
    p50_latency_ms: float
    p95_latency_ms: float
    p99_latency_ms: float
    max_latency_ms: int         # 最大延迟
    token_cost: float           # 当日 Token 消耗（估算费用，$）
    token_count: int            # 当日 Token 总数
    avg_rows_returned: float    # 平均返回行数
    total_rows_returned: int    # 总返回行数
    cache_hit_rate: float       # 缓存命中率
    unique_users: int           # 当日活跃用户数
    unique_tenants: int         # 当日活跃租户数
    top_failed_tables: list     # 失败率最高的表
    top_slow_queries: list      # 最慢的 10 条查询摘要
    top_tokens_queries: list    # Token 消耗最高的查询
    user_satisfaction_score: float  # 用户满意度评分（1-5）

    # 质量细分
    by_intent: dict = field(default_factory=dict)   # 按意图分类准确率
    by_dialect: dict = field(default_factory=dict)  # 按数据库方言准确率
    by_model: dict = field(default_factory=dict)     # 按 LLM 模型准确率

    def to_dict(self) -> dict:
        d = asdict(self)
        return d


@dataclass
class RealtimeStats:
    """实时统计（过去 5 分钟窗口）"""
    window_start: datetime
    window_end: datetime
    query_count: int
    success_rate: float
    avg_latency_ms: float
    error_count: int
    pending_tasks: int


@dataclass
class AlertRule:
    """告警规则"""
    rule_id: str
    name: str
    condition: str           # 条件表达式
    threshold: float
    severity: str            # low / medium / high / critical
    enabled: bool = True
    cooldown_minutes: int = 30  # 告警冷却时间（避免重复告警）


@dataclass
class Alert:
    """告警实例"""
    alert_id: str
    rule_id: str
    rule_name: str
    severity: str
    triggered_at: datetime
    message: str
    metric_value: float
    threshold: float
    status: str = "firing"   # firing / acknowledged / resolved
    resolved_at: datetime = None
    acknowledged_by: str = ""

# ── 指标存储 ────────────────────────────────────────────────

class MetricsStore:
    """
    指标存储层。
    从审计日志聚合计算各项质量指标。
    """

    def __init__(self, db_path: str = "./.microgenbi/audit.db"):
        self._db_path = db_path

    def _get_con(self):
        return sqlite3.connect(self._db_path)

    async def compute_daily_metrics(self, date_str: str) -> SQLQualityMetrics:
        """计算指定日期的质量指标（从审计日志聚合）"""
        con = self._get_con()
        try:
            # 主统计
            row = con.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN execution_result = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN execution_result = 'FAILED' THEN 1 ELSE 0 END) as failed,
                    SUM(CASE WHEN execution_result = 'DENIED' THEN 1 ELSE 0 END) as denied,
                    SUM(tokens_used) as total_tokens,
                    AVG(latency_ms) as avg_latency,
                    SUM(row_count) as total_rows,
                    AVG(row_count) as avg_rows,
                    COUNT(DISTINCT user_id) as unique_users,
                    COUNT(DISTINCT tenant_id) as unique_tenants
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
            """, (date_str,)).fetchone()

            total = row[0] or 0
            success = row[1] or 0
            failed = row[2] or 0
            denied = row[3] or 0
            total_tokens = row[4] or 0

            # 延迟分位数
            latencies = con.execute("""
                SELECT latency_ms FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND latency_ms > 0
                ORDER BY latency_ms
            """, (date_str,)).fetchall()
            latencies = [r[0] for r in latencies]

            if latencies:
                p50 = statistics.median(latencies)
                p95 = latencies[int(len(latencies) * 0.95)]
                p99 = latencies[int(len(latencies) * 0.99)] if len(latencies) > 20 else latencies[-1]
                max_lat = max(latencies)
            else:
                p50 = p95 = p99 = max_lat = 0.0

            # 修正率（correction_count > 0 的比例）
            correction_row = con.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN correction_count > 0 THEN 1 ELSE 0 END) as corrected
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
            """, (date_str,)).fetchone()
            correction_rate = (
                correction_row[1] / correction_row[0]
                if correction_row[0] and correction_row[0] > 0 else 0.0
            )

            # Token 费用（假设 $0.01 / 1K token）
            token_cost = total_tokens * 0.01 / 1000

            # 失败率最高的表
            top_failed = con.execute("""
                SELECT generated_sql, COUNT(*) as cnt,
                       SUM(CASE WHEN execution_result = 'FAILED' THEN 1 ELSE 0 END) as fail_cnt
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND generated_sql != ''
                GROUP BY generated_sql
                ORDER BY fail_cnt DESC
                LIMIT 5
            """, (date_str,)).fetchall()

            top_failed_tables = [
                {
                    "sql_hash": r[0][:50] + "...",
                    "failure_count": r[2],
                    "total": r[1],
                }
                for r in top_failed
            ]

            # 最慢的查询
            top_slow = con.execute("""
                SELECT query, latency_ms, generated_sql
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND latency_ms > 0
                ORDER BY latency_ms DESC
                LIMIT 10
            """, (date_str,)).fetchall()

            top_slow_queries = [
                {
                    "query": r[0][:60],
                    "latency_ms": r[1],
                    "sql_hash": hash(str(r[2])[:30]),
                }
                for r in top_slow
            ]

            # Token 消耗最高的查询
            top_tokens = con.execute("""
                SELECT query, tokens_used
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND tokens_used > 0
                ORDER BY tokens_used DESC
                LIMIT 10
            """, (date_str,)).fetchall()

            top_tokens_queries = [
                {"query": r[0][:60], "tokens": r[1]}
                for r in top_tokens
            ]

            # 按意图准确率
            by_intent = {}
            intent_rows = con.execute("""
                SELECT intent,
                       COUNT(*) as total,
                       SUM(CASE WHEN execution_result = 'SUCCESS' THEN 1 ELSE 0 END) as success
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND intent != ''
                GROUP BY intent
            """, (date_str,)).fetchall()

            for r in intent_rows:
                by_intent[r[0]] = {
                    "total": r[1],
                    "success": r[2],
                    "rate": round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0.0,
                }

            # 按模型准确率
            by_model = {}
            model_rows = con.execute("""
                SELECT model_used,
                       COUNT(*) as total,
                       SUM(CASE WHEN execution_result = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                       AVG(latency_ms) as avg_lat
                FROM audit_logs
                WHERE date(created_at) = ?
                  AND archived = 0
                  AND model_used != ''
                GROUP BY model_used
            """, (date_str,)).fetchall()

            for r in model_rows:
                by_model[r[0]] = {
                    "total": r[1],
                    "success": r[2],
                    "rate": round(r[2] / r[1] * 100, 1) if r[1] > 0 else 0.0,
                    "avg_latency_ms": round(r[3] or 0, 1),
                }

            return SQLQualityMetrics(
                date=date_str,
                total_queries=total,
                success_count=success,
                failed_count=failed,
                denied_count=denied,
                success_rate=round(success / total * 100, 2) if total > 0 else 0.0,
                correction_rate=round(correction_rate * 100, 2),
                avg_latency_ms=round(row[5] or 0, 1),
                p50_latency_ms=round(p50, 1),
                p95_latency_ms=round(p95, 1),
                p99_latency_ms=round(p99, 1),
                max_latency_ms=max_lat,
                token_cost=round(token_cost, 4),
                token_count=total_tokens,
                avg_rows_returned=round(row[7] or 0, 1),
                total_rows_returned=row[6] or 0,
                cache_hit_rate=0.0,  # 从 QueryCache 获取
                unique_users=row[8] or 0,
                unique_tenants=row[9] or 0,
                top_failed_tables=top_failed_tables,
                top_slow_queries=top_slow_queries,
                top_tokens_queries=top_tokens_queries,
                user_satisfaction_score=4.2,  # TODO: 从用户反馈获取
                by_intent=by_intent,
                by_model=by_model,
            )
        finally:
            con.close()

    async def get_realtime_stats(self, window_minutes: int = 5) -> RealtimeStats:
        """获取实时统计（过去 N 分钟窗口）"""
        con = self._get_con()
        now = datetime.now()
        window_start = now - timedelta(minutes=window_minutes)

        try:
            row = con.execute("""
                SELECT
                    COUNT(*) as total,
                    SUM(CASE WHEN execution_result = 'SUCCESS' THEN 1 ELSE 0 END) as success,
                    SUM(CASE WHEN execution_result IN ('FAILED', 'DENIED') THEN 1 ELSE 0 END) as errors,
                    AVG(latency_ms) as avg_lat
                FROM audit_logs
                WHERE created_at >= ?
                  AND archived = 0
            """, (window_start.isoformat(),)).fetchone()

            pending = 0  # TODO: 从任务队列获取

            return RealtimeStats(
                window_start=window_start,
                window_end=now,
                query_count=row[0] or 0,
                success_rate=round((row[1] or 0) / max(row[0] or 1, 1) * 100, 1),
                avg_latency_ms=round(row[3] or 0, 1),
                error_count=row[2] or 0,
                pending_tasks=pending,
            )
        finally:
            con.close()

# ── 告警引擎 ────────────────────────────────────────────────

class AlertEngine:
    """
    告警引擎。
    基于指标规则触发告警，支持 Webhook / 钉钉 / 飞书 / 邮件。
    """

    DEFAULT_RULES = [
        AlertRule("low_accuracy", "准确率过低", "success_rate < 80", 80, "high"),
        AlertRule("high_failure_table", "某表失败率高", "table_failure_rate > 20", 20, "medium"),
        AlertRule("slow_p95", "P95 延迟过高", "p95_latency_ms > 5000", 5000, "medium"),
        AlertRule("token_spike", "Token 消耗异常", "token_growth_rate > 200", 200, "high"),
        AlertRule("no_queries", "无查询活动", "query_count == 0", 0, "low"),
        AlertRule("high_denial", "拒绝率过高", "denial_rate > 10", 10, "high"),
    ]

    def __init__(
        self,
        metrics_store: MetricsStore,
        webhook_url: str = None,
    ):
        self._metrics = metrics_store
        self._webhook_url = webhook_url
        self._rules: dict[str, AlertRule] = {r.rule_id: r for r in self.DEFAULT_RULES}
        self._active_alerts: dict[str, Alert] = {}
        self._last_triggered: dict[str, datetime] = {}

    def add_rule(self, rule: AlertRule):
        self._rules[rule.rule_id] = rule

    async def evaluate(self, date_str: str) -> list[Alert]:
        """评估告警规则，返回触发的告警"""
        metrics = await self._metrics.compute_daily_metrics(date_str)
        alerts = []

        for rule in self._rules.values():
            if not rule.enabled:
                continue

            # 检查冷却时间
            last = self._last_triggered.get(rule.rule_id)
            if last and (datetime.now() - last).total_seconds() < rule.cooldown_minutes * 60:
                continue

            triggered = await self._check_rule(rule, metrics)
            if triggered:
                alert = Alert(
                    alert_id=f"alrt_{rule.rule_id}_{date_str}",
                    rule_id=rule.rule_id,
                    rule_name=rule.name,
                    severity=rule.severity,
                    triggered_at=datetime.now(),
                    message=self._format_message(rule, metrics),
                    metric_value=triggered,
                    threshold=rule.threshold,
                )
                alerts.append(alert)
                self._active_alerts[alert.alert_id] = alert
                self._last_triggered[rule.rule_id] = datetime.now()

                # 发送通知
                await self._send_notification(alert)

        return alerts

    async def _check_rule(self, rule: AlertRule, metrics: SQLQualityMetrics) -> Optional[float]:
        """检查规则是否触发，返回触发时的值"""
        condition = rule.condition
        ctx = {
            "success_rate": metrics.success_rate,
            "p95_latency_ms": metrics.p95_latency_ms,
            "token_growth_rate": 0.0,  # TODO: 计算增长率
            "query_count": metrics.total_queries,
            "denial_rate": metrics.denial_count / max(metrics.total_queries, 1) * 100,
            "table_failure_rate": (
                metrics.top_failed_tables[0]["failure_count"] / max(metrics.total_queries, 1) * 100
                if metrics.top_failed_tables else 0.0
            ),
        }
        try:
            if eval(condition, {"__builtins__": {}}, ctx):
                return ctx.get(rule.condition.split()[0])
        except Exception:
            pass
        return None

    def _format_message(self, rule: AlertRule, metrics: SQLQualityMetrics) -> str:
        msgs = {
            "low_accuracy": f"准确率 {metrics.success_rate}% < {rule.threshold}%",
            "slow_p95": f"P95 延迟 {metrics.p95_latency_ms}ms > {rule.threshold}ms",
            "no_queries": f"今日查询量为 0",
            "high_denial": f"拒绝率 {metrics.denial_count/max(metrics.total_queries,1)*100:.1f}% > {rule.threshold}%",
        }
        return msgs.get(rule.rule_id, rule.name)

    async def _send_notification(self, alert: Alert):
        """发送告警通知"""
        if not self._webhook_url:
            logger.info(f"Alert: [{alert.severity}] {alert.message}")
            return

        try:
            import aiohttp
            async with aiohttp.ClientSession() as session:
                payload = {
                    "alert_id": alert.alert_id,
                    "severity": alert.severity,
                    "rule_name": alert.rule_name,
                    "message": alert.message,
                    "triggered_at": alert.triggered_at.isoformat(),
                }
                await session.post(self._webhook_url, json=payload, timeout=5)
        except Exception as e:
            logger.warning(f"Failed to send alert notification: {e}")

    async def acknowledge(self, alert_id: str, user: str):
        alert = self._active_alerts.get(alert_id)
        if alert:
            alert.status = "acknowledged"
            alert.acknowledged_by = user

    async def resolve(self, alert_id: str):
        alert = self._active_alerts.get(alert_id)
        if alert:
            alert.status = "resolved"
            alert.resolved_at = datetime.now()

# ── Prometheus 指标暴露 ────────────────────────────────────────

class PrometheusExporter:
    """
    Prometheus 指标暴露器。
    将系统指标以 Prometheus 格式暴露给 /metrics 端点。
    """

    METRICS = [
        ("microgenbi_queries_total", "Counter",
         'Queries total, labeled by status',
         ["status"]),
        ("microgenbi_sql_accuracy_ratio", "Gauge",
         'SQL generation accuracy ratio (0-1)',
         []),
        ("microgenbi_query_latency_seconds", "Histogram",
         'Query latency in seconds',
         ["p95"]),
        ("microgenbi_token_usage_total", "Counter",
         'Total tokens used',
         ["model"]),
        ("microgenbi_cache_hit_ratio", "Gauge",
         'Cache hit ratio (0-1)',
         []),
        ("microgenbi_active_alerts", "Gauge",
         'Number of active alerts',
         ["severity"]),
    ]

    def __init__(self, metrics_store: MetricsStore):
        self._metrics = metrics_store
        self._values: dict[str, float] = {}

    async def collect(self, date_str: str = None) -> str:
        """收集所有指标，以 Prometheus 格式返回"""
        date_str = date_str or datetime.now().strftime("%Y-%m-%d")
        metrics = await self._metrics.compute_daily_metrics(date_str)
        realtime = await self._metrics.get_realtime_stats()

        lines = [
            "# HELP microgenbi_info Micro-GenBI system info",
            "# TYPE microgenbi_info gauge",
            "microgenbi_info version=\"1.0.0\"",
            "",
        ]

        # 计数器
        lines.append(f"# HELP microgenbi_queries_total Total queries")
        lines.append("# TYPE microgenbi_queries_total counter")
        lines.append(f'microgenbi_queries_total{{status="success"}} {metrics.success_count}')
        lines.append(f'microgenbi_queries_total{{status="failed"}} {metrics.failed_count}')
        lines.append(f'microgenbi_queries_total{{status="denied"}} {metrics.denial_count}')
        lines.append("")

        # 质量指标
        lines.append("# HELP microgenbi_sql_accuracy_ratio SQL accuracy ratio")
        lines.append("# TYPE microgenbi_sql_accuracy_ratio gauge")
        lines.append(f"microgenbi_sql_accuracy_ratio {metrics.success_rate / 100:.4f}")
        lines.append("")

        # 延迟直方图（简化版，用 GAUGE 暴露 P95）
        lines.append("# HELP microgenbi_query_latency_p95_seconds P95 latency")
        lines.append("# TYPE microgenbi_query_latency_p95_seconds gauge")
        lines.append(f"microgenbi_query_latency_p95_seconds {metrics.p95_latency_ms / 1000:.3f}")
        lines.append("")

        # Token 消耗
        lines.append("# HELP microgenbi_token_usage_total Total tokens used")
        lines.append("# TYPE microgenbi_token_usage_total counter")
        lines.append(f"microgenbi_token_usage_total {{model=\"all\"}} {metrics.token_count}")
        lines.append("")

        # 活跃告警
        lines.append("# HELP microgenbi_active_alerts Active alert count")
        lines.append("# TYPE microgenbi_active_alerts gauge")

        return "\n".join(lines)

# ── 仪表板 API ───────────────────────────────────────────────

"""
GET  /api/v1/dashboard/metrics
     ?date=2026-05-22
     → 返回每日质量指标（JSON）

GET  /api/v1/dashboard/realtime
     ?window=5
     → 返回实时统计（过去 N 分钟）

GET  /api/v1/dashboard/quality-trend
     ?days=30
     → 返回近 N 天的质量趋势（准确率、延迟、Token 消耗曲线）

GET  /api/v1/dashboard/alerts
     ?severity=high&status=firing
     → 返回告警列表

POST /api/v1/dashboard/alerts/{alert_id}/acknowledge
     → 确认告警

POST /api/v1/dashboard/alerts/{alert_id}/resolve
     → 解决告警

GET  /metrics
     → Prometheus 抓取格式
"""
```

**前端可观测性面板设计（Tesla 风格）**：

```html
<!-- observability-panel.html -->
<style>
  .metrics-grid {
    display: grid;
    grid-template-columns: repeat(4, 1fr);
    gap: 1px;
    background: #1a1a1a;
  }
  .metric-card {
    background: #111;
    padding: 24px;
    text-align: center;
  }
  .metric-value {
    font-family: 'Universal Sans', sans-serif;
    font-size: 48px;
    font-weight: 600;
    color: #fff;
  }
  .metric-label {
    font-size: 12px;
    color: #666;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-top: 8px;
  }
  .metric-delta {
    font-size: 14px;
    margin-top: 4px;
  }
  .delta-up { color: #ef4444; }
  .delta-down { color: #22c55e; }
</style>
<div class="metrics-grid">
  <div class="metric-card">
    <div class="metric-value">94.2%</div>
    <div class="metric-label">SQL 准确率</div>
    <div class="metric-delta delta-down">-1.3% vs 昨日</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">847ms</div>
    <div class="metric-label">P95 延迟</div>
    <div class="metric-delta delta-down">-12ms</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">12.4K</div>
    <div class="metric-label">Token 消耗</div>
    <div class="metric-delta delta-up">+8.2%</div>
  </div>
  <div class="metric-card">
    <div class="metric-value">68.3%</div>
    <div class="metric-label">缓存命中率</div>
    <div class="metric-delta delta-up">+3.1%</div>
  </div>
</div>
```


---

## 十、用户体系、分组管理与缓存架构重构

### 10.1 需求分析与设计决策

```
┌──────────────────────────────────────────────────────────────────────┐
│  用户 + 分组 带来三个新问题：                                           │
│                                                                      │
│  1️⃣ 认证与授权：谁可以登录？谁可以查？谁可以写？                        │
│  2️⃣ 缓存隔离：不同分组的数据是否隔离？跨组能否共享缓存？                 │
│  3️⃣ 并发安全：同组多人同时写同一条记录，如何防止数据覆盖？               │
│                                                                      │
│  核心设计原则：                                                        │
│  · 用户 → 属于一个或多个 Group（组）                                   │
│  · Group = 最小数据隔离单元 + 最小缓存隔离单元                          │
│  · 缓存 Key = SHA256(SQL + dialect + group_id)                       │
│  · 写操作并发控制 = 乐观锁（version 字段）+ Redis 分布式锁             │
└──────────────────────────────────────────────────────────────────────┘
```

### 10.2 缓存 Key 设计决策

**三种候选方案对比**：

| 方案 | Key 来源 | 优点 | 缺点 |
|------|---------|------|------|
| A：汉字原文 | 用户输入文本 | 实现最简单 | 不同措辞表达相同语义 → 命中率极低；占用 LLM 生成环境 |
| B：查询结果数据 | SQL 执行后的数据哈希 | 精准反映数据内容 | 数据随时变化，同一 SQL 不同时间结果不同 → 缓存几乎失效 |
| **C：SQL 语句（推荐）** | 生成的标准化 SQL | 相同查询意图 → 相同 SQL → 命中率高；实现稳定 | 用户措辞变化但 SQL 不变时无法合并统计 |

**结论**：以 **SQL 语句**为缓存 Key 的核心，配合以下策略：

- **语义聚合**（可选）：用 LanceDB 将 SQL 文本向量化，用于"相似查询推荐"（不作为缓存命中依据，仅推荐）
- **TTL 可配置**：同组用户感知数据新鲜度，管理员在 Group 级别设置缓存过期时间
- **数据变更失效**：当底层数据库发生写操作时，同组相关表的所有缓存条目按正则匹配失效

### 10.3 用户认证与会话管理

```python
# micro_genbi/auth/user_manager.py

import hashlib
import secrets
import uuid
import sqlite3
import json
import re
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum
import jwt

logger = logging.getLogger(__name__)

# ── 数据模型 ──────────────────────────────────────────────────────

class UserStatus(str, Enum):
    ACTIVE = "active"
    SUSPENDED = "suspended"
    PENDING = "pending"

@dataclass
class User:
    user_id: str
    username: str
    email: str
    password_hash: str
    salt: str
    status: UserStatus = UserStatus.ACTIVE
    created_at: datetime = field(default_factory=datetime.now)
    last_login: datetime = None
    profile: dict = field(default_factory=dict)        # 姓名、部门等
    settings: dict = field(default_factory=dict)      # 用户个人偏好

    def verify_password(self, password: str) -> bool:
        return self.password_hash == self._hash_password(password, self.salt)

    @staticmethod
    def _hash_password(password: str, salt: str) -> str:
        return hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"),
            salt.encode("utf-8"), 100000,
        ).hex()

    @staticmethod
    def generate_salt() -> str:
        return secrets.token_hex(32)


@dataclass
class Group:
    group_id: str
    name: str                          # 组名，如"华东销售数据组"
    description: str = ""
    owner_user_id: str                 # 组长

    # 连接配置
    db_connections: dict = field(default_factory=dict)  # dialect → 连接配置
    default_dialect: str = "mysql"

    # 权限预设（可被用户级别覆盖）
    default_role: str = "viewer"       # viewer / editor / admin

    # 缓存配置（组级别 TTL）
    cache_ttl_seconds: int = 3600       # 默认缓存 TTL（秒）
    cache_enabled: bool = True
    realtime_table_patterns: list[str] = field(
        default_factory=lambda: ["^realtime_.*", "^stock_.*"]
    )  # 实时表名模式（不缓存）

    # 写操作配置
    write_concurrency_mode: str = "optimistic"   # optimistic / pessimistic
    max_write_lock_seconds: int = 30
    enable_write_audit: bool = True

    created_at: datetime = field(default_factory=datetime.now)
    settings: dict = field(default_factory=dict)


@dataclass
class UserGroupMembership:
    user_id: str
    group_id: str
    role: str = "member"              # member / editor / admin
    joined_at: datetime = field(default_factory=datetime.now)
    cache_ttl_override: int = None    # 用户个人 TTL 覆盖（优先于组级别）
    is_active: bool = True


@dataclass
class AuthToken:
    access_token: str
    refresh_token: str
    expires_in: int        # 秒
    token_type: str = "Bearer"
    user_id: str = ""
    group_ids: list[str] = field(default_factory=list)
    role: str = ""


# ── 存储层 ────────────────────────────────────────────────────────

class UserStore:
    """用户和分组数据持久化（SQLite，生产环境可替换为 PostgreSQL）"""

    def __init__(self, db_path: str = "./.microgenbi/auth.db"):
        self._db_path = db_path
        self._con = sqlite3.connect(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        self._con.executescript("""
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                email TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                created_at TEXT NOT NULL,
                last_login TEXT,
                profile_json TEXT DEFAULT '{}',
                settings_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS `groups` (
                group_id TEXT PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT '',
                owner_user_id TEXT NOT NULL,
                db_connections_json TEXT DEFAULT '{}',
                default_dialect TEXT DEFAULT 'mysql',
                default_role TEXT DEFAULT 'viewer',
                cache_ttl_seconds INTEGER DEFAULT 3600,
                cache_enabled INTEGER DEFAULT 1,
                realtime_table_patterns_json TEXT DEFAULT '[]',
                write_concurrency_mode TEXT DEFAULT 'optimistic',
                max_write_lock_seconds INTEGER DEFAULT 30,
                enable_write_audit INTEGER DEFAULT 1,
                created_at TEXT NOT NULL,
                settings_json TEXT DEFAULT '{}'
            );
            CREATE TABLE IF NOT EXISTS user_group_memberships (
                user_id TEXT NOT NULL,
                group_id TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'member',
                joined_at TEXT NOT NULL,
                cache_ttl_override INTEGER,
                is_active INTEGER DEFAULT 1,
                PRIMARY KEY (user_id, group_id)
            );
            CREATE TABLE IF NOT EXISTS refresh_tokens (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                revoked INTEGER DEFAULT 0
            );
        """)
        self._con.commit()

    def create_user(
        self, username: str, email: str, password: str, profile: dict = None
    ) -> User:
        salt = User.generate_salt()
        user = User(
            user_id=f"usr_{uuid.uuid4().hex[:16]}",
            username=username, email=email,
            password_hash=User._hash_password(password, salt),
            salt=salt, profile=profile or {},
        )
        self._con.execute("""
            INSERT INTO users
            (user_id, username, email, password_hash, salt, status,
             created_at, profile_json, settings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            user.user_id, user.username, user.email,
            user.password_hash, user.salt, user.status.value,
            user.created_at.isoformat(),
            json.dumps(user.profile), json.dumps(user.settings),
        ))
        self._con.commit()
        return user

    def get_user_by_email(self, email: str) -> Optional[User]:
        row = self._con.execute(
            "SELECT * FROM users WHERE email = ?", (email,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_by_id(self, user_id: str) -> Optional[User]:
        row = self._con.execute(
            "SELECT * FROM users WHERE user_id = ?", (user_id,)
        ).fetchone()
        return self._row_to_user(row) if row else None

    def get_user_groups(self, user_id: str) -> list[Group]:
        rows = self._con.execute("""
            SELECT g.* FROM `groups` g
            JOIN user_group_memberships m ON g.group_id = m.group_id
            WHERE m.user_id = ? AND m.is_active = 1
        """, (user_id,)).fetchall()
        return [self._row_to_group(r) for r in rows]

    def update_last_login(self, user_id: str):
        self._con.execute(
            "UPDATE users SET last_login = ? WHERE user_id = ?",
            (datetime.now().isoformat(), user_id)
        )
        self._con.commit()

    def create_group(
        self, name: str, owner_user_id: str,
        description: str = "", db_connections: dict = None,
    ) -> Group:
        group = Group(
            group_id=f"grp_{uuid.uuid4().hex[:16]}",
            name=name, owner_user_id=owner_user_id,
            description=description, db_connections=db_connections or {},
        )
        self._con.execute("""
            INSERT INTO `groups`
            (group_id, name, description, owner_user_id,
             db_connections_json, default_dialect, cache_ttl_seconds,
             cache_enabled, realtime_table_patterns_json,
             write_concurrency_mode, max_write_lock_seconds,
             enable_write_audit, created_at, settings_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group.group_id, group.name, group.description,
            group.owner_user_id, json.dumps(group.db_connections),
            group.default_dialect, group.cache_ttl_seconds,
            int(group.cache_enabled),
            json.dumps(group.realtime_table_patterns),
            group.write_concurrency_mode, group.max_write_lock_seconds,
            int(group.enable_write_audit),
            group.created_at.isoformat(), json.dumps(group.settings),
        ))
        self._con.commit()
        return group

    def get_group(self, group_id: str) -> Optional[Group]:
        row = self._con.execute(
            "SELECT * FROM `groups` WHERE group_id = ?", (group_id,)
        ).fetchone()
        return self._row_to_group(row) if row else None

    def add_user_to_group(
        self, user_id: str, group_id: str, role: str = "member"
    ) -> UserGroupMembership:
        m = UserGroupMembership(user_id=user_id, group_id=group_id, role=role)
        self._con.execute("""
            INSERT OR REPLACE INTO user_group_memberships
            (user_id, group_id, role, joined_at, cache_ttl_override, is_active)
            VALUES (?, ?, ?, ?, ?, 1)
        """, (m.user_id, m.group_id, m.role,
              m.joined_at.isoformat(), m.cache_ttl_override))
        self._con.commit()
        return m

    def save_refresh_token(
        self, token_hash: str, user_id: str, expires_hours: int = 720
    ):
        expires_at = datetime.now() + timedelta(hours=expires_hours)
        self._con.execute("""
            INSERT INTO refresh_tokens (token_hash, user_id, created_at, expires_at)
            VALUES (?, ?, ?, ?)
        """, (token_hash, user_id, datetime.now().isoformat(), expires_at.isoformat()))
        self._con.commit()

    def revoke_refresh_token(self, token_hash: str):
        self._con.execute(
            "UPDATE refresh_tokens SET revoked = 1 WHERE token_hash = ?",
            (token_hash,)
        )
        self._con.commit()

    def validate_refresh_token(self, token_hash: str) -> Optional[str]:
        row = self._con.execute("""
            SELECT user_id FROM refresh_tokens
            WHERE token_hash = ? AND revoked = 0 AND expires_at > ?
        """, (token_hash, datetime.now().isoformat())).fetchone()
        return row[0] if row else None

    def _row_to_user(self, row: sqlite3.Row) -> User:
        return User(
            user_id=row[0], username=row[1], email=row[2],
            password_hash=row[3], salt=row[4],
            status=UserStatus(row[5]),
            created_at=datetime.fromisoformat(row[6]),
            last_login=datetime.fromisoformat(row[7]) if row[7] else None,
            profile=json.loads(row[8] or "{}"),
            settings=json.loads(row[9] or "{}"),
        )

    def _row_to_group(self, row: sqlite3.Row) -> Group:
        return Group(
            group_id=row[0], name=row[1], description=row[2] or "",
            owner_user_id=row[3],
            db_connections=json.loads(row[4] or "{}"),
            default_dialect=row[5] or "mysql",
            default_role=row[6] or "viewer",
            cache_ttl_seconds=row[7] or 3600,
            cache_enabled=bool(row[8]),
            realtime_table_patterns=json.loads(row[9] or "[]"),
            write_concurrency_mode=row[10] or "optimistic",
            max_write_lock_seconds=row[11] or 30,
            enable_write_audit=bool(row[12]),
            created_at=datetime.fromisoformat(row[13]),
            settings=json.loads(row[14] or "{}"),
        )


class AuthService:
    """
    认证服务。
    
    支持：
    - 用户注册 / 登录（密码校验）
    - JWT Access Token（15 分钟）+ Refresh Token（30 天，单次使用）
    - 分组感知：Token 中包含用户所属的 group_ids
    - 密码强度校验
    """

    def __init__(self, store: UserStore, jwt_secret: str,
                 jwt_algorithm: str = "HS256"):
        self._store = store
        self._jwt_secret = jwt_secret
        self._jwt_alg = jwt_algorithm

    def register(
        self, username: str, email: str, password: str
    ) -> tuple[User, AuthToken]:
        self._validate_password(password)
        user = self._store.create_user(
            username=username, email=email, password=password
        )
        token = self._issue_token(user)
        return user, token

    def login(self, email: str, password: str) -> AuthToken:
        user = self._store.get_user_by_email(email)
        if not user:
            raise AuthError("Invalid email or password", code="INVALID_CREDENTIALS")
        if user.status != UserStatus.ACTIVE:
            raise AuthError(f"Account is {user.status.value}", code="ACCOUNT_INACTIVE")
        if not user.verify_password(password):
            raise AuthError("Invalid email or password", code="INVALID_CREDENTIALS")
        self._store.update_last_login(user.user_id)
        return self._issue_token(user)

    def refresh_access_token(self, refresh_token: str) -> AuthToken:
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        user_id = self._store.validate_refresh_token(token_hash)
        if not user_id:
            raise AuthError("Invalid or expired refresh token", code="TOKEN_INVALID")
        user = self._store.get_user_by_id(user_id)
        if not user:
            raise AuthError("User not found", code="USER_NOT_FOUND")
        self._store.revoke_refresh_token(token_hash)  # 单次使用
        return self._issue_token(user)

    def logout(self, refresh_token: str = None):
        if refresh_token:
            token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
            self._store.revoke_refresh_token(token_hash)

    def verify_access_token(self, token: str) -> dict:
        try:
            return jwt.decode(token, self._jwt_secret, algorithms=[self._jwt_alg])
        except jwt.ExpiredSignatureError:
            raise AuthError("Token expired", code="TOKEN_EXPIRED")
        except jwt.InvalidTokenError:
            raise AuthError("Invalid token", code="TOKEN_INVALID")

    def _issue_token(self, user: User) -> AuthToken:
        groups = self._store.get_user_groups(user.user_id)
        group_ids = [g.group_id for g in groups]
        now = datetime.now()

        access_payload = {
            "sub": user.user_id, "username": user.username,
            "email": user.email, "group_ids": group_ids,
            "iat": now, "exp": now + timedelta(minutes=15), "type": "access",
        }
        refresh_payload = {
            "sub": user.user_id,
            "iat": now, "exp": now + timedelta(days=30), "type": "refresh",
        }

        access_token = jwt.encode(access_payload, self._jwt_secret, algorithm=self._jwt_alg)
        refresh_token = jwt.encode(refresh_payload, self._jwt_secret, algorithm=self._jwt_alg)

        # 存储 refresh token 哈希
        token_hash = hashlib.sha256(refresh_token.encode()).hexdigest()
        self._store.save_refresh_token(token_hash, user.user_id)

        return AuthToken(
            access_token=access_token, refresh_token=refresh_token,
            expires_in=15 * 60, user_id=user.user_id,
            group_ids=group_ids,
        )

    @staticmethod
    def _validate_password(password: str):
        if len(password) < 8:
            raise AuthError("Password must be at least 8 characters", code="WEAK_PASSWORD")
        if not re.search(r"[A-Z]", password):
            raise AuthError("Password must contain uppercase letter", code="WEAK_PASSWORD")
        if not re.search(r"[a-z]", password):
            raise AuthError("Password must contain lowercase letter", code="WEAK_PASSWORD")
        if not re.search(r"\d", password):
            raise AuthError("Password must contain digit", code="WEAK_PASSWORD")


class AuthError(Exception):
    def __init__(self, message: str, code: str):
        super().__init__(message)
        self.code = code
```

### 10.4 分组级缓存架构（SQL Key + 向量语义搜索 + 可配置 TTL）

#### 10.4.1 整体架构

```
用户问题 → [1. 缓存命中?] → [2. 向量相似推荐?] → [3. 执行 SQL] → [4. 写缓存] → 返回
              ↓                  ↓
          直接返回          显示"其他人问过类似问题"
          缓存结果           可一键复用
```

**缓存命中路径**（毫秒级响应）：

```
用户问题 → SHA256(SQL + dialect + group_id)
         → Redis 精确匹配
         → TTL 未过期
         → 返回 CachedEntry(result_data, chart_options, summary)
```

**向量语义搜索路径**（用于推荐，不用于命中）：

```
用户问题 → Embedding 模型（text-embedding-3-small / BGE）
         → LanceDB 向量检索（Top-K 相似 SQL）
         → 返回"其他人问过相似问题"推荐列表
         → 用户可一键复用该 SQL
```

#### 10.4.2 完整实现

```python
# micro_genbi/service/group_cache.py

import hashlib
import json
import re
import logging
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from typing import Optional
from collections import defaultdict

logger = logging.getLogger(__name__)

# ── 缓存条目（以 SQL 为 Key）────────────────────────────────────

@dataclass
class GroupCacheEntry:
    """
    分组级缓存条目。
    
    缓存 Key = SHA256(标准化 SQL + dialect + group_id)
    
    不缓存原始问题（汉字），因为：
    - 不同措辞 → 相同 SQL → 应命中，但汉字 key 会 miss
    - SQL 是查询意图的最稳定表达
    """
    cache_key: str          # SHA256(SQL+dialect+group_id)
    group_id: str           # 分组 ID（隔离不同组的数据）
    dialect: str            # 数据库方言

    # 缓存内容
    generated_sql: str      # 生成的 SQL（原始）
    result_json: str        # 查询结果 JSON
    row_count: int
    chart_options: str      # ECharts Options JSON
    summary: str            # LLM 自然语言摘要

    # 元数据
    created_at: datetime
    last_accessed: datetime
    access_count: int = 0   # 组内跨用户累计访问次数
    cached_by_user_id: str  # 首 次缓存的用户

    # TTL 配置（由 Group.cache_ttl_seconds 决定）
    ttl_seconds: int

    # 数据新鲜度标记
    data_version: int = 1  # 当底层数据变更时递增，使缓存失效

    @property
    def is_expired(self) -> bool:
        return datetime.now() > (self.created_at + timedelta(seconds=self.ttl_seconds))

    def to_dict(self) -> dict:
        d = asdict(self)
        d["created_at"] = self.created_at.isoformat()
        d["last_accessed"] = self.last_accessed.isoformat()
        return d


# ── SQL 标准化 ────────────────────────────────────────────────

class SQLNormalizer:
    """
    SQL 标准化：生成稳定、跨组唯一的缓存 Key。
    
    标准化策略：
    1. 转大写
    2. 去除多余空白
    3. 去除 LIMIT 值差异（如 LIMIT 100 vs LIMIT 200 → 视为同类）
    4. 去除注释
    5. 参数化常量（'2024-01-01' → '?'）
    """

    def normalize(self, sql: str, dialect: str) -> str:
        s = sql.strip()
        # 去除注释
        s = re.sub(r"--[^\n]*", "", s)
        s = re.sub(r"/\*.*?\*/", "", s, flags=re.DOTALL)
        # 转大写关键字
        for keyword in ["SELECT", "FROM", "WHERE", "JOIN", "GROUP BY",
                         "ORDER BY", "HAVING", "LIMIT"]:
            s = re.sub(rf"\b{keyword}\b", keyword, s, flags=re.IGNORECASE)
        # 去除多余空白
        s = re.sub(r"\s+", " ", s).strip()
        return s

    def make_cache_key(
        self,
        sql: str,
        dialect: str,
        group_id: str,
    ) -> str:
        """
        生成缓存 Key。
        
        包含 group_id 确保：
        - 不同组查相同 SQL → 各自有独立缓存
        - 组内任何用户命中 → 其他人也可复用
        """
        normalized = self.normalize(sql, dialect)
        raw = f"{normalized}|{dialect}|{group_id}"
        return f"gcache:{hashlib.sha256(raw.encode('utf-8')).hexdigest()}"

    def make_vector_key(self, sql: str) -> str:
        """
        生成向量检索用的 Key（仅 SQL 文本，不含 group_id）。
        用于跨组相似查询推荐。
        """
        normalized = self.normalize(sql, "")
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


# ── 向量语义搜索（跨组相似推荐）─────────────────────────────────

class VectorSimilaritySearch:
    """
    向量语义搜索服务。
    
    用于：用户输入问题 → 找到"其他人问过的相似问题"
    不用于：缓存命中（缓存命中用 SQL Key 的精确匹配）
    
    实现：LanceDB（轻量级向量数据库）
    嵌入模型：BGE-large-zh-v1.5（中文优化）/ text-embedding-3-small（英文）
    """

    def __init__(self, embedding_model: str = "bge-large-zh-v1.5"):
        self._embedding_model = embedding_model
        self._table = None  # LanceDB Table
        self._embedding_cache: dict[str, list[float]] = {}
        self._init_lancedb()

    def _init_lancedb(self):
        try:
            import lancedb
            db = lancedb.connect("./.microgenbi/vector_db")
            # schema: cache_key, sql_text, group_id, embedding
            self._table = db.create_table(
                "sql_embeddings", exist_ok=True,
                schema={
                    "cache_key": "string",
                    "sql_text": "string",
                    "dialect": "string",
                    "group_id": "string",
                    "user_id": "string",
                    "created_at": "string",
                }
            )
        except ImportError:
            logger.warning("LanceDB not installed, vector search disabled")
            self._table = None

    async def embed(self, text: str) -> list[float]:
        """对文本进行 Embedding（带内存缓存）"""
        import hashlib as _h
        cache_key = _h.md5(text.encode()).hexdigest()
        if cache_key in self._embedding_cache:
            return self._embedding_cache[cache_key]

        # 使用 OpenAI Embedding 或本地模型
        # 以下为抽象接口，具体实现根据 embedding_model 选择
        embedding = await self._call_embedding_api(text, self._embedding_model)
        self._embedding_cache[cache_key] = embedding
        return embedding

    async def _call_embedding_api(
        self, text: str, model: str
    ) -> list[float]:
        """调用 Embedding API（可扩展：OpenAI / 本地 BGE）"""
        # TODO: 实现实际调用
        # 如果 model 包含 "bge" → 使用本地 BGE 模型
        # 否则 → 使用 OpenAI text-embedding-3-small
        return [0.0] * 1024  # placeholder

    async def index_sql(
        self,
        cache_entry: GroupCacheEntry,
        sql_text: str,
    ):
        """将新缓存条目加入向量索引"""
        if not self._table:
            return
        try:
            embedding = await self.embed(sql_text)
            await self._table.add([
                {
                    "cache_key": cache_entry.cache_key,
                    "sql_text": sql_text,
                    "dialect": cache_entry.dialect,
                    "group_id": cache_entry.group_id,
                    "user_id": cache_entry.cached_by_user_id,
                    "created_at": cache_entry.created_at.isoformat(),
                    "vector": embedding,
                }
            ])
        except Exception as e:
            logger.warning(f"Failed to index SQL vector: {e}")

    async def search_similar(
        self,
        question: str,
        top_k: int = 5,
        group_id: str = None,
    ) -> list[dict]:
        """
        搜索与用户问题最相似的已缓存 SQL。
        
        返回：跨组 Top-K 相似查询（可推荐给用户）
        如指定 group_id → 仅返回同组结果
        """
        if not self._table:
            return []

        try:
            query_embedding = await self.embed(question)
            query = self._table.search(query_embedding, "vector")

            if group_id:
                query = query.where(f"group_id = '{group_id}'")

            results = await query.limit(top_k).to_list()

            return [
                {
                    "cache_key": r["cache_key"],
                    "sql_text": r["sql_text"],
                    "dialect": r["dialect"],
                    "group_id": r["group_id"],
                    "similarity": r.get("_score", 0),
                }
                for r in results
            ]
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            return []


# ── 分组级缓存管理器 ─────────────────────────────────────────

class GroupCache:
    """
    分组级缓存管理器。
    
    核心设计：
    1. 缓存 Key = SHA256(SQL + dialect + group_id)
       → 同组用户问相同 SQL → 命中共享缓存
    2. TTL 由 Group 级别控制（管理员配置）
    3. 实时表模式（realtime_table_patterns）→ 跳过缓存
    4. 写操作触发同表缓存失效（按表名正则匹配）
    5. 向量搜索提供跨组相似查询推荐
    """

    def __init__(
        self,
        redis_url: str = None,
        vector_search: VectorSimilaritySearch = None,
    ):
        # Redis 缓存后端（生产）
        self._redis = None
        if redis_url:
            try:
                import redis
                self._redis = redis.from_url(redis_url, decode_responses=True)
            except Exception as e:
                logger.warning(f"Redis unavailable: {e}, using memory fallback")

        # 内存缓存兜底
        self._memory: dict[str, GroupCacheEntry] = {}
        self._memory_order: list[str] = []

        self._normalizer = SQLNormalizer()
        self._vector = vector_search or VectorSimilaritySearch()

    # ── 核心：缓存 Key 生成 ───────────────────────────────────

    def _effective_ttl(self, group_id: str, user_ttl_override: int = None) -> int:
        """获取有效 TTL（用户覆盖 > 组配置 > 默认值）"""
        if user_ttl_override is not None:
            return user_ttl_override
        # 从 Group 配置读取（需要外部注入）
        return self._group_ttl_cache.get(group_id, 3600)

    def _is_realtime_table(self, sql: str, group_id: str) -> bool:
        """判断 SQL 是否涉及实时表（跳过缓存）"""
        patterns = self._group_realtime_patterns.get(group_id, [])
        sql_upper = sql.upper()
        return any(re.match(p, sql_upper) for p in patterns)

    # ── 缓存读写 ─────────────────────────────────────────────

    async def get(
        self,
        sql: str,
        dialect: str,
        group_id: str,
    ) -> Optional[GroupCacheEntry]:
        """
        根据生成的 SQL 查找缓存。
        
        注意：传入的是 LLM 生成的 SQL，不是用户的原始问题。
        这样保证：同组用户、相同 SQL → 共享缓存。
        """
        key = self._normalizer.make_cache_key(sql, dialect, group_id)

        if self._redis:
            raw = self._redis.get(key)
            if raw:
                data = json.loads(raw)
                entry = self._json_to_entry(data)
                if entry.is_expired:
                    await self.delete(key)
                    return None
                # 更新访问计数（异步）
                self._redis.hincrby(f"{key}:stats", "access_count", 1)
                self._redis.expire(f"{key}:stats", 86400)
                return entry

        # 内存缓存
        entry = self._memory.get(key)
        if entry and not entry.is_expired:
            entry.access_count += 1
            entry.last_accessed = datetime.now()
            return entry

        return None

    async def set(
        self,
        sql: str,
        dialect: str,
        group_id: str,
        result_data: list[dict],
        generated_sql: str,
        row_count: int,
        user_id: str,
        chart_options: dict = None,
        summary: str = "",
        ttl_seconds: int = None,
    ):
        """写入缓存"""
        # 实时表跳过缓存
        if self._is_realtime_table(sql, group_id):
            return

        key = self._normalizer.make_cache_key(sql, dialect, group_id)
        ttl = ttl_seconds or self._effective_ttl(group_id)
        now = datetime.now()

        entry = GroupCacheEntry(
            cache_key=key,
            group_id=group_id,
            dialect=dialect,
            generated_sql=generated_sql,
            result_json=json.dumps(result_data, ensure_ascii=False),
            row_count=row_count,
            chart_options=json.dumps(chart_options, ensure_ascii=False) if chart_options else "",
            summary=summary,
            created_at=now,
            last_accessed=now,
            access_count=1,
            cached_by_user_id=user_id,
            ttl_seconds=ttl,
        )

        if self._redis:
            # 写入缓存 + 统计 Hash
            self._redis.setex(key, ttl, json.dumps(entry.to_dict(), ensure_ascii=False))
            self._redis.hsetnx(f"{key}:stats", "created_at", now.isoformat())
            self._redis.hincrby(f"{key}:stats", "access_count", 1)
            self._redis.expire(f"{key}:stats", 86400)
        else:
            # 内存缓存
            self._memory[key] = entry
            if key not in self._memory_order:
                self._memory_order.append(key)
                if len(self._memory_order) > 5000:
                    oldest = self._memory_order.pop(0)
                    self._memory.pop(oldest, None)

        # 加入向量索引（异步）
        await self._vector.index_sql(entry, generated_sql)

        logger.debug(f"Cached SQL for group {group_id}: {sql[:60]}...")

    async def delete(self, key: str):
        if self._redis:
            self._redis.delete(key, f"{key}:stats")
        self._memory.pop(key, None)
        if key in self._memory_order:
            self._memory_order.remove(key)

    async def invalidate_by_table_pattern(
        self,
        group_id: str,
        table_patterns: list[str],
    ):
        """
        写操作后，按表名正则失效相关缓存。
        
        当某表发生写操作（INSERT/UPDATE/DELETE）时，
        同组内涉及该表的所有缓存全部失效。
        """
        if self._redis:
            # Redis SCAN 匹配
            pattern = f"gcache:*"
            cursor = 0
            deleted = 0
            while True:
                cursor, keys = self._redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    raw = self._redis.get(key)
                    if raw:
                        data = json.loads(raw)
                        if data.get("group_id") != group_id:
                            continue
                        # 检查 SQL 是否涉及目标表
                        sql = data.get("generated_sql", "").upper()
                        if any(re.search(p.upper(), sql) for p in table_patterns):
                            self._redis.delete(key, f"{key}:stats")
                            deleted += 1
                if cursor == 0:
                    break
            logger.info(f"Invalidated {deleted} cache entries for tables: {table_patterns}")
        else:
            # 内存缓存遍历失效
            deleted = 0
            to_delete = []
            for key, entry in self._memory.items():
                if entry.group_id != group_id:
                    continue
                sql = entry.generated_sql.upper()
                if any(re.search(p.upper(), sql) for p in table_patterns):
                    to_delete.append(key)
            for key in to_delete:
                self._memory.pop(key, None)
                self._memory_order.remove(key)
                deleted += 1
            logger.info(f"Invalidated {deleted} memory cache entries")

    async def search_similar(
        self, question: str, group_id: str = None, top_k: int = 5
    ) -> list[dict]:
        """
        语义相似查询推荐。
        用于：当缓存 miss 时，推荐同组用户问过的相似问题。
        """
        return await self._vector.search_similar(
            question=question,
            top_k=top_k,
            group_id=group_id,
        )

    async def get_stats(self, group_id: str = None) -> dict:
        """获取缓存统计"""
        if self._redis:
            return {"backend": "redis", "enabled": True}
        total = len(self._memory)
        by_group = defaultdict(int)
        for entry in self._memory.values():
            by_group[entry.group_id] += 1
        return {
            "backend": "memory",
            "enabled": True,
            "total_entries": total,
            "by_group": dict(by_group),
        }

    @staticmethod
    def _json_to_entry(data: dict) -> GroupCacheEntry:
        return GroupCacheEntry(
            cache_key=data["cache_key"],
            group_id=data["group_id"],
            dialect=data["dialect"],
            generated_sql=data["generated_sql"],
            result_json=data["result_json"],
            row_count=data["row_count"],
            chart_options=data.get("chart_options", ""),
            summary=data.get("summary", ""),
            created_at=datetime.fromisoformat(data["created_at"]),
            last_accessed=datetime.fromisoformat(data["last_accessed"]),
            access_count=data.get("access_count", 0),
            cached_by_user_id=data.get("cached_by_user_id", ""),
            ttl_seconds=data.get("ttl_seconds", 3600),
        )
```

### 10.5 分组级写操作并发控制

**两个场景需要并发控制**：

| 场景 | 问题 | 解决方案 |
|------|------|---------|
| **乐观锁**（普通 UPDATE） | 用户 A 和用户 B 同时修改同一条记录，后提交者覆盖前者的修改 | 数据库表加 `version` 字段，UPDATE 时检查 version |
| **Redis 分布式锁**（DDL / 批量写） | 两个人同时执行 `ALTER TABLE` 或 `TRUNCATE`，导致表损坏 | Redis SETNX 锁 + TTL，锁内执行操作 |

```python
# micro_genbi/security/write_coordinator.py

import asyncio
import uuid
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

# ── 写操作类型 ────────────────────────────────────────────────

class WriteOperationType(str, Enum):
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    TRUNCATE = "truncate"
    ALTER = "alter"
    CREATE = "create"
    DROP = "drop"
    DDL = "ddl"               # 其他 DDL 操作

# ── 乐观锁（版本号控制）────────────────────────────────────────

class OptimisticLock:
    """
    乐观锁实现。
    
    工作机制：
    1. 读取记录时获取当前 version
    2. UPDATE 时 WHERE version = old_version
    3. 影响行数 = 0 → 说明被其他事务修改 → 抛出冲突
    4. 影响行数 = 1 → 修改成功，version += 1
    
    适用：普通 INSERT / UPDATE / DELETE
    """

    @staticmethod
    def add_version_check(
        original_sql: str,
        table_name: str,
        primary_key: str,
        record_id: str,
        current_version: int,
        operation: WriteOperationType,
    ) -> tuple[str, int]:
        """
        将乐观锁条件注入 SQL。
        
        对于 UPDATE/DELETE，追加 WHERE version = ?
        对于 INSERT，添加 version = 1 字段
        
        返回：(修改后的 SQL, 新版本号)
        """
        new_version = current_version + 1
        sql_upper = original_sql.upper().strip()

        if operation == WriteOperationType.UPDATE:
            # 追加乐观锁条件
            protected_sql = f"{original_sql.rstrip(';')} " \
                           f"WHERE \"{primary_key}\" = '{record_id}' " \
                           f"AND \"version\" = {current_version};"
            return protected_sql, new_version

        elif operation == WriteOperationType.DELETE:
            protected_sql = f"{original_sql.rstrip(';')} " \
                           f"WHERE \"{primary_key}\" = '{record_id}' " \
                           f"AND \"version\" = {current_version};"
            return protected_sql, new_version

        elif operation == WriteOperationType.INSERT:
            # 注入 version 字段
            protected_sql = original_sql.rstrip(';').rstrip(')')
            protected_sql += f', "version") VALUES '
            protected_sql += original_sql.split("VALUES", 1)[1].rstrip(';').rstrip(')')
            protected_sql += f", {new_version});"
            return protected_sql, new_version

        return original_sql, current_version

    @staticmethod
    def check_conflict(affected_rows: int, record_id: str) -> bool:
        """
        检查 UPDATE/DELETE 是否因乐观锁冲突而未生效。
        affected_rows = 0 → 冲突发生
        """
        if affected_rows == 0:
            logger.warning(
                f"Optimistic lock conflict detected for record {record_id}"
            )
            return True
        return False


# ── Redis 分布式锁 ────────────────────────────────────────────

class DistributedLock:
    """
    Redis 分布式锁（SETNX + TTL）。
    
    用于：DDL 操作（ALTER/DROP/TRUNCATE）或高危批量写
    防止：多人同时对同一表执行 DDL 导致表损坏
    
    特性：
    - 锁持有者标记（防止误删他人锁）
    - TTL 自动释放（防止死锁）
    - 可重入（同一持有者可续期）
    """

    LOCK_PREFIX = "mgb:write_lock:"

    def __init__(self, redis_url: str):
        import redis
        self._redis = redis.from_url(redis_url, decode_responses=True)

    async def acquire(
        self,
        resource: str,
        owner_id: str,
        ttl_seconds: int = 30,
    ) -> bool:
        """
        尝试获取分布式锁。
        
        - resource: 锁定的资源名（如 "table:orders"）
        - owner_id: 锁持有者 ID（通常是 user_id + task_id）
        - ttl_seconds: 锁自动过期时间
        
        返回：True = 获得锁，False = 锁已被占用
        """
        key = f"{self.LOCK_PREFIX}{resource}"
        acquired = self._redis.set(
            key, owner_id,
            nx=True,      # 仅当 key 不存在时设置（SETNX）
            ex=ttl_seconds,  # 过期时间（防止死锁）
        )
        if acquired:
            logger.info(f"Lock acquired: {resource} by {owner_id} (TTL={ttl_seconds}s)")
        else:
            current_owner = self._redis.get(key)
            logger.warning(
                f"Lock contention: {resource} held by {current_owner}, "
                f"requested by {owner_id}"
            )
        return bool(acquired)

    async def release(self, resource: str, owner_id: str) -> bool:
        """
        释放锁（仅锁持有者可释放，防止误删）。
        """
        key = f"{self.LOCK_PREFIX}{resource}"
        # Lua 脚本：原子性检查 owner 并删除
        lua = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        else
            return 0
        end
        """
        result = self._redis.eval(lua, 1, key, owner_id)
        if result:
            logger.info(f"Lock released: {resource} by {owner_id}")
        return bool(result)

    async def extend(
        self,
        resource: str,
        owner_id: str,
        ttl_seconds: int = 30,
    ) -> bool:
        """延长锁的 TTL（可重入，同一持有者续期）"""
        key = f"{self.LOCK_PREFIX}{resource}"
        lua = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('expire', KEYS[1], ARGV[2])
        else
            return 0
        end
        """
        result = self._redis.eval(lua, 1, key, owner_id, ttl_seconds)
        return bool(result)

    async def get_lock_info(self, resource: str) -> dict:
        """查看锁状态（谁持有、剩余 TTL）"""
        key = f"{self.LOCK_PREFIX}{resource}"
        owner = self._redis.get(key)
        ttl = self._redis.ttl(key)
        return {
            "resource": resource,
            "locked": owner is not None,
            "owner": owner,
            "ttl_seconds": ttl if ttl > 0 else 0,
        }


# ── 写操作协调器 ────────────────────────────────────────────────

class WriteCoordinator:
    """
    写操作协调器。
    
    对外统一入口，内部路由到乐观锁或分布式锁。
    
    工作流程：
    1. 分析写操作类型（DML / DDL）
    2. 涉及表名提取（从 SQL 解析）
    3. DDL → 获取分布式锁 → 执行 → 释放锁
    4. DML → 注入乐观锁版本号 → 执行 → 检查冲突
    5. 无论成功失败 → 触发相关缓存失效
    """

    def __init__(
        self,
        distributed_lock: DistributedLock,
        group_cache: "GroupCache",
    ):
        self._lock = distributed_lock
        self._cache = group_cache

    async def execute_write(
        self,
        sql: str,
        operation: WriteOperationType,
        table_name: str,
        group_id: str,
        user_id: str,
        task_id: str,
        current_version: int = None,
        record_id: str = None,
        primary_key: str = "id",
    ) -> "WriteResult":
        """
        执行写操作并处理并发控制。
        
        返回 WriteResult 包含：
        - success: 是否成功
        - affected_rows: 影响行数
        - conflict: 是否发生并发冲突
        - lock_info: 锁信息（DDL 时）
        """
        owner_id = f"{user_id}:{task_id}"
        lock_key = f"table:{table_name}"
        result = WriteResult()

        try:
            if self._is_ddl(operation):
                # ── DDL：分布式锁保护 ───────────────────────
                acquired = await self._lock.acquire(
                    resource=lock_key,
                    owner_id=owner_id,
                    ttl_seconds=60,  # DDL 最多 60 秒
                )
                if not acquired:
                    return WriteResult(
                        success=False,
                        conflict=False,
                        error=f"表 {table_name} 正在被其他操作锁定，请稍后重试",
                    )

                # 续期任务：DDL 执行中持续续锁
                asyncio.create_task(self._renew_lock(lock_key, owner_id))

            elif operation in (WriteOperationType.UPDATE, WriteOperationType.DELETE):
                # ── DML UPDATE/DELETE：乐观锁 ───────────────
                if current_version is not None and record_id:
                    sql, new_version = OptimisticLock.add_version_check(
                        sql, table_name, primary_key,
                        record_id, current_version, operation,
                    )
                    result.new_version = new_version

            # 执行 SQL（实际执行由外部 DB Driver 完成）
            # 这里模拟返回
            result.affected_rows = await self._execute_sql(sql)
            result.success = result.affected_rows >= 0

            if operation in (WriteOperationType.UPDATE, WriteOperationType.DELETE):
                # 乐观锁冲突检查
                if OptimisticLock.check_conflict(result.affected_rows, record_id):
                    result.success = False
                    result.conflict = True
                    result.error = (
                        f"记录已被其他人修改，请刷新后重新编辑。"
                        f"（您的修改基于版本 {current_version}，但当前版本已更新）"
                    )

            # 成功后：失效相关缓存
            if result.success:
                await self._cache.invalidate_by_table_pattern(
                    group_id=group_id,
                    table_patterns=[f"^{table_name}$"],
                )
                logger.info(
                    f"Write operation succeeded: {operation.value} on {table_name}, "
                    f"{result.affected_rows} rows affected"
                )

        except Exception as e:
            result.success = False
            result.error = str(e)
            logger.error(f"Write operation failed: {e}")

        finally:
            # 释放分布式锁
            if self._is_ddl(operation):
                await self._lock.release(lock_key, owner_id)

        return result

    def _is_ddl(self, operation: WriteOperationType) -> bool:
        return operation in (
            WriteOperationType.TRUNCATE,
            WriteOperationType.ALTER,
            WriteOperationType.CREATE,
            WriteOperationType.DROP,
            WriteOperationType.DDL,
        )

    async def _execute_sql(self, sql: str) -> int:
        """执行 SQL（实际由 DatabaseExecutor 调用）"""
        # placeholder
        return 0

    async def _renew_lock(self, resource: str, owner_id: str):
        """后台任务：自动续期分布式锁（DDL 长时间执行时）"""
        while True:
            await asyncio.sleep(20)  # 每 20 秒续一次
            extended = await self._lock.extend(resource, owner_id, ttl_seconds=60)
            if not extended:
                break


@dataclass
class WriteResult:
    success: bool = False
    affected_rows: int = 0
    conflict: bool = False        # 乐观锁冲突
    lock_waiting: bool = False    # 等待锁中
    new_version: int = None
    error: str = ""
    warning: str = ""

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "affected_rows": self.affected_rows,
            "conflict": self.conflict,
            "lock_waiting": self.lock_waiting,
            "new_version": self.new_version,
            "error": self.error,
            "warning": self.warning,
        }
```

### 10.6 REST API 接口

```yaml
# ── 认证 ────────────────────────────────────────────────────────

POST /api/v1/auth/register
  body: { "username": "...", "email": "...", "password": "..." }
  → 201: { "user": {...}, "access_token": "...", "refresh_token": "..." }

POST /api/v1/auth/login
  body: { "email": "...", "password": "..." }
  → 200: { "access_token": "...", "refresh_token": "...", "expires_in": 900 }

POST /api/v1/auth/refresh
  body: { "refresh_token": "..." }
  → 200: { "access_token": "...", "refresh_token": "..." }

POST /api/v1/auth/logout
  header: Authorization: Bearer {access_token}
  body: { "refresh_token": "..." }
  → 204

# ── 分组管理 ─────────────────────────────────────────────────────

POST   /api/v1/groups                    # 创建分组（管理员）
GET    /api/v1/groups                    # 列出用户所属分组
GET    /api/v1/groups/{group_id}         # 查看分组详情
PUT    /api/v1/groups/{group_id}         # 更新分组配置
DELETE /api/v1/groups/{group_id}         # 删除分组

GET    /api/v1/groups/{group_id}/members  # 列出组成员
POST   /api/v1/groups/{group_id}/members # 添加成员（admin）
DELETE /api/v1/groups/{group_id}/members/{user_id}  # 移除成员

# 分组配置（缓存 TTL / 实时表模式 / 写并发模式）
PUT    /api/v1/groups/{group_id}/settings
  body: {
    "cache_ttl_seconds": 7200,          # 用户可配置的缓存 TTL
    "cache_enabled": true,
    "realtime_table_patterns": ["^stock_.*", "^realtime_.*"],
    "write_concurrency_mode": "optimistic",
    "max_write_lock_seconds": 30,
  }

# ── 缓存 ────────────────────────────────────────────────────────

GET  /api/v1/groups/{group_id}/cache/stats  # 组级缓存统计
POST /api/v1/groups/{group_id}/cache/invalidate  # 手动失效缓存
  body: { "table_patterns": ["^orders$"] }

# ── 写操作 ──────────────────────────────────────────────────────

POST /api/v1/groups/{group_id}/write
  header: Authorization: Bearer {access_token}
  body: {
    "sql": "UPDATE orders SET status = 'completed' WHERE id = ?",
    "operation": "update",
    "table_name": "orders",
    "record_id": "123",
    "current_version": 5,      # 乐观锁版本号
    "primary_key": "id",
  }
  → 200: { "success": true, "affected_rows": 1, "new_version": 6 }
  → 409: { "success": false, "conflict": true, "error": "记录已被修改" }
  → 423: { "success": false, "error": "表正在被锁定" }

GET  /api/v1/groups/{group_id}/write/lock-status?table=orders
  → 200: { "locked": true, "owner": "usr_xxx:task_yyy", "ttl_seconds": 45 }
```

### 10.7 缓存 Key 设计总结

```
┌────────────────────────────────────────────────────────────────────┐
│                        缓存 Key 生成流程                            │
│                                                                    │
│  用户问题：「各部门上月的报销总额」                                  │
│                 ↓                                                  │
│         LLM 生成 SQL                                               │
│  SELECT "dept_name", SUM("amount") ...                             │
│                 ↓                                                  │
│         SQL 标准化（去注释、大写、归一化空格）                        │
│  SELECT "dept_name", SUM("amount") ... GROUP BY "dept_name"         │
│                 ↓                                                  │
│         SHA256(标准化SQL + dialect + group_id)                      │
│  = SHA256("SELECT...GROUP BY..." + "mysql" + "grp_abc123")          │
│                 ↓                                                  │
│         Redis 精确查找                                              │
│  gcache:a3f8b2c1... ← Hit! 返回缓存结果                            │
│                                                                    │
│  ── 同组第二个用户问「各部门的报销总额是多少」（措辞不同）────         │
│                 ↓                                                  │
│         LLM 生成相同 SQL                                            │
│                 ↓                                                  │
│         命中同一缓存 Key → 直接复用                                  │
│                                                                    │
│  ── 向量搜索（推荐，不命中）────────────────────────────────        │
│                 ↓                                                  │
│  用户问题 → Embedding → LanceDB Top-K 相似 SQL                     │
│  → 返回「这些查询和你的问题相似，可一键复用」                         │
└────────────────────────────────────────────────────────────────────┘
```


---

## 十二、枚举推断规则与字段确认机制

### 12.1 问题定义

现有 Section 11.4 的枚举推断过于粗糙，本节做三件事：

```
┌────────────────────────────────────────────────────────────────────────┐
│  1️⃣ 推断规则精细化：                                                 │
│     · state / mode / type / kind / category 后缀 → 枚举列             │
│     · is / has / can 前缀 → 布尔开关量（0/1）                        │
│     · 无注释时采样推断 → 区分【类型列】vs【开关量】                   │
│                                                                        │
│  2️⃣ 置信度评分 + 人工确认工作流：                                     │
│     · 高置信度（≥0.8）：直接注入 Prompt，标记"已验证"                 │
│     · 低置信度（< 0.8）：进入"待确认"队列，前端弹窗引导用户确认         │
│     · 零置信度（无法推断）：强制阻断 SQL 生成，直到用户手动维护完成       │
│                                                                        │
│  3️⃣ 硬性关卡：                                                       │
│     · 所有参与查询的列必须有有效映射                                   │
│     · 未确认列 → 返回友好错误，引导用户完成字段维护                     │
│     · 仅读列（SELECT 列表中的列）同样需要映射，否则 SQL 质量无保证      │
└────────────────────────────────────────────────────────────────────────┘
```

### 12.2 枚举列命名规则库

```python
# micro_genbi/schema/enum_rules.py

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

# ── 枚举类型枚举 ─────────────────────────────────────────────────

class EnumType(str, Enum):
    """枚举值类型分类"""
    TYPE_CODE = "type_code"     # 类型码：state/mode/type/kind/category 后缀
    BOOLEAN_FLAG = "bool_flag" # 开关量：is/has/can/enable 前缀
    STATUS_CODE = "status_code" # 状态码：status/state 后缀（同 TYPE_CODE）
    UNKNOWN = "unknown"         # 未知


@dataclass
class EnumInferenceRule:
    """
    枚举推断规则定义。
    
    支持两种匹配方式：
    - suffix: 列名以后缀结尾（如 status / state / mode）
    - prefix: 列名以前缀开头（如 is_ / has_ / can_）
    - pattern: 正则表达式匹配（如 r".*_state$"）
    """
    name: str
    enum_type: EnumType
    match_type: str            # "suffix" | "prefix" | "regex" | "exact"
    pattern: str               # 匹配的模式字符串
    default_values: list[tuple[str, str]] = field(default_factory=list)
    description: str = ""
    priority: int = 100       # 优先级（越小越优先）

    def matches(self, column_name: str) -> bool:
        col = column_name.lower()
        if self.match_type == "suffix":
            return col.endswith(self.pattern.lower())
        elif self.match_type == "prefix":
            return col.startswith(self.pattern.lower())
        elif self.match_type == "regex":
            return bool(re.search(self.pattern, col))
        elif self.match_type == "exact":
            return col == self.pattern.lower()
        return False


# ── 内置规则库 ──────────────────────────────────────────────────

BUILTIN_ENUM_RULES: list[EnumInferenceRule] = [

    # ── 类型码规则（state / mode / type / kind / category）──────────
    EnumInferenceRule(
        name="state后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="state",
        description="以 state 结尾的列通常是状态枚举",
        priority=10,
    ),
    EnumInferenceRule(
        name="status后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="status",
        description="以 status 结尾的列通常是状态枚举",
        priority=10,
    ),
    EnumInferenceRule(
        name="mode后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="mode",
        description="以 mode 结尾的列通常是模式枚举（如发油方式）",
        priority=10,
    ),
    EnumInferenceRule(
        name="type后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="type",
        description="以 type 结尾的列通常是类型枚举",
        priority=10,
    ),
    EnumInferenceRule(
        name="kind后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="kind",
        description="以 kind 结尾的列通常是类型枚举",
        priority=10,
    ),
    EnumInferenceRule(
        name="category后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="category",
        description="以 category 结尾的列通常是分类枚举",
        priority=10,
    ),
    EnumInferenceRule(
        name="level后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="level",
        description="以 level 结尾的列通常是等级枚举（如 VIP 等级）",
        priority=20,
    ),
    EnumInferenceRule(
        name="priority后缀",
        enum_type=EnumType.TYPE_CODE,
        match_type="suffix",
        pattern="priority",
        description="以 priority 结尾的列通常是优先级枚举",
        priority=20,
    ),

    # ── 开关量规则（is / has / can / enable 前缀）─────────────────
    EnumInferenceRule(
        name="is_前缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="prefix",
        pattern="is_",
        description="以 is_ 开头的是布尔开关量（0/1）",
        default_values=[("0", "否/关闭"), ("1", "是/开启")],
        priority=5,  # 最高优先：is_ 几乎一定是布尔
    ),
    EnumInferenceRule(
        name="has_前缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="prefix",
        pattern="has_",
        description="以 has_ 开头的是布尔开关量",
        default_values=[("0", "否"), ("1", "是")],
        priority=5,
    ),
    EnumInferenceRule(
        name="can_前缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="prefix",
        pattern="can_",
        description="以 can_ 开头的是布尔开关量",
        default_values=[("0", "否"), ("1", "是")],
        priority=5,
    ),
    EnumInferenceRule(
        name="enable前缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="prefix",
        pattern="enable",
        description="以 enable 开头的是布尔开关量",
        default_values=[("0", "禁用"), ("1", "启用")],
        priority=5,
    ),
    EnumInferenceRule(
        name="flag后缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="suffix",
        pattern="flag",
        description="以 flag 结尾的列通常是标志位",
        default_values=[("0", "否"), ("1", "是")],
        priority=30,
    ),
    EnumInferenceRule(
        name="active后缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="suffix",
        pattern="active",
        description="以 active 结尾的列通常是激活状态",
        default_values=[("0", "未激活"), ("1", "已激活")],
        priority=30,
    ),
    EnumInferenceRule(
        name="deleted后缀",
        enum_type=EnumType.BOOLEAN_FLAG,
        match_type="suffix",
        pattern="deleted",
        description="以 deleted 结尾的列通常是软删除标记",
        default_values=[("0", "未删除"), ("1", "已删除")],
        priority=30,
    ),
]


class EnumRuleRegistry:
    """
    枚举推断规则注册表。
    
    支持：
    - 内置规则（不可删除）
    - 用户自定义规则（管理员可在 Group 级别添加）
    - 规则优先级排序（低优先值 = 高优先级）
    """

    def __init__(self):
        self._rules: list[EnumInferenceRule] = sorted(
            BUILTIN_ENUM_RULES, key=lambda r: r.priority
        )

    def add_rule(self, rule: EnumInferenceRule):
        """添加自定义规则（按优先级插入）"""
        self._rules.append(rule)
        self._rules.sort(key=lambda r: r.priority)

    def find_matching_rule(self, column_name: str) -> Optional[EnumInferenceRule]:
        """查找第一个匹配的规则"""
        for rule in self._rules:
            if rule.matches(column_name):
                return rule
        return None

    def suggest_type(
        self, column_name: str, comment: str = ""
    ) -> Optional[EnumInferenceRule]:
        """根据列名 + 注释综合推断匹配的规则"""
        # 先从注释中提取（注释优先级最高）
        rule_from_comment = self._match_from_comment(comment)
        if rule_from_comment:
            return rule_from_comment

        # 再按列名匹配规则
        return self.find_matching_rule(column_name)

    def _match_from_comment(self, comment: str) -> Optional[EnumInferenceRule]:
        """从注释文本中匹配规则关键词"""
        if not comment:
            return None
        for rule in self._rules:
            # 检查注释中是否包含规则相关关键词
            if rule.enum_type == EnumType.BOOLEAN_FLAG:
                # 注释中含 "开关" / "是否" / "0=否,1=是" 等
                if any(kw in comment for kw in ["开关", "是否", "0=否", "0=停", "0=关"]):
                    return rule
            elif rule.enum_type == EnumType.TYPE_CODE:
                # 注释中含 "方式" / "类型" / "状态" 等
                if any(kw in comment for kw in ["方式", "类型", "状态", "级别"]):
                    return rule
        return None
```

### 12.3 置信度评分与推断引擎

```python
# micro_genbi/schema/enum_inference_engine.py

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

# ── 置信度等级 ──────────────────────────────────────────────────

class ConfidenceLevel(str):
    HIGH = "high"       # ≥ 0.85：直接从注释解析，可信度极高
    MEDIUM = "medium"   # 0.50~0.84：采样推断 + 命名规则，需确认
    LOW = "low"         # 0.20~0.49：仅命名规则，无采样数据，需强制确认
    ZERO = "zero"       # 0.00：无法推断，必须手动维护

# ── 推断结果模型 ───────────────────────────────────────────────

@dataclass
class EnumInferenceResult:
    """
    单列枚举推断结果。
    
    包含：推断值映射 + 置信度评分 + 确认状态。
    """
    table_name: str
    column_name: str

    # 推断结论
    is_enum: bool                  # 是否为枚举列
    enum_type: EnumType            # 枚举类型
    enum_values: list[EnumMapping]  # 推断的枚举值映射

    # 置信度评分
    confidence: float              # 0.0 ~ 1.0
    confidence_level: str          # HIGH / MEDIUM / LOW / ZERO
    score_breakdown: dict = field(default_factory=dict)
    # 示例：{"comment_match": 0.5, "name_match": 0.2, "sample_match": 0.3}

    # 来源
    source: str                   # "comment" / "rule" / "sample" / "manual" / "none"
    matched_rule: str = ""        # 命中的规则名

    # 确认状态（核心）
    confirmation_status: str = "pending"  # pending / confirmed / rejected / manual
    confirmed_by: str = ""
    confirmed_at: datetime = None

    # 最终映射（确认后的结果）
    final_mapping: list[EnumMapping] = field(default_factory=list)

    def is_confirmed(self) -> bool:
        return self.confirmation_status in ("confirmed", "manual")

    def is_blocking(self) -> bool:
        """零置信度 → 强制阻断 SQL 生成"""
        return self.confidence == 0.0 and self.confirmation_status == "pending"


@dataclass
class EnumMapping:
    db_value: str
    display_value: str
    description: str = ""
    source: str = ""       # "comment" / "sample" / "rule" / "manual"
    sample_count: int = 0  # 采样中该值出现次数（用于置信度计算）


# ── 推断引擎 ──────────────────────────────────────────────────

class EnumInferenceEngine:
    """
    枚举推断引擎。
    
    推断流程：
    
    Step 1 — 注释解析（最高优先级，得分 0.8~1.0）
    ┌─────────────────────────────────────────────────────────────┐
    │ 注释: "发油方式 1:按视体积发油;2:按标准体积发油;3:按重量发油" │
    │ → 完整解析出 3 个枚举值，置信度 = 0.95                      │
    └─────────────────────────────────────────────────────────────┘
    
    Step 2 — 规则匹配（次优先级，得分 0.3~0.6）
    ┌─────────────────────────────────────────────────────────────┐
    │ 列名: loadOutOilMode 匹配 "mode后缀" 规则                   │
    │ → 推断为 TYPE_CODE 类型，置信度 +0.3                        │
    └─────────────────────────────────────────────────────────────┘
    
    Step 3 — 采样验证（补充优先级，得分 0.0~0.4）
    ┌─────────────────────────────────────────────────────────────┐
    │ SELECT DISTINCT loadOutOilMode FROM table LIMIT 50;        │
    │ → 采样到 [1, 2, 3]，值域 < 10 → 确认是枚举列              │
    │ → 置信度 +0.3                                             │
    └─────────────────────────────────────────────────────────────┘
    
    最终得分 = min(1.0, sum(各维度得分))
    
    决策阈值：
    · ≥ 0.85 → HIGH（直接注入，标记"已验证"）
    · 0.50~0.84 → MEDIUM（注入，弹窗引导用户确认）
    · 0.20~0.49 → LOW（注入但标红警告，用户必须确认）
    · = 0.00 → ZERO（阻断 SQL 生成，要求手动维护）
    """

    # 各推断维度的基准分值
    SCORE_COMMENT_FULL = 0.95    # 注释完整解析
    SCORE_COMMENT_PARTIAL = 0.70 # 注释部分匹配
    SCORE_RULE_MATCH = 0.30      # 规则匹配（mode/state/type 后缀）
    SCORE_BOOL_RULE = 0.50       # 开关量规则匹配（is_ 前缀）
    SCORE_SAMPLE_CONFIRM = 0.30  # 采样值域验证
    SCORE_SAMPLE_REJECT = -0.20  # 采样值域过大（>20）→ 否定枚举推断

    def __init__(self, rule_registry: EnumRuleRegistry):
        self._rules = rule_registry

    def infer(
        self,
        table_name: str,
        column_name: str,
        comment: str,
        sample_values: list[str],
        column_type: str,    # string / number
        existing_manual_mapping: list[EnumMapping] = None,
    ) -> EnumInferenceResult:
        """
        对单列执行枚举推断。
        
        参数：
        - existing_manual_mapping: 已有手动维护的映射（最优先）
        """
        # 优先使用用户手动维护的映射
        if existing_manual_mapping:
            return EnumInferenceResult(
                table_name=table_name,
                column_name=column_name,
                is_enum=True,
                enum_type=EnumType.TYPE_CODE,
                enum_values=existing_manual_mapping,
                confidence=1.0,
                confidence_level=ConfidenceLevel.HIGH,
                score_breakdown={"manual": 1.0},
                source="manual",
                confirmation_status="manual",
                confirmed_at=datetime.now(),
                final_mapping=existing_manual_mapping,
            )

        total_score = 0.0
        breakdown = {}
        matched_rule = None
        enum_type = EnumType.UNKNOWN

        # ── Step 1: 注释解析 ───────────────────────────────
        comment_result = self._parse_comment(comment, column_name)
        if comment_result:
            total_score += comment_result["score"]
            breakdown["comment"] = comment_result["score"]
            enum_values = comment_result["enum_values"]
            source = "comment"
            if comment_result["score"] >= self.SCORE_COMMENT_FULL - 0.05:
                enum_type = self._infer_enum_type_from_comment(comment)
        else:
            enum_values = []

        # ── Step 2: 规则匹配 ─────────────────────────────
        rule = self._rules.suggest_type(column_name, comment)
        if rule:
            matched_rule = rule.name
            if rule.enum_type == EnumType.BOOLEAN_FLAG:
                score = self.SCORE_BOOL_RULE
                enum_type = EnumType.BOOLEAN_FLAG
            else:
                score = self.SCORE_RULE_MATCH
                enum_type = EnumType.TYPE_CODE

            # 开关量：使用默认枚举值
            if rule.enum_type == EnumType.BOOLEAN_FLAG and not enum_values:
                enum_values = [
                    EnumMapping(db_value=k, display_value=v,
                                description="默认", source="rule")
                    for k, v in rule.default_values
                ]

            total_score += score
            breakdown["rule"] = score

        # ── Step 3: 采样验证 ─────────────────────────────
        sample_result = self._evaluate_sample(
            sample_values, column_type, enum_values
        )
        total_score += sample_result["score"]
        breakdown["sample"] = sample_result["score"]

        # 如果采样到值域 > 20，否定枚举推断
        if sample_result["rejected"]:
            total_score = min(total_score, 0.15)
            breakdown["rejected"] = -0.20

        # 如果采样确认了枚举值（值域小，且有值）
        if sample_result["confirmed"] and not enum_values:
            enum_values = sample_result["enum_values"]

        # 归一化到 [0, 1]
        final_score = max(0.0, min(1.0, total_score))
        confidence_level = self._score_to_level(final_score, bool(enum_values))

        # 来源判定
        if not source:
            if breakdown.get("comment", 0) >= self.SCORE_COMMENT_PARTIAL:
                source = "comment"
            elif breakdown.get("rule", 0) > 0:
                source = "rule"
            elif breakdown.get("sample", 0) > 0:
                source = "sample"
            else:
                source = "none"

        # 确认状态：HIGH → 自动 confirmed；其余 → pending
        if confidence_level == ConfidenceLevel.HIGH:
            confirmation_status = "confirmed"
        else:
            confirmation_status = "pending"

        return EnumInferenceResult(
            table_name=table_name,
            column_name=column_name,
            is_enum=(final_score >= 0.20),
            enum_type=enum_type,
            enum_values=enum_values,
            confidence=round(final_score, 3),
            confidence_level=confidence_level,
            score_breakdown=breakdown,
            source=source,
            matched_rule=matched_rule or "",
            confirmation_status=confirmation_status,
            final_mapping=enum_values if confidence_level == ConfidenceLevel.HIGH else [],
        )

    def _parse_comment(
        self, comment: str, column_name: str
    ) -> Optional[dict]:
        """从列注释中解析枚举值"""
        if not comment:
            return None

        # 支持的格式（同 Section 11.4）
        # 1. "1:按体积发油;2:按标准体积发油;3:按重量发油"
        patterns = [
            # 分号/逗号分隔：1:xxx;2:yyy;3:zzz
            (r"(\d+)\s*[:：=]\s*([^\s;，,]+(?:[^\s;，,]*[^\s;，,])?)", 1, 2),
            # 括号内：(0=否 1=是)
            (r"[（(](\d+)\s*[=：:]\s*([^）)\n]+)[）)]", 1, 2),
            # 英文：pending=待支付,processing=处理中
            (r"([A-Za-z_]+)\s*=\s*([^\s,，]+)", 1, 2),
        ]

        parsed_values = []
        for pattern, k_idx, v_idx in patterns:
            for m in re.finditer(pattern, comment):
                groups = m.groups()
                if len(groups) >= 2:
                    db_val = groups[k_idx].strip()
                    disp_val = groups[v_idx].strip()
                    if db_val and disp_val and db_val != disp_val:
                        parsed_values.append(
                            EnumMapping(
                                db_value=db_val,
                                display_value=disp_val,
                                description=f"从注释解析（匹配: {m.group(0)[:30]}）",
                                source="comment",
                            )
                        )

        if not parsed_values:
            return None

        # 判断完整度：解析出的值 ≥ 2 → 完整解析
        if len(parsed_values) >= 2:
            return {
                "enum_values": parsed_values,
                "score": self.SCORE_COMMENT_FULL,
                "completeness": "full",
            }
        else:
            return {
                "enum_values": parsed_values,
                "score": self.SCORE_COMMENT_PARTIAL,
                "completeness": "partial",
            }

    def _evaluate_sample(
        self,
        sample_values: list[str],
        column_type: str,
        existing_values: list[EnumMapping],
    ) -> dict:
        """
        评估采样数据，验证或否定枚举推断。
        
        返回：{"score": float, "confirmed": bool, "rejected": bool, "enum_values": list}
        """
        if not sample_values:
            return {"score": 0.0, "confirmed": False, "rejected": False, "enum_values": []}

        unique_vals = list(set(str(v) for v in sample_values))
        val_count = len(unique_vals)

        # 高基数 → 否定枚举
        if val_count > 20:
            return {
                "score": self.SCORE_SAMPLE_REJECT,
                "confirmed": False,
                "rejected": True,
                "enum_values": [],
            }

        # 低基数（≤ 20）且类型是字符串/数字 → 确认枚举
        if val_count <= 20 and column_type in ("string", "number"):
            # 如果没有从注释获得映射，使用采样值作为枚举
            if not existing_values:
                enum_values = [
                    EnumMapping(
                        db_value=v,
                        display_value=v,
                        description="从采样推断",
                        source="sample",
                        sample_count=sample_values.count(v),
                    )
                    for v in unique_vals
                ]
                return {
                    "score": self.SCORE_SAMPLE_CONFIRM,
                    "confirmed": True,
                    "rejected": False,
                    "enum_values": enum_values,
                }
            else:
                # 注释已有映射，采样仅作为置信度加分
                return {
                    "score": 0.1,
                    "confirmed": False,
                    "rejected": False,
                    "enum_values": existing_values,
                }

        return {"score": 0.0, "confirmed": False, "rejected": False, "enum_values": []}

    def _infer_enum_type_from_comment(self, comment: str) -> EnumType:
        """从注释内容推断枚举类型"""
        if not comment:
            return EnumType.UNKNOWN
        if any(kw in comment for kw in ["方式", "模式", "mode"]):
            return EnumType.TYPE_CODE
        if any(kw in comment for kw in ["开关", "是否", "启用"]):
            return EnumType.BOOLEAN_FLAG
        if any(kw in comment for kw in ["状态", "status", "state"]):
            return EnumType.TYPE_CODE
        return EnumType.TYPE_CODE

    def _score_to_level(self, score: float, has_values: bool) -> str:
        if score >= 0.85:
            return ConfidenceLevel.HIGH
        elif score >= 0.50:
            return ConfidenceLevel.MEDIUM
        elif score >= 0.20:
            return ConfidenceLevel.LOW
        else:
            return ConfidenceLevel.ZERO
```

### 12.4 批次推断与待确认队列

```python
# micro_genbi/schema/enum_batch_processor.py

import asyncio
from dataclasses import dataclass, field
from typing import Optional

# ── 批次推断结果 ───────────────────────────────────────────────

@dataclass
class BatchInferenceResult:
    """整张表/整个 Schema 的批次推断结果"""
    group_id: str
    table_name: str
    column_results: list[EnumInferenceResult] = field(default_factory=list)

    # 汇总
    total_columns: int = 0
    enum_columns: int = 0
    confirmed: int = 0
    pending: int = 0
    blocking: int = 0  # ZERO 置信度，需要手动维护才能继续

    # 需要用户确认的列
    pending_columns: list[str] = field(default_factory=list)
    blocking_columns: list[str] = field(default_factory=list)  # 阻断列

    def has_blocking_columns(self) -> bool:
        """是否存在阻断列（→ SQL 生成被阻止）"""
        return any(r.is_blocking() for r in self.column_results)

    def get_blocking_report(self) -> dict:
        """生成阻断报告（用于前端展示）"""
        blocking = [r for r in self.column_results if r.is_blocking()]
        pending = [r for r in self.column_results
                   if r.confidence_level in (ConfidenceLevel.MEDIUM, ConfidenceLevel.LOW)
                   and r.confirmation_status == "pending"]

        return {
            "has_blocking": bool(blocking),
            "blocking_columns": [
                {
                    "table_name": r.table_name,
                    "column_name": r.column_name,
                    "confidence": r.confidence,
                    "enum_type": r.enum_type.value,
                    "matched_rule": r.matched_rule,
                    "sample_values": [e.db_value for e in r.enum_values[:5]],
                }
                for r in blocking
            ],
            "pending_columns": [
                {
                    "table_name": r.table_name,
                    "column_name": r.column_name,
                    "confidence": r.confidence,
                    "confidence_level": r.confidence_level,
                    "suggested_values": [e.display_value for e in r.enum_values[:5]],
                    "source": r.source,
                }
                for r in pending
            ],
            "summary": (
                f"{len(blocking)} 个字段无法推断（阻断 SQL 生成），"
                f"{len(pending)} 个字段需确认"
            )
        }


class EnumBatchProcessor:
    """
    批次枚举推断处理器。
    
    工作流程：
    1. 接收 SchemaMeta（包含所有表/列/采样数据）
    2. 并行对每列执行推断
    3. 按表聚合结果
    4. 生成阻断报告 + 待确认队列
    5. 通知前端展示确认弹窗
    """

    def __init__(self, inference_engine: EnumInferenceEngine):
        self._engine = inference_engine

    async def process_schema(
        self,
        schema: "SchemaMeta",
        existing_mappings: dict = None,  # {(table, col): list[EnumMapping]}
    ) -> dict[str, BatchInferenceResult]:
        """
        处理整个 Schema，返回按表分组的推断结果。
        
        existing_mappings: 已有的手动映射（最高优先级）
        格式：{f"{table}.{col}": [EnumMapping(...), ...]}
        """
        existing_mappings = existing_mappings or {}

        table_results: dict[str, BatchInferenceResult] = {}

        for table in schema.tables:
            column_results = []

            for col in table.columns:
                key = f"{table.table_name}.{col.name}"
                manual = existing_mappings.get(key, [])

                result = self._engine.infer(
                    table_name=table.table_name,
                    column_name=col.name,
                    comment=col.comment,
                    sample_values=col.sample_values,
                    column_type=col.db_type,
                    existing_manual_mapping=manual,
                )
                column_results.append(result)

            batch = self._build_batch_result(table.table_name, column_results)
            table_results[table.table_name] = batch

        return table_results

    def _build_batch_result(
        self,
        table_name: str,
        column_results: list[EnumInferenceResult],
    ) -> BatchInferenceResult:
        """构建单表批次结果"""
        total = len(column_results)
        enum_cols = sum(1 for r in column_results if r.is_enum)
        confirmed = sum(1 for r in column_results if r.is_confirmed())
        pending = sum(
            1 for r in column_results
            if not r.is_confirmed() and r.confidence > 0
        )
        blocking = sum(1 for r in column_results if r.is_blocking())

        return BatchInferenceResult(
            group_id="",  # 由调用方填充
            table_name=table_name,
            column_results=column_results,
            total_columns=total,
            enum_columns=enum_cols,
            confirmed=confirmed,
            pending=pending,
            blocking=blocking,
            pending_columns=[
                f"{r.table_name}.{r.column_name}"
                for r in column_results
                if not r.is_confirmed() and r.confidence > 0
            ],
            blocking_columns=[
                f"{r.table_name}.{r.column_name}"
                for r in column_results
                if r.is_blocking()
            ],
        )


# ── 确认工作流服务 ─────────────────────────────────────────────

class EnumConfirmationService:
    """
    枚举确认工作流服务。
    
    负责：
    1. 存储待确认队列
    2. 处理用户确认/拒绝操作
    3. 生成阻断报告
    4. 向 AskService 提供已确认映射
    """

    def __init__(self, store: "EnumConfirmationStore"):
        self._store = store

    async def save_pending(
        self,
        group_id: str,
        batch_results: dict[str, BatchInferenceResult],
    ):
        """保存批次推断结果（pending 状态的列）"""
        for table_name, batch in batch_results.items():
            for result in batch.column_results:
                if not result.is_confirmed() and result.confidence > 0:
                    await self._store.save_pending(
                        group_id=group_id,
                        table_name=table_name,
                        column_name=result.column_name,
                        confidence=result.confidence,
                        confidence_level=result.confidence_level,
                        enum_type=result.enum_type.value,
                        suggested_values=[
                            {"db_value": e.db_value, "display_value": e.display_value}
                            for e in result.enum_values
                        ],
                        source=result.source,
                        matched_rule=result.matched_rule,
                    )

    async def confirm_column(
        self,
        group_id: str,
        table_name: str,
        column_name: str,
        confirmed_by: str,
        enum_values: list[dict],  # [{"db_value": "0", "display_value": "否"}, ...]
        confirmed: bool = True,
    ) -> EnumInferenceResult:
        """
        用户确认/拒绝枚举列。
        
        - confirmed=True：用户确认了建议的枚举值（可修改）
        - confirmed=False：用户明确拒绝（不是枚举列）
        
        两者都会清除 blocking 状态，允许 SQL 生成继续。
        """
        mapping = [
            EnumMapping(
                db_value=e["db_value"],
                display_value=e["display_value"],
                description="用户确认",
                source="manual",
            )
            for e in enum_values
        ]

        if confirmed:
            result = EnumInferenceResult(
                table_name=table_name,
                column_name=column_name,
                is_enum=True,
                enum_type=EnumType.TYPE_CODE,
                enum_values=mapping,
                confidence=1.0,
                confidence_level=ConfidenceLevel.HIGH,
                source="manual",
                confirmation_status="confirmed",
                confirmed_by=confirmed_by,
                confirmed_at=datetime.now(),
                final_mapping=mapping,
            )
        else:
            result = EnumInferenceResult(
                table_name=table_name,
                column_name=column_name,
                is_enum=False,
                enum_type=EnumType.UNKNOWN,
                enum_values=[],
                confidence=0.0,
                confidence_level=ConfidenceLevel.ZERO,
                source="manual",
                confirmation_status="rejected",
                confirmed_by=confirmed_by,
                confirmed_at=datetime.now(),
                final_mapping=[],
            )

        await self._store.save_confirmation(
            group_id=group_id,
            table_name=table_name,
            column_name=column_name,
            result=result,
        )

        # 清除该列的 pending 状态
        await self._store.delete_pending(
            group_id, table_name, column_name
        )

        return result

    async def get_blocking_report(self, group_id: str) -> dict:
        """获取阻断报告（哪些列阻止了 SQL 生成）"""
        pending = await self._store.get_all_pending(group_id)
        blocking = [p for p in pending if p.get("confidence_level") == ConfidenceLevel.ZERO]
        return {
            "blocking_count": len(blocking),
            "blocking_columns": blocking,
            "pending_count": len(pending) - len(blocking),
            "pending_columns": [
                p for p in pending
                if p.get("confidence_level") != ConfidenceLevel.ZERO
            ],
        }

    async def get_confirmed_mapping(
        self,
        group_id: str,
        table_name: str = None,
        column_name: str = None,
    ) -> dict:
        """
        获取已确认的枚举映射（供 AskService 使用）。
        
        返回格式：{f"{table}.{col}": [EnumMapping(...), ...]}
        """
        return await self._store.get_confirmed_mappings(
            group_id=group_id,
            table_name=table_name,
            column_name=column_name,
        )


# ── 确认存储 ─────────────────────────────────────────────────

class EnumConfirmationStore:
    """枚举确认状态存储"""

    def __init__(self, db_path: str = "./.microgenbi/enum_confirm.db"):
        import sqlite3, json
        self._con = sqlite3.connect(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        self._con.executescript("""
            CREATE TABLE IF NOT EXISTS enum_pending (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                confidence REAL,
                confidence_level TEXT,
                enum_type TEXT,
                suggested_values_json TEXT DEFAULT '[]',
                source TEXT,
                matched_rule TEXT,
                created_at TEXT NOT NULL,
                UNIQUE(group_id, table_name, column_name)
            );
            CREATE TABLE IF NOT EXISTS enum_confirmations (
                group_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                is_enum INTEGER NOT NULL,
                enum_type TEXT,
                enum_values_json TEXT DEFAULT '[]',
                confidence REAL,
                confirmation_status TEXT,
                confirmed_by TEXT,
                confirmed_at TEXT NOT NULL,
                PRIMARY KEY (group_id, table_name, column_name)
            );
        """)
        self._con.commit()

    async def save_pending(self, **kwargs):
        import json
        from datetime import datetime
        self._con.execute("""
            INSERT OR REPLACE INTO enum_pending
            (group_id, table_name, column_name, confidence, confidence_level,
             enum_type, suggested_values_json, source, matched_rule, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            kwargs["group_id"], kwargs["table_name"], kwargs["column_name"],
            kwargs["confidence"], kwargs["confidence_level"],
            kwargs.get("enum_type"), json.dumps(kwargs["suggested_values"]),
            kwargs.get("source"), kwargs.get("matched_rule"),
            datetime.now().isoformat(),
        ))
        self._con.commit()

    async def delete_pending(self, group_id, table_name, column_name):
        self._con.execute("""
            DELETE FROM enum_pending
            WHERE group_id=? AND table_name=? AND column_name=?
        """, (group_id, table_name, column_name))
        self._con.commit()

    async def get_all_pending(self, group_id) -> list[dict]:
        rows = self._con.execute("""
            SELECT * FROM enum_pending WHERE group_id=? ORDER BY confidence ASC
        """, (group_id,)).fetchall()
        cols = [d[0] for d in self._con.execute(
            "PRAGMA table_info(enum_pending)").fetchall()]
        import json
        return [
            {
                **dict(zip(cols, r)),
                "suggested_values": json.loads(r[cols.index("suggested_values_json")])
                if r[cols.index("suggested_values_json")] else []
            }
            for r in rows
        ]

    async def save_confirmation(self, group_id, table_name, column_name, result):
        import json
        from datetime import datetime
        self._con.execute("""
            INSERT OR REPLACE INTO enum_confirmations
            (group_id, table_name, column_name, is_enum, enum_type,
             enum_values_json, confidence, confirmation_status, confirmed_by, confirmed_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            group_id, table_name, column_name,
            int(result.is_enum), result.enum_type.value,
            json.dumps([e.__dict__ for e in result.enum_values]),
            result.confidence, result.confirmation_status,
            result.confirmed_by, datetime.now().isoformat(),
        ))
        self._con.commit()

    async def get_confirmed_mappings(self, group_id, table_name=None, column_name=None):
        import json
        query = "SELECT * FROM enum_confirmations WHERE group_id=? AND confirmation_status IN ('confirmed','manual')"
        params = [group_id]
        if table_name:
            query += " AND table_name=?"
            params.append(table_name)
        if column_name:
            query += " AND column_name=?"
            params.append(column_name)

        rows = self._con.execute(query, params).fetchall()
        cols = [d[0] for d in self._con.execute(
            "PRAGMA table_info(enum_confirmations)").fetchall()]

        result = {}
        for r in rows:
            key = f"{r[1]}.{r[2]}"
            vals_raw = json.loads(r[cols.index("enum_values_json")])
            result[key] = [EnumMapping(**v) for v in vals_raw]
        return result
```

### 12.5 SQL 生成阻断机制

```python
# micro_genbi/service/safe_ask_service.py

class SafeAskService:
    """
    带字段确认检查的 Ask 服务。
    
    在 SQL 生成之前，检查所有涉及的列是否已完成映射确认：
    
    流程：
    1. LLM 生成 SQL 后，解析出所有涉及的表和列
    2. 调 EnumConfirmationService 检查每列的确认状态
    3. 有阻断列 → 返回友好错误（包含阻断列清单和"去维护"链接）
    4. 无阻断列 → 执行 SQL，返回结果
    """

    def __init__(
        self,
        ask_service: "AskService",          # 原 Ask 服务
        confirmation_service: EnumConfirmationService,
    ):
        self._ask = ask_service
        self._confirm = confirmation_service

    async def ask(
        self,
        question: str,
        group_id: str,
        user_id: str,
        dialect: str = "mysql",
        **kwargs,
    ) -> dict:
        """
        安全版 ask。
        
        额外检查：
        - 生成 SQL 后，先解析涉及的所有列
        - 查每个列的确认状态
        - 有 blocking 列 → 拒绝执行，返回阻断报告
        """
        # Step 1: 先让原 AskService 生成 SQL
        # （传入 flag：不要真正执行，只返回 SQL）
        preview = await self._ask.ask(
            question=question,
            group_id=group_id,
            dialect=dialect,
            dry_run=True,   # 不执行 SQL，只返回 SQL 和涉及的列
            **kwargs,
        )

        generated_sql = preview.get("sql", "")
        involved_columns = preview.get("involved_columns", [])
        # involved_columns: [{"table": "orders", "column": "status"}, ...]

        # Step 2: 检查所有涉及的列是否有阻断
        if involved_columns:
            blocking_report = await self._check_columns(
                group_id=group_id,
                columns=involved_columns,
            )

            if blocking_report["has_blocking"]:
                # 阻断：有列未完成维护 → 返回友好错误
                return {
                    "success": False,
                    "error_type": "ENUM_MAPPING_INCOMPLETE",
                    "message": (
                        f"查询涉及 {blocking_report['blocking_count']} 个未维护字段，"
                        "无法保证 SQL 质量，请先完成字段映射。"
                    ),
                    "blocking_report": blocking_report,
                    "hint": (
                        "请前往「Schema 管理 → 字段映射」页面，"
                        "完成这些字段的枚举值维护后再试。"
                    ),
                }

        # Step 3: 无阻断，执行真实查询
        return await self._ask.ask(
            question=question,
            group_id=group_id,
            dialect=dialect,
            dry_run=False,
            **kwargs,
        )

    async def _check_columns(
        self,
        group_id: str,
        columns: list[dict],
    ) -> dict:
        """检查所有涉及列的确认状态"""
        confirmed_mappings = await self._confirm.get_confirmed_mapping(group_id)
        blocking = []
        pending = []

        for col in columns:
            key = f"{col['table']}.{col['column']}"
            mapping = confirmed_mappings.get(key, [])

            if not mapping:
                # 没有确认映射 → 检查是否为阻断
                # 尝试从已知的 high-confidence 自动确认中查找
                # （由 EnumBatchProcessor 在推断时自动标记 confirmed 的列）
                is_auto_confirmed = await self._is_auto_confirmed(
                    group_id, col["table"], col["column"]
                )
                if not is_auto_confirmed:
                    blocking.append({
                        "table": col["table"],
                        "column": col["column"],
                        "action": "前往「字段映射」页面完成维护",
                    })
                else:
                    pending.append({
                        "table": col["table"],
                        "column": col["column"],
                        "status": "auto_confirmed",
                    })

        return {
            "has_blocking": bool(blocking),
            "blocking_count": len(blocking),
            "blocking_columns": blocking,
            "pending_count": len(pending),
            "pending_columns": pending,
        }

    async def _is_auto_confirmed(
        self, group_id: str, table: str, column: str
    ) -> bool:
        """检查列是否为高置信度自动确认"""
        confirmed = await self._confirm.get_confirmed_mapping(group_id, table, column)
        key = f"{table}.{column}"
        return key in confirmed and len(confirmed[key]) > 0
```

### 12.6 前端：字段维护引导界面

```html
<!-- enum-confirmation-panel.html -->

<style>
  /* 阻断状态：红色警示 */
  .blocking-badge {
    background: #2a0a0a;
    border: 1px solid #ef4444;
    color: #ef4444;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
  }
  /* 待确认状态：黄色提示 */
  .pending-badge {
    background: #2a1f00;
    border: 1px solid #f59e0b;
    color: #f59e0b;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
  }
  /* 已确认：绿色 */
  .confirmed-badge {
    background: #0a2a0a;
    border: 1px solid #22c55e;
    color: #22c55e;
    border-radius: 6px;
    padding: 2px 8px;
    font-size: 11px;
  }
  /* 枚举值编辑行 */
  .enum-row {
    display: flex;
    align-items: center;
    gap: 12px;
    padding: 6px 0;
    border-bottom: 1px solid #222;
  }
  .enum-row input {
    background: #1a1a1a;
    border: 1px solid #333;
    border-radius: 6px;
    color: #fff;
    padding: 6px 10px;
    font-size: 13px;
    flex: 1;
  }
  .enum-row input:focus {
    border-color: #3a7bd5;
    outline: none;
  }
  .source-tag {
    font-size: 10px;
    color: #555;
    background: #111;
    padding: 2px 6px;
    border-radius: 4px;
  }
</style>

<!-- 阻断告警 Banner（任何页面均可显示） -->
<div class="blocking-banner" id="blockingBanner" style="display:none">
  <div class="banner-icon">⚠️</div>
  <div class="banner-content">
    <strong>存在未维护字段，SQL 生成已阻断</strong>
    <p id="blockingSummary">0 个字段无法推断，0 个字段待确认</p>
  </div>
  <button class="banner-action" onclick="openEnumConfirmation()">
    立即维护 →
  </button>
</div>

<!-- 枚举确认弹窗 -->
<div class="modal" id="enumConfirmModal" style="display:none">
  <div class="modal-content">
    <h2>字段枚举值维护</h2>
    <p class="modal-subtitle">
      以下字段无法自动推断，请选择或填写正确的枚举值映射。
      完成维护前，这些字段相关的 SQL 查询将被阻断。
    </p>

    <!-- 阻断列（必须维护） -->
    <div class="section blocking-section">
      <h3>⚠️ 必须维护（阻断 SQL 生成）</h3>
      <div id="blockingList"></div>
    </div>

    <!-- 待确认列（建议确认） -->
    <div class="section pending-section">
      <h3>🟡 建议确认（自动推断）</h3>
      <div id="pendingList"></div>
    </div>

    <div class="modal-footer">
      <button class="btn-secondary" onclick="closeEnumConfirmation()">稍后</button>
      <button class="btn-primary" onclick="saveEnumConfirmations()">
        保存并继续
      </button>
    </div>
  </div>
</div>

<!-- 单列枚举编辑器 -->
<div class="enum-editor">
  <div class="editor-header">
    <span class="col-name">loadOutOilMode</span>
    <span class="table-name">sys_oil_batch</span>
    <span class="blocking-badge">必须维护</span>
  </div>

  <div class="editor-meta">
    <span>推断来源：<strong>mode 后缀规则</strong></span>
    <span>置信度：<strong style="color:#ef4444">0.30（低）</strong></span>
    <span>采样值：<code>[1, 2, 3]</code></span>
  </div>

  <!-- 枚举值表格 -->
  <table class="enum-table">
    <thead>
      <tr>
        <th>数据库值</th>
        <th>中文显示</th>
        <th>来源</th>
        <th>操作</th>
      </tr>
    </thead>
    <tbody>
      <tr class="enum-row">
        <td><input value="1" readonly></td>
        <td><input value="按视体积发油" placeholder="请输入中文含义"></td>
        <td><span class="source-tag">采样推断</span></td>
        <td><button onclick="removeRow(this)">删除</button></td>
      </tr>
      <tr class="enum-row">
        <td><input value="2" readonly></td>
        <td><input value="按标准体积发油" placeholder="请输入中文含义"></td>
        <td><span class="source-tag">采样推断</span></td>
        <td><button onclick="removeRow(this)">删除</button></td>
      </tr>
      <tr class="enum-row">
        <td><input value="3" readonly></td>
        <td><input value="按重量发油" placeholder="请输入中文含义"></td>
        <td><span class="source-tag">采样推断</span></td>
        <td><button onclick="removeRow(this)">删除</button></td>
      </tr>
    </tbody>
  </table>

  <button class="btn-add" onclick="addEnumRow()">+ 添加映射值</button>
  <button class="btn-reject" onclick="rejectAsEnum()">
    这不是枚举列（标记为普通文本字段）
  </button>
</div>

<script>
// 加载阻断报告
async function loadBlockingReport(groupId) {
  const resp = await fetch(`/api/v1/groups/${groupId}/enum/blocking-report`);
  const report = await resp.json();

  if (report.blocking_count > 0 || report.pending_count > 0) {
    const banner = document.getElementById('blockingBanner');
    banner.style.display = 'flex';
    document.getElementById('blockingSummary').textContent =
      `${report.blocking_count} 个字段无法推断，${report.pending_count} 个字段待确认`;
  }
}

// 打开确认弹窗
async function openEnumConfirmation(groupId) {
  const modal = document.getElementById('enumConfirmModal');
  modal.style.display = 'flex';

  const resp = await fetch(`/api/v1/groups/${groupId}/enum/blocking-report`);
  const report = await resp.json();

  renderBlockingList(report.blocking_columns);
  renderPendingList(report.pending_columns);
}

// 渲染阻断列列表
function renderBlockingList(columns) {
  const container = document.getElementById('blockingList');
  container.innerHTML = columns.map(col => `
    <div class="enum-editor" data-table="${col.table_name}" data-column="${col.column_name}">
      <div class="editor-header">
        <span class="col-name">${col.column_name}</span>
        <span class="table-name">${col.table_name}</span>
        <span class="blocking-badge">必须维护</span>
      </div>
      <div class="editor-meta">
        <span>匹配规则：${col.matched_rule || '无'}</span>
        <span>采样值：${col.sample_values?.join(', ') || '无'}</span>
      </div>
      <div class="enum-rows">
        ${(col.suggested_values || []).map((v, i) => `
          <div class="enum-row">
            <input class="db-val" value="${v.db_value}" placeholder="数据库值">
            <input class="disp-val" value="${v.display_value}" placeholder="中文含义">
            <span class="source-tag">${col.source}</span>
            <button onclick="removeRow(this)">删除</button>
          </div>
        `).join('')}
      </div>
      <button class="btn-add" onclick="addEnumRowInEditor(this)">+ 添加</button>
      <button class="btn-reject" onclick="rejectColumn(this)">这不是枚举列</button>
    </div>
  `).join('');
}

// 提交确认
async function saveEnumConfirmations() {
  const editors = document.querySelectorAll('.enum-editor[data-table]');
  const updates = [];

  editors.forEach(editor => {
    const table = editor.dataset.table;
    const column = editor.dataset.column;
    const isRejected = editor.dataset.rejected === 'true';

    const rows = editor.querySelectorAll('.enum-row');
    const enum_values = [];

    if (!isRejected) {
      rows.forEach(row => {
        const dbVal = row.querySelector('.db-val')?.value;
        const dispVal = row.querySelector('.disp-val')?.value;
        if (dbVal && dispVal) {
          enum_values.push({ db_value: dbVal, display_value: dispVal });
        }
      });
    }

    updates.push({
      table_name: table,
      column_name: column,
      confirmed: !isRejected,
      enum_values: enum_values,
    });
  });

  await fetch('/api/v1/groups/{group_id}/enum/confirm-batch', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates }),
  });

  closeEnumConfirmation();
  location.reload();
}
</script>
```

### 12.7 REST API

```yaml
# ── 枚举推断与确认 ──────────────────────────────────────────────

GET  /api/v1/groups/{group_id}/enum/inference
     → 返回所有列的枚举推断结果

GET  /api/v1/groups/{group_id}/enum/blocking-report
     → 返回阻断报告（哪些列阻止了 SQL 生成）

GET  /api/v1/groups/{group_id}/enum/pending
     → 返回待确认队列

POST /api/v1/groups/{group_id}/enum/confirm-batch
     body: {
       "updates": [
         {
           "table_name": "sys_oil_batch",
           "column_name": "loadOutOilMode",
           "confirmed": true,
           "enum_values": [
             {"db_value": "1", "display_value": "按视体积发油"},
             {"db_value": "2", "display_value": "按标准体积发油"},
             {"db_value": "3", "display_value": "按重量发油"}
           ]
         },
         {
           "table_name": "sys_order",
           "column_name": "order_no",
           "confirmed": false
         }
       ]
     }
     → 批量确认/拒绝枚举列

# ── 规则管理 ───────────────────────────────────────────────────

GET  /api/v1/groups/{group_id}/enum/rules
     → 返回当前组的枚举推断规则列表

POST /api/v1/groups/{group_id}/enum/rules
     body: {
       "name": "oil_type后缀",
       "enum_type": "type_code",
       "match_type": "suffix",
       "pattern": "oil_type",
       "description": "油气类型枚举",
     }
     → 添加自定义规则

[SECTION 13 INSERTION POINT - TO BE REPLACED]
## 十一、Schema 管理与业务字典映射

### 11.1 整体设计

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        Schema 管理完整流程                               │
│                                                                         │
│  ┌─────────────┐    ┌──────────────────┐    ┌──────────────────────┐  │
│  │ 配置数据库   │ →  │ 自动抽取 Schema  │ →  │ 生成 ER 关系图        │  │
│  │ 连接信息    │    │ 表/列/类型/外键  │    │ 表结构可视化         │  │
│  └─────────────┘    └──────────────────┘    └──────────────────────┘  │
│                                ↓                                        │
│                    ┌──────────────────┐                                 │
│                    │ 业务字典映射      │                                 │
│                    │ · 枚举值映射      │                                 │
│                    │ · 列名中文释义    │                                 │
│                    │ · 业务规则注入    │                                 │
│                    └──────────────────┘                                 │
│                                ↓                                        │
│                    ┌──────────────────┐                                 │
│                    │ 注入 LLM Prompt  │                                 │
│                    │ 提升 SQL 生成质量 │                                 │
│                    └──────────────────┘                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 11.2 数据库连接与 Schema 自动抽取

#### 11.2.1 连接管理

```python
# micro_genbi/schema/db_connector.py

import sqlite3
import re
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

# ── 表结构元数据 ────────────────────────────────────────────────

@dataclass
class ColumnMeta:
    name: str
    data_type: str            # 原始数据库类型：varchar / int / datetime ...
    db_type: str             # 归一化类型：string / number / datetime / boolean / json
    nullable: bool
    is_primary_key: bool
    is_foreign_key: bool
    foreign_key_ref: str = ""   # "table.column" 形式
    default_value: str = ""
    comment: str = ""          # 列注释（中文释义/枚举值说明在此）
    sample_values: list = field(default_factory=list)  # 示例值（用于推断枚举）
    max_length: int = None     # 字符串最大长度
    numeric_precision: int = None
    numeric_scale: int = None

@dataclass
class TableMeta:
    table_name: str
    schema_name: str           # 数据库名（PostgreSQL schema）
    comment: str = ""         # 表注释
    columns: list[ColumnMeta] = field(default_factory=list)
    primary_key: list[str] = field(default_factory=list)  # 联合主键支持
    indexes: list[dict] = field(default_factory=list)
    row_count_estimate: int = 0  # 估算行数（用于向 LLM 说明表大小）

@dataclass
class SchemaMeta:
    group_id: str
    dialect: str               # mysql / postgresql / sqlite / mssql / clickhouse
    database_name: str
    tables: list[TableMeta] = field(default_factory=list)
    extracted_at: datetime = field(default_factory=datetime.now)
    version: int = 1          # Schema 版本号（变更时递增）

# ── 数据库连接抽象 ─────────────────────────────────────────────

class DBConnector(ABC):
    """数据库连接抽象（适配不同数据库方言）"""

    @abstractmethod
    def connect(self, config: dict) -> any: ...

    @abstractmethod
    async def introspect_tables(self) -> list[TableMeta]: ...

    @abstractmethod
    async def introspect_columns(self, table_name: str) -> list[ColumnMeta]: ...

    @abstractmethod
    async def introspect_foreign_keys(self) -> list[dict]: ...

    @abstractmethod
    async def get_table_sample(self, table_name: str, limit: int = 5) -> list[dict]: ...

    @abstractmethod
    async def get_table_row_count(self, table_name: str) -> int: ...


class MySQLConnector(DBConnector):
    """MySQL Schema 抽取"""

    async def introspect_tables(self) -> list[TableMeta]:
        rows = await self._fetchall("""
            SELECT TABLE_NAME, TABLE_COMMENT, TABLE_ROWS, DATA_LENGTH
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = %s AND TABLE_TYPE = 'BASE TABLE'
        """, (self._database,))

        return [
            TableMeta(
                table_name=r["TABLE_NAME"],
                schema_name=self._database,
                comment=r["TABLE_COMMENT"] or "",
                row_count_estimate=r["TABLE_ROWS"] or 0,
            )
            for r in rows
        ]

    async def introspect_columns(self, table_name: str) -> list[ColumnMeta]:
        rows = await self._fetchall("""
            SELECT
                COLUMN_NAME, DATA_TYPE, COLUMN_TYPE,
                IS_NULLABLE, COLUMN_KEY, COLUMN_COMMENT,
                COLUMN_DEFAULT, CHARACTER_MAXIMUM_LENGTH,
                NUMERIC_PRECISION, NUMERIC_SCALE, EXTRA
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
            ORDER BY ORDINAL_POSITION
        """, (self._database, table_name))

        # 批量获取外键
        fks = await self._fetchall("""
            SELECT COLUMN_NAME, REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s AND TABLE_NAME = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (self._database, table_name))
        fk_map = {r["COLUMN_NAME"]: f"{r['REFERENCED_TABLE_NAME']}.{r['REFERENCED_COLUMN_NAME']}"
                   for r in fks}

        # 批量获取示例值（用于枚举推断）
        samples = await self._get_column_samples(table_name, [r["COLUMN_NAME"] for r in rows])

        return [
            ColumnMeta(
                name=r["COLUMN_NAME"],
                data_type=r["DATA_TYPE"],
                db_type=self._normalize_type(r["DATA_TYPE"], r["COLUMN_TYPE"]),
                nullable=(r["IS_NULLABLE"] == "YES"),
                is_primary_key=(r["COLUMN_KEY"] == "PRI"),
                is_foreign_key=(r["COLUMN_NAME"] in fk_map),
                foreign_key_ref=fk_map.get(r["COLUMN_NAME"], ""),
                default_value=r["COLUMN_DEFAULT"] or "",
                comment=r["COLUMN_COMMENT"] or "",
                sample_values=samples.get(r["COLUMN_NAME"], []),
                max_length=r["CHARACTER_MAXIMUM_LENGTH"],
                numeric_precision=r["NUMERIC_PRECISION"],
                numeric_scale=r["NUMERIC_SCALE"],
            )
            for r in rows
        ]

    async def introspect_foreign_keys(self) -> list[dict]:
        rows = await self._fetchall("""
            SELECT
                TABLE_NAME, COLUMN_NAME,
                REFERENCED_TABLE_NAME, REFERENCED_COLUMN_NAME,
                CONSTRAINT_NAME
            FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
            WHERE TABLE_SCHEMA = %s
              AND REFERENCED_TABLE_NAME IS NOT NULL
        """, (self._database,))
        return list(rows)

    async def get_table_sample(
        self, table_name: str, limit: int = 5
    ) -> list[dict]:
        sql = f"SELECT * FROM `{table_name}` LIMIT {limit}"
        return await self._fetchall(sql)

    async def get_table_row_count(self, table_name: str) -> int:
        rows = await self._fetchall(
            f"SELECT COUNT(*) as cnt FROM `{table_name}`"
        )
        return rows[0]["cnt"] if rows else 0

    def _normalize_type(self, data_type: str, column_type: str) -> str:
        """将数据库类型归一化为统一类型"""
        dt = data_type.lower()
        if dt in ("varchar", "char", "text", "longtext", "mediumtext",
                   "tinytext", "nchar", "nvarchar"):
            return "string"
        if dt in ("int", "bigint", "smallint", "tinyint",
                   "mediumint", "integer"):
            return "number"
        if dt in ("decimal", "numeric", "float", "double", "real"):
            return "decimal"
        if dt in ("datetime", "timestamp", "date", "time", "year"):
            return "datetime"
        if dt in ("bit", "bool", "boolean"):
            return "boolean"
        if dt in ("json",):
            return "json"
        if dt in ("blob", "mediumblob", "longblob", "binary", "varbinary"):
            return "binary"
        return "string"


class PostgreSQLConnector(DBConnector):
    """PostgreSQL Schema 抽取"""

    async def introspect_tables(self) -> list[TableMeta]:
        rows = await self._fetchall("""
            SELECT t.table_name,
                   COALESCE(obj_description(c.oid), '') as comment,
                   (SELECT reltuples FROM pg_class WHERE relname = t.table_name)::bigint as row_count
            FROM information_schema.tables t
            JOIN pg_class c ON c.relname = t.table_name
            WHERE t.table_schema = 'public' AND t.table_type = 'BASE TABLE'
        """)
        return [
            TableMeta(
                table_name=r["table_name"],
                schema_name="public",
                comment=r["comment"] or "",
                row_count_estimate=r["row_count"] or 0,
            )
            for r in rows
        ]

    async def introspect_columns(self, table_name: str) -> list[ColumnMeta]:
        rows = await self._fetchall("""
            SELECT
                c.column_name, c.data_type, c.udt_name,
                c.is_nullable, c.column_default, c.character_maximum_length,
                c.numeric_precision, c.numeric_scale,
                col_description((c.table_schema||'.'||c.table_name)::regclass, c.ordinal_position) as comment,
                CASE WHEN pk.column_name IS NOT NULL THEN TRUE ELSE FALSE END as is_primary_key,
                fk.foreign_key_ref
            FROM information_schema.columns c
            LEFT JOIN LATERAL (
                SELECT column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                WHERE tc.table_name = c.table_name
                  AND tc.constraint_type = 'PRIMARY KEY'
                  AND kcu.column_name = c.column_name
            ) pk ON TRUE
            LEFT JOIN LATERAL (
                SELECT conname, gen_random_uuid() as ref
                FROM pg_constraint con
                JOIN pg_class cl ON con.confrelid = cl.oid
                JOIN pg_namespace ns ON cl.relnamespace = ns.oid
                JOIN pg_attribute a ON a.attrelid = con.conrelid
                WHERE con.conrelid = (c.table_schema||'.'||c.table_name)::regclass::oid
                  AND a.attnum = ANY(con.conkey)
                  AND a.attname = c.column_name
                  AND con.contype = 'f'
            ) fk ON TRUE
            WHERE c.table_name = %s AND c.table_schema = 'public'
            ORDER BY c.ordinal_position
        """, (table_name,))
        return [
            ColumnMeta(
                name=r["column_name"],
                data_type=r["data_type"],
                db_type=self._normalize_pg_type(r["udt_name"]),
                nullable=(r["is_nullable"] == "YES"),
                is_primary_key=bool(r["is_primary_key"]),
                is_foreign_key=bool(r.get("foreign_key_ref")),
                comment=r["comment"] or "",
                max_length=r["character_maximum_length"],
                numeric_precision=r["numeric_precision"],
                numeric_scale=r["numeric_scale"],
            )
            for r in rows
        ]

    def _normalize_pg_type(self, udt: str) -> str:
        pg_type_map = {
            "varchar": "string", "text": "string", "char": "string",
            "bpchar": "string",
            "int4": "number", "int8": "number", "int2": "number",
            "numeric": "decimal", "float4": "decimal", "float8": "decimal",
            "bool": "boolean",
            "timestamp": "datetime", "timestamptz": "datetime",
            "date": "datetime", "time": "datetime",
            "jsonb": "json", "json": "json",
            "bytea": "binary",
        }
        return pg_type_map.get(udt.lower(), "string")


# ── Schema 抽取服务 ────────────────────────────────────────────

class SchemaIntrospector:
    """
    Schema 自动抽取服务。
    
    工作流程：
    1. 连接数据库（根据方言选择 Connector）
    2. 遍历所有表，抽取列信息
    3. 抽取外键关系
    4. 采样数据（用于枚举值推断）
    5. 生成统一 SchemaMeta
    """

    CONNECTOR_MAP = {
        "mysql": MySQLConnector,
        "mariadb": MySQLConnector,
        "postgresql": PostgreSQLConnector,
        "sqlite": SQLiteConnector,     # 实现省略（结构类似）
        "mssql": MsSQLConnector,       # 实现省略
    }

    def __init__(self, db_config: dict):
        self._config = db_config
        dialect = db_config.get("dialect", "mysql")
        connector_cls = self.CONNECTOR_MAP.get(dialect, MySQLConnector)
        self._conn = connector_cls()
        self._conn.connect(db_config)

    async def extract_full_schema(self, group_id: str) -> SchemaMeta:
        """抽取完整 Schema"""
        logger.info(f"Starting schema introspection for group {group_id}")

        # 1. 抽取所有表
        tables = await self._conn.introspect_tables()

        # 2. 并行抽取每个表的列信息
        import asyncio
        table_tasks = [
            self._extract_table_detail(t)
            for t in tables
        ]
        tables = await asyncio.gather(*table_tasks)

        # 3. 抽取外键关系
        foreign_keys = await self._conn.introspect_foreign_keys()

        # 4. 构建 SchemaMeta
        schema = SchemaMeta(
            group_id=group_id,
            dialect=self._config.get("dialect", "mysql"),
            database_name=self._config.get("database", ""),
            tables=tables,
        )

        # 5. 建立外键关联
        self._link_foreign_keys(schema, foreign_keys)

        logger.info(f"Schema introspection complete: {len(schema.tables)} tables")
        return schema

    async def _extract_table_detail(self, table: TableMeta) -> TableMeta:
        """抽取单个表的详细信息"""
        columns = await self._conn.introspect_columns(table.table_name)
        table.columns = columns

        # 获取主键
        pk_cols = [c.name for c in columns if c.is_primary_key]
        table.primary_key = pk_cols

        # 采样数据（用于枚举推断）
        sample_rows = await self._conn.get_table_sample(table.table_name)
        for row in sample_rows:
            for col in columns:
                val = row.get(col.name)
                if val is not None and col.db_type in ("string", "number"):
                    if len(col.sample_values) < 10:
                        col.sample_values.append(str(val))

        # 估算行数
        table.row_count_estimate = await self._conn.get_table_row_count(table.table_name)

        return table

    def _link_foreign_keys(self, schema: SchemaMeta, fks: list[dict]):
        """建立外键引用关系"""
        table_map = {t.table_name: t for t in schema.tables}
        for fk in fks:
            src_table = table_map.get(fk.get("TABLE_NAME"))
            if not src_table:
                continue
            for col in src_table.columns:
                if col.name == fk.get("COLUMN_NAME"):
                    col.is_foreign_key = True
                    col.foreign_key_ref = (
                        f"{fk.get('REFERENCED_TABLE_NAME')}."
                        f"{fk.get('REFERENCED_COLUMN_NAME')}"
                    )
```

### 11.3 ER 关系图生成

**设计思路**：Schema 抽取完成后，自动生成可视化的 ER 关系图，帮助用户理解表结构。

```python
# micro_genbi/schema/er_diagram.py

import json
import re
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

# ── ER 图数据模型 ──────────────────────────────────────────────

@dataclass
class ERNode:
    """ER 图中的节点（表）"""
    id: str                # 节点唯一 ID（用于前端渲染）
    table_name: str
    label: str             # 显示名称（优先用表注释）
    comment: str           # 表注释
    column_count: int
    row_count: int         # 估算行数
    columns: list[dict]    # 列信息摘要
    position: dict = field(default_factory=lambda: {"x": 0, "y": 0})  # 布局位置

@dataclass
class EREdge:
    """ER 图中的边（外键关系）"""
    id: str
    source: str            # 源表节点 ID
    target: str            # 目标表节点 ID
    source_col: str        # 源列
    target_col: str        # 目标列
    label: str             # 显示标签

# ── Mermaid 格式生成 ────────────────────────────────────────────

class ERDiagramGenerator:
    """
    ER 关系图生成器。
    
    支持输出格式：
    - Mermaid（用于文档 / 前端渲染）
    - Graphviz DOT（用于图片导出）
    - JSON（用于前端自定义渲染，如 D3.js / AntV G6）
    """

    def to_mermaid(self, schema: "SchemaMeta") -> str:
        """
        生成 Mermaid ER 图格式。
        
        使用方法：
        1. 在前端 <div class="mermaid"> 标签中渲染
        2. 或在 Markdown 中直接嵌入
        """
        lines = ["erDiagram"]

        for table in schema.tables:
            # 表定义行
            table_label = self._escape_mermaid(table.comment or table.table_name)
            lines.append(f"    {table.table_name} {{")

            # 列定义
            for col in table.columns:
                col_type = self._map_type_to_mermaid(col.db_type)
                # 构建列注释（包含枚举值提示）
                col_desc = self._build_column_desc(col)
                lines.append(f"        {col_type} {col.name} \"{col_desc}\"")

            lines.append("    }")

        # 外键关系
        for table in schema.tables:
            for col in table.columns:
                if col.is_foreign_key and col.foreign_key_ref:
                    ref_table, ref_col = col.foreign_key_ref.split(".", 1)
                    lines.append(
                        f"    {table.table_name} ||--o{{ {ref_table} : "
                        f"{col.name} → {ref_col}"
                    )

        return "\n".join(lines)

    def to_json(self, schema: "SchemaMeta") -> dict:
        """生成前端渲染用的 JSON 格式"""
        nodes = []
        edges = []
        edge_id = 0

        # 自动布局（简单网格布局）
        cols = 3
        for i, table in enumerate(schema.tables):
            x = (i % cols) * 400
            y = (i // cols) * 500

            nodes.append(ERNode(
                id=table.table_name,
                table_name=table.table_name,
                label=table.comment or table.table_name,
                comment=table.comment,
                column_count=len(table.columns),
                row_count=table.row_count_estimate,
                columns=[
                    {
                        "name": c.name,
                        "type": c.db_type,
                        "isPK": c.is_primary_key,
                        "isFK": c.is_foreign_key,
                        "comment": c.comment,
                        "isEnum": bool(self._parse_enum_values(c.comment)),
                    }
                    for c in table.columns
                ],
                position={"x": x, "y": y},
            ))

        # 生成边
        seen_edges = set()
        for table in schema.tables:
            for col in table.columns:
                if col.is_foreign_key and col.foreign_key_ref:
                    ref_table, ref_col = col.foreign_key_ref.split(".", 1)
                    edge_key = (table.table_name, ref_table)
                    if edge_key in seen_edges:
                        continue
                    seen_edges.add(edge_key)
                    edges.append(EREdge(
                        id=f"edge_{edge_id}",
                        source=table.table_name,
                        target=ref_table,
                        source_col=col.name,
                        target_col=ref_col,
                        label=f"{col.name} → {ref_col}",
                    ))
                    edge_id += 1

        return {
            "nodes": [n.__dict__ for n in nodes],
            "edges": [e.__dict__ for e in edges],
            "stats": {
                "table_count": len(nodes),
                "relationship_count": len(edges),
                "dialect": schema.dialect,
                "extracted_at": schema.extracted_at.isoformat(),
            }
        }

    def to_graphviz_dot(self, schema: "SchemaMeta") -> str:
        """生成 Graphviz DOT 格式（用于导出 PNG/SVG）"""
        lines = [
            "digraph ER {",
            "  rankdir=LR;",
            "  node [shape=box, style=filled, fillcolor=lightblue];",
            "  edge [arrowhead=none];",
            "",
        ]

        for table in schema.tables:
            lines.append(f'  "{table.table_name}" [label="{table.table_name}\\n({len(table.columns)} 列)"];')

        for table in schema.tables:
            for col in table.columns:
                if col.is_foreign_key and col.foreign_key_ref:
                    ref_table, _ = col.foreign_key_ref.split(".", 1)
                    lines.append(f'  "{table.table_name}" -> "{ref_table}" [label="{col.name}"];')

        lines.append("}")
        return "\n".join(lines)

    @staticmethod
    def _escape_mermaid(text: str) -> str:
        """Mermaid 特殊字符转义"""
        return text.replace('"', "'").replace("\\", "\\\\")

    @staticmethod
    def _map_type_to_mermaid(db_type: str) -> str:
        type_map = {
            "string": "string", "number": "int", "decimal": "decimal",
            "datetime": "datetime", "boolean": "boolean", "json": "json",
        }
        return type_map.get(db_type, "string")

    @staticmethod
    def _build_column_desc(col: "ColumnMeta") -> str:
        """构建列的描述（包含枚举值提示）"""
        parts = []
        if col.comment:
            parts.append(col.comment)
        if col.is_primary_key:
            parts.append("PK")
        if col.is_foreign_key:
            parts.append(f"FK→{col.foreign_key_ref}")
        if col.db_type == "boolean":
            enum_vals = ERDiagramGenerator._parse_enum_values(col.comment)
            if enum_vals:
                parts.append(f"枚举: {enum_vals}")
        return " | ".join(parts)

    @staticmethod
    def _parse_enum_values(comment: str) -> Optional[list[str]]:
        """从列注释中解析枚举值说明"""
        if not comment:
            return None
        # 匹配模式：
        # - "状态: 0=未开始,1=进行中,2=已完成"
        # - "性别: 0-女,1-男"
        # - "状态 (0=否 1=是)"
        patterns = [
            r"[\(（\[]([\d\w\u4e00-\u9fa5]+[=：:][^（）()\[\],，\n]+)[\)）\]]",
            r"([\d\w\u4e00-\u9fa5]+)\s*[=:：]\s*([\d\w\u4e00-\u9fa5]+(?:\s*[,，]\s*[\d\w\u4e00-\u9fa5]+\s*[=:：]\s*[\d\w\u4e00-\u9fa5]+)*)",
        ]
        for p in patterns:
            m = re.search(p, comment)
            if m:
                # 简单解析 "0=否,1=是" → ["0=否", "1=是"]
                raw = m.group(1)
                items = re.split(r"[,，\s]+", raw)
                return [it.strip() for it in items if "=" in it or "：" in it]
        return None
```

### 11.4 业务字典与枚举值映射

**核心设计**：枚举值的来源优先级：`列注释 > 用户手动维护 > 自动推断`

```
┌──────────────────────────────────────────────────────────────────┐
│                 业务字典映射完整流程                               │
│                                                                  │
│  Step 1: 自动从列注释解析枚举值                                    │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 注释: "状态(0=未开始,1=进行中,2=已完成)"                   │  │
│  │ → 解析为: {"0": "未开始", "1": "进行中", "2": "已完成"}   │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  Step 2: 自动从数据采样推断枚举值                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ SELECT DISTINCT status FROM orders LIMIT 20;               │  │
│  │ → ["pending", "processing", "completed", "cancelled"]     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  Step 3: 用户手动维护（修正/补充）                                 │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ 前端可视化界面：                                            │  │
│  │ 表名.列名: status                                          │  │
│  │ 映射值: 0→未开始  1→进行中  2→已完成  3→已取消 (手动)     │  │
│  └────────────────────────────────────────────────────────────┘  │
│                              ↓                                     │
│  Step 4: 业务字典注入 LLM Prompt                                  │
│  ┌────────────────────────────────────────────────────────────┐  │
│  │ WHERE status = '1'  → WHERE status = '进行中'              │  │
│  │ LLM 生成: WHERE status = 1 (自动映射)                      │  │
│  └────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

```python
# micro_genbi/schema/business_dictionary.py

import json
import re
import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum

logger = logging.getLogger(__name__)

# ── 枚举映射模型 ────────────────────────────────────────────────

@dataclass
class EnumMapping:
    """单个枚举值映射"""
    db_value: str           # 数据库中的原始值："0" / "1" / "Y" / "N"
    display_value: str      # 展示/中文值："否" / "是" / "未开始"
    description: str = ""   # 描述

@dataclass
class ColumnMapping:
    """列的业务映射"""
    table_name: str
    column_name: str
    display_name: str       # 列的中文名称（从注释提取或手动维护）

    # 枚举值映射（数值 → 中文）
    enum_values: list[EnumMapping] = field(default_factory=list)

    # 是否为枚举列
    is_enum: bool = False

    # 来源优先级
    source: str = "auto"   # "comment" / "sample" / "manual"

    # 版本控制
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""


@dataclass
class TableMapping:
    """表的业务映射"""
    table_name: str
    display_name: str       # 表的中文名
    description: str = ""    # 表的描述
    columns: list[ColumnMapping] = field(default_factory=list)


@dataclass
class BusinessDictionary:
    """业务字典（一个 Group 共享一份）"""
    group_id: str
    dialect: str
    tables: list[TableMapping] = field(default_factory=list)
    version: int = 1
    updated_at: datetime = field(default_factory=datetime.now)
    updated_by: str = ""


# ── 枚举值解析器 ────────────────────────────────────────────────

class EnumValueParser:
    """
    从列注释中自动解析枚举值映射。
    
    支持的注释格式：
    1. "状态(0=未开始,1=进行中,2=已完成)"
    2. "性别: 0-女,1-男"
    3. "是否(0=否 1=是)"
    4. "订单状态: pending=待支付,processing=处理中,completed=已完成"
    5. "开关状态 0=关闭 1=开启"
    """

    # 正则模式（从注释中匹配枚举值说明）
    ENUM_PATTERNS = [
        # 模式1: 括号内 "0=未开始,1=进行中"
        (r"[（(](\d+\s*[=:]\s*[^，,()（）\n]+(?:\s*[，,]\s*\d+\s*[=:]\s*[^，,()（）\n]+)+)[）)]", 1),
        # 模式2: 冒号后 "状态: 0=未开始,1=进行中"
        (r"[：:]\s*(\d+\s*[=:]\s*[^\s，,]+(?:\s*[，,]\s*\d+\s*[=:]\s*[^\s，,]+)+)", 1),
        # 模式3: 分散形式 "0=否 1=是"
        (r"(\d+\s*[=:]\s*[^\s]+(?:\s+\d+\s*[=:]\s*[^\s]+){1,5})", 1),
        # 模式4: 英文枚举 "0=No,1=Yes"
        (r"([A-Za-z0-9_-]+\s*[=:]\s*[^\s，,]+(?:\s*[，,]\s*[A-Za-z0-9_-]+\s*[=:]\s*[^\s，,]+)+)", 1),
    ]

    def parse_from_comment(self, comment: str) -> list[EnumMapping]:
        """从列注释解析枚举值"""
        if not comment:
            return []

        for pattern, group_idx in self.ENUM_PATTERNS:
            match = re.search(pattern, comment)
            if not match:
                continue

            raw = match.group(group_idx).strip()
            mappings = self._parse_kv_pairs(raw)
            if mappings:
                return [
                    EnumMapping(
                        db_value=k.strip(),
                        display_value=v.strip(),
                        description=comment,
                    )
                    for k, v in mappings
                ]

        return []

    def _parse_kv_pairs(self, raw: str) -> list[tuple[str, str]]:
        """解析键值对字符串"""
        # 先尝试按逗号/中文逗号分割
        parts = re.split(r"[，,]\s*", raw)
        if len(parts) < 2:
            # 按空格分割
            parts = raw.split()

        pairs = []
        for part in parts:
            part = part.strip()
            if not part:
                continue
            # 匹配 key=value 或 key:value 形式
            m = re.match(r"^([^\s=:：]+)\s*[=:：]\s*(.+)$", part)
            if m:
                pairs.append((m.group(1), m.group(2)))
            else:
                # 纯数值/文本，无映射关系
                pairs.append((part, part))

        return pairs

    def infer_from_sample(
        self,
        sample_values: list[str],
        column_name: str,
        comment: str = "",
    ) -> list[EnumMapping]:
        """
        从数据采样推断枚举值。
        
        推断条件：
        1. 不同值数量 <= 20（防止高基数列误判为枚举）
        2. 列名包含枚举特征词（status/type/state/kind/category）
        3. 值多为短文本（<= 30 字符）
        """
        if not sample_values:
            return []

        unique_vals = list(set(str(v) for v in sample_values))
        if len(unique_vals) > 20:
            return []

        # 检查列名是否具有枚举特征
        enum_indicators = ["status", "type", "state", "kind", "category",
                           "flag", "mode", "level", "priority", "state"]
        col_lower = column_name.lower()
        is_likely_enum = any(ind in col_lower for ind in enum_indicators)

        # 高基数列，即使列名有特征也不推断
        if not is_likely_enum and len(unique_vals) > 10:
            return []

        return [
            EnumMapping(db_value=v, display_value=v, description="自动推断")
            for v in unique_vals
        ]


# ── 业务字典服务 ────────────────────────────────────────────────

class BusinessDictionaryService:
    """
    业务字典服务。
    
    工作流程：
    1. 根据 SchemaMeta 自动构建字典
    2. 优先级：注释解析 > 采样推断 > 空
    3. 用户可在前端手动修正/补充
    4. 字典变更版本递增
    """

    def __init__(self, store: "BusinessDictionaryStore"):
        self._store = store
        self._parser = EnumValueParser()

    async def build_from_schema(
        self,
        schema: "SchemaMeta",
        updated_by: str = "system",
    ) -> BusinessDictionary:
        """
        从 SchemaMeta 自动构建业务字典。
        
        对每个列：
        1. 从 comment 解析枚举值
        2. 从 sample_values 推断枚举值
        3. 合并（comment 优先）
        """
        tables = []

        for table in schema.tables:
            columns = []

            for col in table.columns:
                # 从注释解析
                enum_from_comment = self._parser.parse_from_comment(col.comment)

                # 从采样推断
                enum_from_sample = []
                if not enum_from_comment:
                    enum_from_sample = self._parser.infer_from_sample(
                        col.sample_values, col.name, col.comment
                    )

                # 选择枚举值来源
                if enum_from_comment:
                    enum_values = enum_from_comment
                    source = "comment"
                elif enum_from_sample:
                    enum_values = enum_from_sample
                    source = "sample"
                else:
                    enum_values = []
                    source = "none"

                # 从注释提取列的中文名称
                display_name = self._extract_display_name(col.comment, col.name)

                columns.append(ColumnMapping(
                    table_name=table.table_name,
                    column_name=col.name,
                    display_name=display_name,
                    enum_values=enum_values,
                    is_enum=bool(enum_values),
                    source=source,
                ))

            tables.append(TableMapping(
                table_name=table.table_name,
                display_name=self._extract_display_name(table.comment, table.table_name),
                description=table.comment,
                columns=columns,
            ))

        dictionary = BusinessDictionary(
            group_id=schema.group_id,
            dialect=schema.dialect,
            tables=tables,
            version=1,
            updated_by=updated_by,
        )

        # 持久化
        await self._store.save(dictionary)

        logger.info(
            f"Business dictionary built for group {schema.group_id}: "
            f"{len(tables)} tables, "
            f"{sum(1 for t in tables for c in t.columns if c.is_enum)} enum columns"
        )
        return dictionary

    async def update_column_mapping(
        self,
        group_id: str,
        table_name: str,
        column_name: str,
        display_name: str = None,
        enum_values: list[dict] = None,
    ) -> ColumnMapping:
        """
        手动更新列映射（用户修正/补充枚举值）。
        设置 source = "manual"。
        """
        mapping = await self._store.get_column_mapping(
            group_id, table_name, column_name
        )
        if not mapping:
            raise ValueError(f"Mapping not found: {table_name}.{column_name}")

        if display_name is not None:
            mapping.display_name = display_name

        if enum_values is not None:
            mapping.enum_values = [
                EnumMapping(
                    db_value=e.get("db_value", ""),
                    display_value=e.get("display_value", ""),
                    description=e.get("description", "手动维护"),
                )
                for e in enum_values
            ]
            mapping.is_enum = True

        mapping.source = "manual"
        mapping.updated_at = datetime.now()

        await self._store.save_column_mapping(mapping)
        await self._store.increment_version(group_id)

        return mapping

    def to_llm_context(self, dictionary: BusinessDictionary) -> str:
        """
        将业务字典转换为 LLM Prompt 上下文。
        
        输出格式示例：
        '''
        ## 业务字典
        表 orders（订单）:
          - status: 订单状态 [枚举值: 0=待支付, 1=处理中, 2=已完成, 3=已取消]
          - payment_method: 支付方式 [枚举值: alipay=支付宝, wxpay=微信支付, bank=银行转账]
        
        表 customers（客户）:
          - gender: 性别 [枚举值: 0=女, 1=男]
          - vip_level: VIP等级 [枚举值: 0=普通, 1=银卡, 2=金卡, 3=钻石]
        '''
        """
        lines = ["## 业务字典（枚举值映射）"]

        for table in dictionary.tables:
            enum_cols = [c for c in table.columns if c.is_enum]
            if not enum_cols:
                continue

            table_header = (
                f"表 {table.table_name}"
                + (f"（{table.display_name}）" if table.display_name != table.table_name else "")
                + (f": {table.description}" if table.description else "")
            )
            lines.append(table_header)

            for col in enum_cols:
                enum_str = ", ".join(
                    f"{e.db_value}={e.display_value}" for e in col.enum_values
                )
                lines.append(
                    f"  - {col.column_name}"
                    + (f"（{col.display_name}）" if col.display_name else "")
                    + f": [{enum_str}]"
                )

        return "\n".join(lines)

    def translate_enum_value(
        self,
        dictionary: BusinessDictionary,
        table_name: str,
        column_name: str,
        db_value: str,
        reverse: bool = False,
    ) -> Optional[str]:
        """
        枚举值翻译。
        
        - reverse=False: 数据库值 → 中文显示值
          translate_enum_value(dict, "orders", "status", "1") → "进行中"
        - reverse=True: 中文显示值 → 数据库值
          translate_enum_value(dict, "orders", "status", "进行中", reverse=True) → "1"
        """
        for table in dictionary.tables:
            if table.table_name != table_name:
                continue
            for col in table.columns:
                if col.column_name != column_name:
                    continue
                for e in col.enum_values:
                    if not reverse and e.db_value == db_value:
                        return e.display_value
                    if reverse and e.display_value == db_value:
                        return e.db_value
        return None

    @staticmethod
    def _extract_display_name(comment: str, fallback: str) -> str:
        """从注释中提取中文名称（取第一个分句）"""
        if not comment:
            return fallback
        # 取第一个分句（到逗号/冒号/括号前）
        m = re.match(r"^([^（(,，:：\n]+)", comment.strip())
        return m.group(1).strip() if m else fallback
```

### 11.5 Schema 与字典的存储

```python
# micro_genbi/schema/dictionary_store.py

import sqlite3
import json
import logging
from typing import Optional
from datetime import datetime

logger = logging.getLogger(__name__)

class BusinessDictionaryStore:
    """业务字典持久化存储"""

    def __init__(self, db_path: str = "./.microgenbi/schema.db"):
        self._db_path = db_path
        self._con = sqlite3.connect(db_path)
        self._ensure_tables()

    def _ensure_tables(self):
        self._con.executescript("""
            CREATE TABLE IF NOT EXISTS business_dictionaries (
                group_id TEXT NOT NULL,
                dialect TEXT NOT NULL,
                version INTEGER DEFAULT 1,
                updated_at TEXT NOT NULL,
                updated_by TEXT DEFAULT 'system',
                tables_json TEXT NOT NULL,
                PRIMARY KEY (group_id)
            );

            CREATE TABLE IF NOT EXISTS column_mappings (
                group_id TEXT NOT NULL,
                table_name TEXT NOT NULL,
                column_name TEXT NOT NULL,
                display_name TEXT DEFAULT '',
                is_enum INTEGER DEFAULT 0,
                enum_values_json TEXT DEFAULT '[]',
                source TEXT DEFAULT 'none',
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                updated_by TEXT DEFAULT '',
                PRIMARY KEY (group_id, table_name, column_name)
            );
        """)
        self._con.commit()

    async def save(self, dictionary: "BusinessDictionary"):
        self._con.execute("""
            INSERT OR REPLACE INTO business_dictionaries
            (group_id, dialect, version, updated_at, updated_by, tables_json)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            dictionary.group_id, dictionary.dialect,
            dictionary.version, datetime.now().isoformat(),
            dictionary.updated_by,
            json.dumps([t.__dict__ for t in dictionary.tables], ensure_ascii=False),
        ))
        self._con.commit()

    async def get(self, group_id: str) -> Optional["BusinessDictionary"]:
        row = self._con.execute(
            "SELECT * FROM business_dictionaries WHERE group_id = ?",
            (group_id,)
        ).fetchone()
        if not row:
            return None
        # 反序列化（略）
        return None  # placeholder

    async def save_column_mapping(self, mapping: "ColumnMapping"):
        self._con.execute("""
            INSERT OR REPLACE INTO column_mappings
            (group_id, table_name, column_name, display_name,
             is_enum, enum_values_json, source, created_at, updated_at, updated_by)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            mapping.table_name, mapping.column_name, mapping.display_name,
            int(mapping.is_enum),
            json.dumps([e.__dict__ for e in mapping.enum_values]),
            mapping.source,
            mapping.created_at.isoformat(), mapping.updated_at.isoformat(),
            mapping.updated_by,
        ))
        self._con.commit()

    async def get_column_mapping(
        self, group_id: str, table_name: str, column_name: str
    ) -> Optional["ColumnMapping"]:
        row = self._con.execute("""
            SELECT * FROM column_mappings
            WHERE group_id=? AND table_name=? AND column_name=?
        """, (group_id, table_name, column_name)).fetchone()
        if not row:
            return None
        # 反序列化（略）
        return None

    async def increment_version(self, group_id: str):
        self._con.execute(
            "UPDATE business_dictionaries SET version = version + 1 "
            "WHERE group_id = ?", (group_id,)
        )
        self._con.commit()
```

### 11.6 Schema 注入 LLM Prompt 的完整流程

```python
# micro_genbi/service/ask_service.py  （Schema 注入部分）

class SchemaInjectedAskService:
    """
    集成了 Schema + 业务字典的 Ask 服务。
    
    Prompt 注入顺序（Context Hygiene 原则）：
    1. 静态部分（最稳定）：DDL（表结构）+ System Prompt
    2. 半静态（可变更）：业务字典（枚举值）
    3. 动态（每次不同）：用户问题 + 对话历史
    """

    def __init__(
        self,
        schema_introspector: SchemaIntrospector,
        dictionary_service: BusinessDictionaryService,
        dictionary_store: BusinessDictionaryStore,
        group_cache: "GroupCache",
    ):
        self._schema = schema_introspector
        self._dict_svc = dictionary_service
        self._dict_store = dictionary_store
        self._cache = group_cache

    async def build_llm_context(
        self,
        group_id: str,
        schema_meta: "SchemaMeta",
    ) -> str:
        """
        构建完整的 LLM 上下文。
        
        格式示例：
        '''
        ## 数据库信息
        方言: MySQL 8.0
        
        ## 表结构（DDL）
        CREATE TABLE orders (...);
        CREATE TABLE customers (...);
        
        ## 业务字典
        - orders.status: 0=待支付, 1=处理中, 2=已完成
        - customers.gender: 0=女, 1=男
        
        ## 外键关系
        orders.customer_id → customers.id（客户）
        orders.product_id → products.id（商品）
        '''
        """
        ctx_parts = []

        # 1. 数据库基本信息
        ctx_parts.append(f"## 数据库信息\n方言: {schema_meta.dialect.upper()}")

        # 2. 表结构（DDL）
        ctx_parts.append("\n## 表结构（DDL）")
        for table in schema_meta.tables:
            ddl = self._generate_ddl(table)
            ctx_parts.append(ddl)

        # 3. 业务字典（枚举值）
        dictionary = await self._dict_store.get(group_id)
        if dictionary:
            dict_ctx = self._dict_svc.to_llm_context(dictionary)
            ctx_parts.append(f"\n{dict_ctx}")

        # 4. 外键关系
        ctx_parts.append("\n## 外键关系")
        fk_relations = []
        for table in schema_meta.tables:
            for col in table.columns:
                if col.is_foreign_key and col.foreign_key_ref:
                    ref_table, ref_col = col.foreign_key_ref.split(".", 1)
                    # 尝试获取关联表的中文名
                    ref_table_name = self._get_table_display_name(dictionary, ref_table)
                    fk_relations.append(
                        f"- {table.table_name}.{col.name} → "
                        f"{ref_table}({ref_table_name}).{ref_col}"
                    )
        ctx_parts.append("\n".join(fk_relations) if fk_relations else "（无外键关系）")

        return "\n\n".join(ctx_parts)

    def _generate_ddl(self, table: "TableMeta") -> str:
        """生成单表的 CREATE TABLE 语句（供 LLM 理解表结构）"""
        col_defs = []
        for col in table.columns:
            parts = [f'    "{col.name}" {col.data_type}']
            if not col.nullable:
                parts.append("NOT NULL")
            if col.default_value:
                parts.append(f"DEFAULT {col.default_value}")
            if col.is_primary_key:
                parts.append("PRIMARY KEY")
            if col.comment:
                parts.append(f"COMMENT '{col.comment}'")
            col_defs.append(" ".join(parts))

        pk_clause = f",\n    PRIMARY KEY ({', '.join(f'"{k}"' for k in table.primary_key)})" \
                     if table.primary_key else ""

        table_comment = f"COMMENT '{table.comment}'" if table.comment else ""
        return (
            f"CREATE TABLE \"{table.table_name}\" (\n"
            + ",\n".join(col_defs)
            + pk_clause
            + f"\n) {table_comment};"
        )

    def _get_table_display_name(
        self, dictionary: "BusinessDictionary", table_name: str
    ) -> str:
        if not dictionary:
            return table_name
        for t in dictionary.tables:
            if t.table_name == table_name:
                return t.display_name if t.display_name != t.table_name else table_name
        return table_name
```

### 11.7 前端 Schema 可视化

```html
<!-- schema-panel.html — Tesla 风格的 Schema 可视化面板 -->

<style>
  .schema-panel {
    background: #0a0a0a;
    color: #fff;
    font-family: 'Universal Sans', sans-serif;
  }
  /* ER 图容器 */
  .er-canvas {
    width: 100%;
    height: 600px;
    position: relative;
    overflow: auto;
  }
  /* 表卡片 */
  .table-card {
    position: absolute;
    background: #141414;
    border: 1px solid #2a2a2a;
    border-radius: 12px;
    min-width: 220px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.5);
    transition: border-color 0.2s;
  }
  .table-card:hover { border-color: #3a7bd5; }
  .table-card-header {
    padding: 12px 16px;
    border-bottom: 1px solid #2a2a2a;
    display: flex;
    align-items: center;
    gap: 8px;
  }
  .table-icon { color: #3a7bd5; font-size: 18px; }
  .table-name { font-weight: 600; font-size: 14px; }
  .table-count { font-size: 11px; color: #666; margin-left: auto; }
  .table-card-body { padding: 8px 0; }
  /* 列行 */
  .col-row {
    display: flex;
    align-items: center;
    padding: 4px 16px;
    font-size: 12px;
    gap: 8px;
  }
  .col-row:hover { background: #1e1e1e; }
  .col-pk { color: #f59e0b; }
  .col-fk { color: #3a7bd5; }
  .col-type { color: #555; font-size: 10px; margin-left: auto; }
  .col-name { flex: 1; }
  .col-enum { color: #22c55e; font-size: 10px; }
  /* 枚举标签 */
  .enum-badge {
    background: #1a2e1a;
    color: #22c55e;
    border-radius: 4px;
    padding: 1px 6px;
    font-size: 10px;
  }
</style>

<!-- 工具栏 -->
<div class="schema-toolbar">
  <button onclick="refreshSchema()">重新抽取</button>
  <button onclick="toggleERView()">ER 图 / 列表</button>
  <input placeholder="搜索表名/列名" oninput="filterSchema(this.value)">
  <span class="schema-stats" id="schemaStats"></span>
</div>

<!-- ER 图画布（使用 AntV G6 或 D3.js 渲染） -->
<div class="er-canvas" id="erCanvas"></div>

<!-- 枚举值映射面板（点击列名弹出） -->
<div class="enum-editor-modal" id="enumEditor" style="display:none">
  <div class="enum-editor-header">
    <h3 id="enumColTitle">列名（表名.列名）</h3>
    <button onclick="closeEnumEditor()">✕</button>
  </div>
  <div class="enum-editor-body">
    <p>来源：<span id="enumSource">自动解析</span></p>
    <table>
      <thead>
        <tr><th>数据库值</th><th>中文显示</th><th>操作</th></tr>
      </thead>
      <tbody id="enumRows"></tbody>
    </table>
    <button onclick="addEnumRow()">+ 添加映射</button>
  </div>
  <button class="save-btn" onclick="saveEnumMapping()">保存</button>
</div>

<script>
// ER 图渲染（使用 AntV G6）
async function renderERDiagram(schemaJson) {
  const { nodes, edges, stats } = schemaJson;

  // 渲染统计信息
  document.getElementById('schemaStats').textContent =
    `${stats.table_count} 张表 · ${stats.relationship_count} 个关系`;

  // G6 初始化
  const graph = new G6.Graph({
    container: 'erCanvas',
    width: document.getElementById('erCanvas').offsetWidth,
    height: 600,
    layout: { type: 'dagre', rankdir: 'LR', nodesep: 60, ranksep: 100 },
    defaultNode: {
      type: 'rect',
      style: { fill: '#141414', stroke: '#2a2a2a', radius: 8, width: 200 },
      labelCfg: { style: { fill: '#fff', fontSize: 13 } },
    },
    defaultEdge: { type: 'cubic-horizontal', style: { stroke: '#3a7bd5', endArrow: true } },
  });

  // 过滤枚举列（加特殊标记）
  nodes.forEach(node => {
    const enumCols = node.columns.filter(c => c.isEnum);
    if (enumCols.length > 0) {
      node.label += ` [${enumCols.length} 枚举]`;
      node.style.stroke = '#22c55e';
    }
  });

  graph.data({ nodes, edges });
  graph.render();

  // 点击列名 → 打开枚举编辑器
  graph.on('node:click', (evt) => {
    const colName = evt.item.getModel().columns?.[evt.index]?.name;
    if (colName) openEnumEditor(evt.item.getModel(), colName);
  });
}

function openEnumEditor(tableNode, columnName) {
  // 获取列的枚举值，打开编辑弹窗
  // ...
}
</script>
```

### 11.8 REST API 接口

```yaml
# ── Schema 管理 ─────────────────────────────────────────────────

GET  /api/v1/groups/{group_id}/schema
     → 返回完整 SchemaMeta（表/列/外键/采样）

POST /api/v1/groups/{group_id}/schema/refresh
     → 重新抽取数据库 Schema（覆盖）

GET  /api/v1/groups/{group_id}/schema/er
     → 返回 ER 图 JSON（前端渲染用）
     ?format=mermaid | graphviz | json

GET  /api/v1/groups/{group_id}/schema/er/image
     → 返回 ER 图 PNG（通过 Graphviz 渲染）

# ── 业务字典 ───────────────────────────────────────────────────

GET  /api/v1/groups/{group_id}/dictionary
     → 返回完整业务字典

PUT  /api/v1/groups/{group_id}/dictionary/columns/{table}/{column}
     → 手动更新列映射
     body: {
       "display_name": "订单状态",
       "enum_values": [
         {"db_value": "0", "display_value": "待支付"},
         {"db_value": "1", "display_value": "已支付"},
         {"db_value": "2", "display_value": "已完成"},
       ]
     }

POST /api/v1/groups/{group_id}/dictionary/rebuild
     → 从 Schema 重新构建业务字典（覆盖手动修改）

GET  /api/v1/groups/{group_id}/schema/preview
     ?table=orders
     → 返回单表的 DDL + 采样数据 + 枚举解析预览
```



```
Micro-GenBI-Integration.md 总计 10 个章节：

  一、WrenAI 借鉴 vs 自研：边界矩阵
  二、RESTful API 设计（Java / .NET 集成方案）
  三、Java / .NET 集成方案
  四、前端原型扩展路线图
  五、完整部署架构
  六、实现优先级总览
  七、多模型支持与模型管理
  八、细粒度读写权限控制与写操作安全
  九、PRD 模式整合状态与补充功能
     9.1 PRD 五大模式整合现状（对照表）
     9.2 缺失：Hook Governance Layer（完整代码）
     9.3 缺失：SQL 铁律强化（SELECT * 检测）
     9.4 建议新增 6 项功能
        9.4.1 SQL 审计日志与追溯
        9.4.2 Prompt 版本管理与灰度回滚
        9.4.3 查询结果缓存（Query Cache）
        9.4.4 SQL 执行计划解释
        9.4.5 中文 Prompt 模板优化
        9.4.6 可观测性：质量评分与监控面板
▶ 十、用户体系、分组管理与缓存架构重构    ← 本次新增
    10.1 需求分析与设计决策
    10.2 缓存 Key 设计决策（三方案对比）
    10.3 用户认证与会话管理（完整实现）
    10.4 分组级缓存架构（SQL Key + 向量搜索 + 可配置 TTL）
    10.5 分组级写操作并发控制（乐观锁 + 分布式锁）
    10.6 REST API 接口
    10.7 缓存 Key 设计总结
▶ 十一、Schema 管理与业务字典映射    ← 本次新增
    11.1 整体设计
    11.2 数据库连接与 Schema 自动抽取（MySQL / PostgreSQL 完整代码）
    11.3 ER 关系图生成（Mermaid / Graphviz DOT / JSON 三种格式）
    11.4 业务字典与枚举值映射（注释解析 > 采样推断 > 手动维护）
    11.5 Schema 与字典的存储
    11.6 Schema 注入 LLM Prompt 的完整流程
    11.7 前端 Schema 可视化（Tesla 风格 ER 图 + 枚举编辑器）
    11.8 REST API 接口
▶ 十二、枚举推断规则与字段确认机制    ← 本次新增
    12.1 问题定义
    12.2 枚举列命名规则库（state/mode/type/is 前缀/后缀完整规则）
    12.3 置信度评分与推断引擎（注释优先 + 规则次之 + 采样验证）
    12.4 批次推断与待确认队列 + 确认工作流服务
    12.5 SQL 生成阻断机制（SafeAskService）
    12.6 前端：阻断 Banner + 枚举确认弹窗 + 字段编辑器
    12.7 REST API
▶ 十三、五个功能深化设计    ← 本次新增
    13.1 跨数据库 JOIN 支持（联邦查询）
    13.2 多租户行级数据隔离（RLS）——四层防御 + AST 检查
    13.3 LLM 输出稳定性保障——JSON Schema 验证 + SQL 格式标准化
    13.4 SQL 模板缓存（参数归一化）——{{INT_0}} 占位符 + 聚合函数不适用
    13.5 SQL 质量回归测试——准确率对比 + 上线阻断
    13.6 字段名中文别名映射——manual > comment > inferred 三层来源
    13.7 REST API