# Micro-GenBI

> 企业级 Text2SQL 智能分析平台

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104+-green.svg)](https://fastapi.tiangolo.com/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

## 简介

Micro-GenBI 是一个企业级的 **Text2SQL 智能分析平台**，允许用户使用自然语言查询数据库，系统自动生成 SQL 并返回查询结果。

### 核心特性

- **自然语言查询**：用自然语言提问，系统自动生成 SQL
- **多数据库支持**：PostgreSQL、MySQL、SQLite、ClickHouse
- **多租户架构**：支持用户组隔离，每个租户独立配置
- **智能 Schema 理解**：基于 Schema 上下文生成准确 SQL
- **安全防护**：SQL 注入防护、Prompt 注入检测、数据脱敏
- **自愈重试**：SQL 执行失败自动分析和修复
- **MCP 协议**：支持 AI Agent 集成（Claude Desktop 等）

## 系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Micro-GenBI 系统                          │
├─────────────────────────────────────────────────────────────┤
│  用户端界面（Streamlit）                                    │
│  ├── 数据查询 - 自然语言对话                                │
│  ├── 项目管理 - 按业务线组织数据源                          │
│  ├── 数据源   - 配置业务数据库                             │
│  ├── LLM 配置 - 配置 AI 模型                              │
│  └── Token 消耗 - 查看使用统计                             │
├─────────────────────────────────────────────────────────────┤
│  API 层（FastAPI）                                         │
│  ├── /api/v1/query     - 查询接口                         │
│  ├── /api/v1/admin/*   - 配置管理接口                      │
│  └── /api/v1/health    - 健康检查                         │
├─────────────────────────────────────────────────────────────┤
│  核心服务层                                                │
│  ├── AskService       - 查询流水线                         │
│  ├── IntentClassifier - 意图分类                           │
│  ├── SemanticRetriever - 语义检索                         │
│  ├── SQLGenerator     - SQL 生成                           │
│  └── SelfCorrector   - 自愈重试                           │
├─────────────────────────────────────────────────────────────┤
│  数据层                                                    │
│  ├── 系统数据库 - 用户、租户、配置                          │
│  └── 业务数据库 - 用户配置的数据库                          │
└─────────────────────────────────────────────────────────────┘
```

## 快速开始

### 方式一：一键启动（推荐）

```bash
# Windows
.\scripts\start.ps1

# Linux/macOS
chmod +x scripts/start.sh
./scripts/start.sh
```

### 方式二：手动启动

```bash
# 1. 安装依赖
pip install -e ".[all]"

# 2. 初始化数据库
python scripts/init_db.py --all

# 3. 启动 API 服务
uvicorn micro_genbi.api.main:app --reload --port 8000

# 4. 启动用户界面（新终端）
streamlit run src/micro_genbi/ui/user_app.py --port 8501

# 5. 启动管理后台（新终端）
streamlit run src/micro_genbi/ui/admin_app.py --port 8502
```

### 访问地址

| 服务 | 地址 |
|------|------|
| API 文档 | http://localhost:8000/docs |
| 用户界面 | http://localhost:8501 |
| 管理后台 | http://localhost:8502 |

### 默认账户

```
用户名: admin
密码: admin123
```

## 项目结构

```
src/micro_genbi/
├── __init__.py              # 模块入口
├── errors.py               # 异常处理
├── models.py               # 数据模型
├── api/                    # API 路由
│   ├── main.py            # FastAPI 应用
│   ├── routes.py          # 查询路由
│   ├── config_routes.py   # 配置路由
│   └── dependencies.py     # 依赖注入
├── database/              # 系统数据库
│   ├── models.py          # ORM 模型
│   └── services.py        # CRUD 服务
├── db/                    # 业务数据库
│   ├── config.py          # 配置管理
│   ├── engine.py          # 执行引擎
│   └── health_check.py    # 健康检查
├── llm/                   # LLM 客户端
│   ├── base.py            # 基类
│   └── prompts.py         # Prompt 模板
├── semantic/              # 语义层
│   └── schema_registry.py # Schema 管理
├── security/              # 安全模块
│   ├── sql_sanitizer.py   # SQL 安全
│   ├── prompt_injection.py # 注入检测
│   └── data_masker.py     # 数据脱敏
├── service/               # 核心服务
│   └── ask_service.py     # 查询服务
├── pipeline/              # 执行流水线
│   └── self_correction.py  # 自愈重试
├── retrieval/              # 语义检索
│   └── semantic_retriever.py
├── mcp/                   # MCP Server
│   └── server.py
├── ui/                    # Streamlit 界面
│   ├── user_app.py        # 用户端
│   └── admin_app.py       # 管理后台
└── monitoring/            # 可观测性
    └── logging.py

scripts/
├── init_db.py             # 数据库初始化
├── schema_extract.py      # Schema 抽取
├── start.sh               # Linux 启动脚本
└── start.ps1             # Windows 启动脚本
```

## 配置说明

### 环境变量

复制 `.env.example` 为 `.env` 并配置：

```bash
# 系统数据库（默认 SQLite）
SYSTEM_DB_URL="sqlite:///./microgenbi.db"

# 或使用 PostgreSQL
# SYSTEM_DB_URL="postgresql+asyncpg://user:pass@localhost:5432/microgenbi"
```

### 数据源配置

1. 进入「数据源管理」页面
2. 点击「添加数据源」
3. 填写数据库连接信息
4. 测试并保存

### Schema 配置

从数据库自动抽取 Schema：

```bash
python scripts/schema_extract.py --db-url "postgresql://user:pass@localhost:5432/mydb" -o schema.yaml
```

## API 接口

### 查询接口

```bash
POST /api/v1/query
{
    "query": "统计各部门上月的报销总额",
    "project_id": "project_oil",
    "connection_id": "conn_001"
}
```

### 配置管理

```bash
# LLM 配置
GET    /api/v1/admin/llm-configs
POST   /api/v1/admin/llm-configs

# 数据源
GET    /api/v1/admin/connections
POST   /api/v1/admin/connections

# 项目
GET    /api/v1/admin/projects
POST   /api/v1/admin/projects
```

详见 API 文档：http://localhost:8000/docs

## 开发

### 运行测试

```bash
pytest tests/ -v
```

### 代码格式

```bash
# Black 格式化
black src/

# Ruff 检查
ruff check src/
```

## 部署

### Docker 部署

```bash
cd docker
docker-compose up -d
```

### 生产环境

1. 使用 PostgreSQL 作为系统数据库
2. 配置反向代理（Nginx）
3. 启用 HTTPS
4. 配置备份策略

## 文档

- [开发计划](./Micro-GenBI-Dev-Plan.md)
- [API 规范](./Micro-GenBI-API-Spec.md)
- [系统数据库设计](./Micro-GenBI-System-Database.md)
- [安全加固](./Micro-GenBI-Security-Enhancement.md)

## License

MIT License
