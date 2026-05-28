# Micro-GenBI AI 编程助手指引

本文件为 AI 编程助手（Claude Code、Cursor 等）提供项目上下文和开发规范。

---

## 项目概述

Micro-GenBI 是一个企业级 **Text2SQL 垂直领域智能体**，实现"对话式数据分析平台"。

### 核心功能
- 自然语言转 SQL 查询
- 多数据库联合查询（同构聚合 / 异构联邦）
- 时序预测与异常检测
- AI 驱动的深度分析

### 技术栈
- Python 3.11+ / FastAPI / SQLAlchemy 2.x
- LLM: DeepSeek / OpenAI / Ollama
- 向量存储: LanceDB（可选）
- 预测模型: Prophet / statsmodels（可选）

---

## 项目结构

```
micro-genbi/
├── src/micro_genbi/          # 主源码目录
│   ├── __init__.py
│   ├── errors.py             # 异常处理（WrenAI 移植）
│   ├── models.py            # Pydantic 数据模型
│   ├── config.py            # 配置管理
│   │
│   ├── db/                  # 数据库层
│   │   ├── config.py        # ProfileManager（3层回退）
│   │   ├── engine.py        # SQLAlchemy Engine
│   │   ├── executor.py       # 异步 SQL 执行器
│   │   ├── schema_registry.py # 多库语义配置
│   │   ├── router.py        # 多库路由器
│   │   └── connection_factory.py # 多库连接池
│   │
│   ├── semantic/             # 语义层
│   │   └── schema_manager.py # schema.yaml 加载
│   │
│   ├── pipeline/            # 执行流水线
│   │   ├── safety_validator.py # SQL 安全验证
│   │   ├── self_correction.py # SQL 自愈
│   │   └── instructions.py   # Prompt 指令
│   │
│   ├── intent/              # 意图分类
│   │   └── classifier.py     # 三层分类器
│   │
│   ├── retrieval/           # RAG 检索
│   │   ├── semantic_retriever.py
│   │   └── tfidf_index.py
│   │
│   ├── llm/                 # LLM 客户端
│   │   ├── base.py
│   │   ├── deepseek_client.py
│   │   ├── openai_client.py
│   │   └── ollama_client.py
│   │
│   ├── chart/                # 图表生成
│   │   └── chart_engine.py  # ECharts 生成
│   │
│   ├── service/             # 顶层服务
│   │   ├── ask_service.py
│   │   ├── history_manager.py
│   │   ├── task_tracker.py
│   │   └── factory.py
│   │
│   ├── api/                 # FastAPI 路由
│   │   ├── main.py
│   │   └── routes.py
│   │
│   ├── mcp/                 # MCP Server
│   │   └── server.py
│   │
│   ├── ui/                  # Streamlit 前端
│   │   └── streamlit_app.py
│   │
│   ├── cli/                 # CLI 工具
│   │   └── main.py
│   │
│   └── monitoring/          # 可观测性
│       ├── logging.py
│       └── metrics.py
│
├── tests/                   # 测试目录
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── schema.yaml              # 语义配置（单库）
├── schema_registry/          # 多库配置目录
├── genbi_config.yaml       # 多库连接配置
└── pyproject.toml
```

---

## 开发规范

### 1. 代码风格
- 使用 `ruff` 进行代码检查
- 行长度限制：100 字符
- 缩进：4 空格
- 遵循 PEP 8 + Google 代码风格

### 2. 类型注解
- 公开 API 必须有类型注解
- 使用 `TYPE_CHECKING` 避免循环导入
- 优先使用 Pydantic 模型而非裸 dict

### 3. 异常处理
```python
from micro_genbi.errors import GenBIError, GenBIReRetry, should_propagate, to_retry

# 基础设施错误直接抛出
if should_propagate(exc):
    raise

# LLM 可修复的错误触发重试
raise to_retry(exc)
```

### 4. SQL 安全
- 所有 SQL 必须经过 `SQLSafetyValidator` 验证
- 禁止写操作（INSERT/UPDATE/DELETE/DROP/ALTER）
- 必须有 LIMIT（默认 1000）
- 表名必须在 schema.yaml 中存在

### 5. LLM 调用
- 使用统一的 `LLMClient` 接口
- 支持 DeepSeek / OpenAI / Ollama
- 必须设置 `max_tokens` 防止无限输出
- 敏感信息脱敏使用 `redact_secrets()`

### 6. 异步编程
- 使用 `asyncpg` / `aiomysql` 进行异步数据库操作
- 并发执行使用 `asyncio.gather()`
- 避免在循环中 await

---

## 依赖文档索引

| 需要了解的内容 | 参考文档 |
|-------------|---------|
| 完整架构设计 | `Micro-GenBI-Integration.md` |
| 多库架构 | `Multi-Database-Architecture.md` |
| WrenAI 源码移植 | `Micro-GenBI-WrenAI-Port-Guide.md` |
| PRD 定义 | `GenBI_Integration_PRD.md` |
| WrenAI 原始源码 | `WrenAI-wren-v0.7.0/` |

---

## 常用命令

```bash
# 安装依赖
pip install -e ".[all]"    # 安装全部依赖
pip install -e ".[dev]"     # 仅安装开发依赖

# 运行应用
uvicorn micro_genbi.api.main:app --reload --port 8000

# 运行 Streamlit UI
streamlit run src/micro_genbi/ui/streamlit_app.py

# 运行测试
pytest tests/ -v
pytest tests/unit/ -v --cov=micro_genbi

# 代码检查
ruff check src/micro_genbi/
ruff format src/micro_genbi/

# CLI 工具
genbi ask "统计本月销售额"
genbi schema --list
genbi config --validate
```

---

## 注意事项

### 1. 多库 vs 单库
- 单库模式：使用 `schema.yaml`
- 多库模式：使用 `schema_registry/` 目录 + `genbi_config.yaml`
- 模式在启动时确定，运行时不切换

### 2. LLM 成本控制
- IntentClassifier Layer 1 使用规则引擎（0 token）
- 只在必要时调用 LLM
- 结果摘要避免 token 爆炸

### 3. SQL 安全红线
- 绝对禁止裸 SQL 拼接
- 必须使用参数化查询
- 敏感字段值必须脱敏后记录日志

### 4. 测试要求
- 核心模块（SQLSafetyValidator、IntentClassifier）必须有单元测试
- 集成测试覆盖完整流水线
- 测试用例存放在 `tests/fixtures/`

---

## 环境配置

```bash
# 复制环境变量模板
cp .env.example .env

# 填写实际配置
# - 设置 LLM API Key
# - 配置数据库连接
# - 配置 schema.yaml 路径
```
