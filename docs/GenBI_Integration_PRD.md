# 🚀 微分内部系统 - GenBI 垂直领域大模型集成指南 (Claude Code 架构增强版)

## 📌 1. 项目背景与目标
*   **目标**：在现有的“Java Spring Boot + Vue”内部管理系统（OA）中，搭建一个极度安全、高效的 **Text2SQL 垂直领域小智能体（Agent）**，实现“对话式数据查询与图表生成”功能。
*   **设计哲学**：深度借鉴 **Claude Code (Anthropic Agent OS)** 的底层架构思想，抛弃传统的“裸调大模型 API”做法，引入提示词缓存经济学、爆炸半径控制、工具流水线与上下文卫生系统。
*   **阶段**：MVP 测试版。先在独立环境跑通核心链路，验证 SQL 准确率与系统安全性。

---

## 🧠 2. 核心架构设计思想 (源自 Claude Code)

为了让这个 Text2SQL Agent 达到企业级生产标准，AI 开发助手在编写代码时必须严格遵循以下 5 大架构模式：

### 💎 模式一：Prompt Cache Economics (提示词缓存经济学)
*   **痛点**：每次提问都要带上庞大的数据库表结构（DDL），Token 消耗极大且响应慢。
*   **规范**：构建 **“静态前置（Stable Prefix） + 动态后置（Dynamic Tail）”** 的提示词结构。
    *   **Static Prefix**：将 Agent 的角色设定（System Prompt）、工具描述（Tool Definitions）、以及所有相关的建表语句（DDL）全部放在 Prompt 最前面，绝对固定不变，以最高效利用大模型的 Prompt Cache。
    *   **Dynamic Tail**：将用户的当前提问、动态的时间变量（如当前日期）、极少量的多轮对话历史，严格放在 Prompt 的最末尾。

### 🛡️ 模式二：Blast Radius Permission (爆炸半径权限控制)
*   **痛点**：AI 生成的恶意或低效 SQL 可能导致删库或把数据库卡死。
*   **规范**：实行双层防护机制。
    1.  **物理层**：数据库连接只使用 `READ_ONLY` 权限的专属账号。
    2.  **词法层拦截**：在执行 SQL 工具前，使用正则强行拦截包含 `DROP, DELETE, UPDATE, TRUNCATE, ALTER, GRANT` 的语句，直接触发 `PermissionDenied` 异常并打断工作流。

### 🪝 模式三：Hook Governance Layer (钩子治理与上下文注入)
*   **痛点**：用户常说黑话（如“公车私用”），AI 不知道对应数据库里的字典值。
*   **规范**：利用 `PreToolUse Hook`（执行前钩子）。当系统解析到相关业务词汇时，Hook 会自动去后端的“业务字典表”查询映射关系，并将这些信息作为 **“附加隐式上下文 (Additional Context)”** 悄悄拼接到用户的提问前，指导 AI 准确生成 SQL。

### 🧹 模式四：Context Hygiene System (上下文卫生系统)
*   **痛点**：如果 `SELECT` 查出 10000 条数据直接返回给 AI，会瞬间撑爆上下文窗口（Context Window），导致 Agent 崩溃。
*   **规范**：利用 `PostToolUse Hook`（执行后钩子）。数据库返回海量数据后，**绝对不要**把全量数据丢进对话历史。Hook 只负责提取数据生成图表 JSON 传给前端，然后向 Agent 的上下文里只返回一条精简摘要：“查询成功，共返回 10000 行数据，前端已渲染饼图”，保持大模型的记忆绝对干净。

### 📜 模式五：Behavior Institutionalization (行为制度化)
*   **规范**：在 System Prompt 中为 SQL 编写立下“铁律”：
    1. 除非明确要求汇总，否则所有 `SELECT` 必须追加 `LIMIT 1000`。
    2. 绝对禁止使用 `SELECT *`，必须显式写出需要的字段名。

---

## 🛠️ 3. 开发实现步骤（写给 AI 程序员）

### 第一步：数据库安全隔离 (SQL 脚本)
1. 创建只读用户 `genbi_readonly`。
2. 仅授予对测试库（如 `car_apply_record`、`reimbursement_record`）的 `SELECT` 权限。

### 第二步：Agent 后端引擎开发 (Spring Boot 或 FastAPI)
1. **API 网关接口**：编写 `/api/v1/ai/genbi/query` 接口，接收 Vue 前端的提问。
2. **提示词组装器 (`PromptAssembler`)**：实现模式一，精准拼接 Cache 友好的 DDL 静态头部。
3. **工具运行时流水线 (`ToolRuntimePipeline`)**：
   * 编写 `execute_sql` 工具。
   * **Pre-Hook**：执行字典表注入（模式三）和 SQL 词法扫描拦截（模式二）。
   * **Execute**：使用只读账号连接数据库执行 SQL。
   * **Post-Hook**：如果行数大于 10 行，执行数据截断（模式四）。将数据交由 ECharts 配置生成器转换为图表代码。

### 第三步：Vue 前端专属“AI 助手”组件开发
1. 编写 `AiDataAssistant.vue` 悬浮抽屉或全屏看板。
2. 实现类似 ChatGPT 的聊天气泡交互。
3. **图表渲染**：解析后端传回的 `echarts_option` JSON 格式，动态挂载渲染柱状图、饼图或数据表格。

---

## 🎯 4. 验收标准
MVP 演示时，输入“统计各部门上月报销总额”，系统应在 3 秒内：
1. 精准命中提示词缓存。
2. 触发 Pre-Hook 获取部门 ID 字典。
3. 安全执行带 LIMIT 的 SQL。
4. 返回极简上下文给模型，并在 Vue 前端优雅渲染出 ECharts 柱状图。