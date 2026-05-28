# Micro-GenBI 部署指南

## 目录

- [环境要求](#环境要求)
- [快速部署（Docker）](#快速部署docker)
- [手动部署](#手动部署)
- [配置详解](#配置详解)
- [验证部署](#验证部署)
- [可选功能](#可选功能)
- [生产环境](#生产环境)
- [故障排查](#故障排查)

---

## 环境要求

| 项目 | 要求 |
|------|------|
| Python | 3.11+ |
| 内存 | 最低 2GB，推荐 4GB+ |
| 磁盘 | 10GB+ |
| 数据库 | PostgreSQL 12+ / MySQL 8+ / SQLite 3（开发） |
| LLM API | DeepSeek / OpenAI / Ollama（至少配置一个） |

---

## 快速部署（Docker）

### 1. 准备环境

确保已安装：
- [Docker](https://docs.docker.com/get-docker/)
- [Docker Compose](https://docs.docker.com/compose/install/)

### 2. 配置环境变量

```bash
# 进入项目目录
cd d:\myProjects\text2sqlAgent

# 复制环境变量模板
copy .env.example .env

# 编辑 .env 文件，填入你的 LLM API Key
```

`.env` 文件关键配置：

```env
# LLM 配置（必填）
LLM_PROVIDER=deepseek
DEEPSEEK_API_KEY=sk-your-api-key

# 或者使用 OpenAI
# LLM_PROVIDER=openai
# OPENAI_API_KEY=sk-your-api-key

# 应用配置
APP_ENV=production
DEBUG=false
LOG_LEVEL=INFO

# 系统数据库
SYSTEM_DB_URL=postgresql+asyncpg://microgenbi:microgenbi_secret@postgres:5432/microgenbi
```

### 3. 启动服务

```bash
cd docker

# 启动所有服务（API + PostgreSQL + 可选 UI）
docker-compose up -d

# 查看日志
docker-compose logs -f api
```

### 4. 访问服务

| 服务 | 地址 |
|------|------|
| API 文档 | http://localhost:8000/docs |
| 用户界面 | http://localhost:8501 |
| 管理后台 | http://localhost:8502 |
| 健康检查 | http://localhost:8000/health |

---

## 手动部署

### 方式一：pip 安装

```bash
# 1. 克隆项目
git clone https://github.com/example/micro-genbi.git
cd micro-genbi

# 2. 创建虚拟环境（推荐）
python -m venv venv
venv\Scripts\activate  # Windows
# source venv/bin/activate  # Linux/macOS

# 3. 安装依赖
pip install -e ".[all]"

# 4. 复制环境变量
copy .env.example .env

# 5. 编辑 .env 填入配置
```

### 方式二：仅核心依赖

```bash
# 不安装可选依赖（预测、记忆等）
pip install -e .
```

### 6. 初始化数据库

```bash
# 使用 SQLite（开发，推荐）
echo "SYSTEM_DB_URL=sqlite:///./microgenbi.db" >> .env

# 初始化系统数据库
python -m micro_genbi.cli.main init-db

# 或使用 PostgreSQL
# python -m micro_genbi.cli.main init-db --db-url "postgresql+asyncpg://user:pass@localhost:5432/microgenbi"
```

### 7. 配置 Schema

从业务数据库自动抽取 Schema：

```bash
python -m micro_genbi.db.schema_extractor \
    --db-url "postgresql://user:pass@localhost:5432/business_db" \
    --output schema.yaml

# 或手动编辑 schema.yaml
```

### 8. 启动服务

```bash
# 终端 1: 启动 API
uvicorn micro_genbi.api.main:app --host 0.0.0.0 --port 8000 --reload

# 终端 2: 启动用户界面
streamlit run src/micro_genbi/ui/user_app.py --port 8501

# 终端 3: 启动管理后台（可选）
streamlit run src/micro_genbi/ui/admin_app.py --port 8502
```

---

## 配置详解

### .env 环境变量

```env
# =============================================
# 必需配置
# =============================================

# LLM 提供商
LLM_PROVIDER=deepseek          # deepseek | openai | ollama

# DeepSeek
DEEPSEEK_API_KEY=sk-xxx
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_BASE_URL=https://api.deepseek.com

# OpenAI（备选）
# OPENAI_API_KEY=sk-xxx
# OPENAI_MODEL=gpt-4o-mini

# =============================================
# 数据库配置
# =============================================

# 开发环境（SQLite）
SYSTEM_DB_URL=sqlite:///./microgenbi.db

# 生产环境（PostgreSQL）
# SYSTEM_DB_URL=postgresql+asyncpg://user:pass@localhost:5432/microgenbi

# =============================================
# 可选配置
# =============================================

# Schema 路径
SCHEMA_PATH=./schema.yaml

# 性能调优
MAX_LIMIT=1000
SQL_TIMEOUT=30
MAX_JOIN_COUNT=10
```

### schema.yaml 配置

定义业务数据库的语义信息：

```yaml
schema_version: "1.0"
databases:
  - id: sales
    display_name: 销售数据库
    db_category: primary
    tables:
      - name: orders
        logical_name: 订单表
        description: 所有销售订单
        primary_key: id
        columns:
          - name: total_amount
            logical_name: 订单金额
            type: DECIMAL(15,2)
            description: 订单总金额
          - name: status
            logical_name: 订单状态
            type: VARCHAR(20)
            enum_values:
              pending: 待支付
              paid: 已支付
              completed: 已完成
```

---

## 验证部署

### 1. 健康检查

```bash
curl http://localhost:8000/health
```

预期响应：
```json
{"status": "healthy", "version": "0.1.0"}
```

### 2. API 文档

访问 http://localhost:8000/docs 查看交互式 API 文档。

### 3. 测试查询

```bash
curl -X POST http://localhost:8000/api/v1/query \
  -H "Content-Type: application/json" \
  -d '{
    "query": "统计本月订单总额",
    "connection_id": "your-connection-id"
  }'
```

### 4. 运行测试

```bash
# 运行所有测试
pytest tests/ -v

# 只运行单元测试
pytest tests/unit/ -v

# 只运行集成测试
pytest tests/integration/ -v

# 带覆盖率
pytest tests/ --cov=micro_genbi --cov-report=html
```

---

## 可选功能

### 启用预测服务

```bash
# 安装预测依赖
pip install -e ".[prediction]"
```

```env
ENABLE_PREDICTION=true
PREDICTOR=auto  # auto | prophet | statistics
```

### 启用记忆存储

```bash
# 安装记忆依赖
pip install -e ".[memory]"
```

```env
LANCEDB_PATH=./data/lancedb
EMBEDDING_MODEL=BAAI/bge-small-zh-v1.5
```

### 启用 Redis 缓存

```env
REDIS_URL=redis://localhost:6379/0
CACHE_TTL=300
```

使用 Docker Compose 启动 Redis：

```bash
cd docker
docker-compose --profile with-redis up -d
```

### 启用 UI

```bash
cd docker
docker-compose --profile with-ui up -d
```

---

## 生产环境

### 1. 使用 PostgreSQL

```env
SYSTEM_DB_URL=postgresql+asyncpg://user:password@db-host:5432/microgenbi
```

### 2. 反向代理（Nginx）

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /streamlit {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 3. HTTPS 配置

```nginx
server {
    listen 443 ssl;
    ssl_certificate /path/to/cert.pem;
    ssl_certificate_key /path/to/key.pem;

    # 上述 location 配置...
}
```

### 4. 系统服务（systemd）

创建 `/etc/systemd/system/microgenbi.service`：

```ini
[Unit]
Description=Micro-GenBI API Service
After=network.target

[Service]
Type=simple
User=microgenbi
WorkingDirectory=/opt/microgenbi
Environment="PATH=/opt/microgenbi/venv/bin"
EnvironmentFile=/opt/microgenbi/.env
ExecStart=/opt/microgenbi/venv/bin/uvicorn micro_genbi.api.main:app --host 0.0.0.0 --port 8000
Restart=always

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable microgenbi
sudo systemctl start microgenbi
```

### 5. 备份策略

```bash
# 备份数据库
pg_dump -h localhost -U microgenbi microgenbi > backup_$(date +%Y%m%d).sql

# 备份配置文件
tar -czf config_backup.tar.gz schema.yaml .env
```

---

## 故障排查

### 服务启动失败

```bash
# 查看详细错误日志
docker-compose logs api
uvicorn micro_genbi.api.main:app --reload --log-level debug
```

### LLM 调用失败

1. 检查 API Key 是否正确配置
2. 检查网络是否可达（代理设置）
3. 查看日志中的具体错误信息

```env
# 如果需要代理
HTTP_PROXY=http://proxy:8080
HTTPS_PROXY=http://proxy:8080
```

### 数据库连接失败

1. 检查数据库是否运行
2. 检查连接字符串格式
3. 检查用户名密码

```bash
# 测试 PostgreSQL 连接
psql -h localhost -U microgenbi -d microgenbi

# 测试 SQLite
sqlite3 microgenbi.db ".tables"
```

### 端口被占用

```bash
# Windows 查看端口占用
netstat -ano | findstr :8000

# 杀掉占用进程
taskkill /PID <process_id> /F
```

### Schema 相关问题

```bash
# 重新抽取 Schema
python -m micro_genbi.db.schema_extractor \
    --db-url "your-db-url" \
    --output schema.yaml \
    --force

# 验证 Schema 格式
python -c "import yaml; yaml.safe_load(open('schema.yaml'))"
```

---

## 默认账户

```
用户名: admin
密码: admin123
```

> ⚠️ 生产环境请务必修改默认密码！

---

## 常见问题

**Q: 支持哪些数据库？**
A: PostgreSQL、MySQL、SQLite、ClickHouse。

**Q: 需要 GPU 吗？**
A: 不需要。LLM 调用通过 API 完成，使用 CPU 即可。

**Q: 如何添加新用户？**
A: 通过管理后台（http://localhost:8502）或 API 添加。

**Q: 如何扩展 Schema？**
A: 编辑 `schema.yaml` 或使用 `schema_extractor` 从数据库自动抽取。

**Q: 支持私有化部署吗？**
A: 支持。使用 Ollama 可以在本地运行 LLM，无需外部 API。

---

## 文档索引

| 文档 | 说明 |
|------|------|
| [README.md](./README.md) | 项目简介 |
| [CLAUDE.md](./CLAUDE.md) | AI 编程指南 |
| [Micro-GenBI-Dev-Plan.md](./Micro-GenBI-Dev-Plan.md) | 开发计划 |
| [Micro-GenBI-API-Spec.md](./Micro-GenBI-API-Spec.md) | API 规范 |
| [Multi-Database-Architecture.md](./Multi-Database-Architecture.md) | 多库架构 |
| [Micro-GenBI-System-Database.md](./Micro-GenBI-System-Database.md) | 系统数据库设计 |
