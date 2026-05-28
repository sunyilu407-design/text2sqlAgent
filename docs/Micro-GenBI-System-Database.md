# Micro-GenBI 系统数据库设计

> 版本：v1.0
> 日期：2026-05-25

---

## 一、概述

Micro-GenBI 采用 **双数据库架构**：

```
┌─────────────────────────────────────────────────────────────┐
│                    Micro-GenBI 系统                          │
├─────────────────────────────────────────────────────────────┤
│  系统数据库（SQLite/PostgreSQL）                            │
│  ├── 用户管理                                               │
│  ├── 用户组/租户                                            │
│  ├── LLM 配置（每个组独立配置）                             │
│  ├── 数据库连接配置（每个组多个数据库）                      │
│  ├── Schema 配置                                            │
│  ├── 查询历史                                               │
│  ├── 会话管理                                               │
│  ├── API Key 管理                                          │
│  └── 审计日志                                              │
├─────────────────────────────────────────────────────────────┤
│  业务数据库（用户配置的数据库）                              │
│  ├── 油库数据库 A                                          │
│  ├── 油库数据库 B                                          │
│  └── 客户数据库 C                                          │
└─────────────────────────────────────────────────────────────┘
```

---

## 二、系统数据库设计

### 2.1 ER 图

```
┌──────────────┐       ┌──────────────┐
│   tenants    │       │    users    │
├──────────────┤       ├──────────────┤
│ id (PK)      │◄──┐   │ id (PK)     │
│ name         │   │   │ tenant_id   │───┐
│ description  │   │   │ username    │   │
│ created_at   │   │   │ email       │   │
│ updated_at   │   │   │ password    │   │
└──────────────┘   │   │ role        │   │
       │            │   │ created_at  │   │
       │            │   └──────────────┘   │
       │            │                       │
       ▼            │                       ▼
┌──────────────┐   │   ┌──────────────────┐
│tenant_members│   │   │   llm_configs     │
├──────────────┤   │   ├──────────────────┤
│ id (PK)      │   │   │ id (PK)          │
│ tenant_id(FK)│───┘   │ tenant_id (FK)   │───┐
│ user_id (FK) │───────►│ name             │   │
│ role         │       │ provider          │   │
│ created_at   │       │ api_key (加密)   │   │
└──────────────┘       │ base_url         │   │
                        │ model             │   │
                        │ max_tokens        │   │
                        │ temperature       │   │
                        │ is_default        │   │
                        │ created_at        │   │
                        └──────────────────┘   │
                                │            │
                                ▼            │
┌──────────────────────┐   ┌──────────────────┐
│  database_connections │   │   schema_configs │
├──────────────────────┤   ├──────────────────┤
│ id (PK)              │   │ id (PK)          │
│ tenant_id (FK)       │───┤ tenant_id (FK)   │───┐
│ name                 │   │ name             │   │
│ db_type              │   │ connection_id(FK)│   │
│ host                 │   │ yaml_content     │   │
│ port                 │   │ version          │   │
│ database             │   │ is_active        │   │
│ username             │   │ created_at       │   │
│ password (加密)      │   │ updated_at       │   │
│ is_default           │   └──────────────────┘   │
│ created_at           │              │
└──────────────────────┘              │
                                       ▼
┌──────────────────────┐   ┌──────────────────┐
│   query_history      │   │   audit_logs    │
├──────────────────────┤   ├──────────────────┤
│ id (PK)              │   │ id (PK)          │
│ user_id (FK)         │   │ tenant_id (FK)   │
│ tenant_id (FK)       │   │ user_id (FK)     │
│ session_id           │   │ ip_address        │
│ natural_query        │   │ event_type       │
│ generated_sql         │   │ resource          │
│ tables_used          │   │ action            │
│ row_count            │   │ result            │
│ execution_time_ms     │   │ error_message     │
│ llm_config_id        │   │ metadata (JSON)   │
│ connection_id         │   │ created_at        │
│ created_at           │   └──────────────────┘
└──────────────────────┘

┌──────────────────────┐
│   api_keys          │
├──────────────────────┤
│ id (PK)              │
│ tenant_id (FK)       │
│ user_id (FK)         │
│ name                 │
│ key_hash             │
│ key_prefix           │
│ scope                │
│ allowed_ips (JSON)    │
│ expires_at           │
│ is_active            │
│ last_used_at         │
│ created_at           │
└──────────────────────┘
```

---

## 三、数据表定义

### 3.1 tenants - 租户/用户组表

```sql
CREATE TABLE tenants (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(255) NOT NULL UNIQUE,
    description TEXT,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE tenants IS '租户/用户组表';
COMMENT ON COLUMN tenants.name IS '租户名称';
```

### 3.2 users - 用户表

```sql
CREATE TABLE users (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) REFERENCES tenants(id),
    username VARCHAR(100) NOT NULL UNIQUE,
    email VARCHAR(255) UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    role VARCHAR(50) DEFAULT 'user',  -- admin, user, readonly
    is_active BOOLEAN DEFAULT TRUE,
    last_login_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_users_tenant ON users(tenant_id);
CREATE INDEX idx_users_username ON users(username);

COMMENT ON TABLE users IS '用户表';
```

### 3.3 tenant_members - 租户成员表

```sql
CREATE TABLE tenant_members (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    role VARCHAR(50) DEFAULT 'member',  -- admin, member
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tenant_id, user_id)
);

CREATE INDEX idx_members_tenant ON tenant_members(tenant_id);
CREATE INDEX idx_members_user ON tenant_members(user_id);
```

### 3.4 llm_configs - LLM 配置表

```sql
CREATE TABLE llm_configs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    provider VARCHAR(50) NOT NULL,  -- deepseek, openai, ollama
    api_key_encrypted TEXT,  -- AES-256 加密
    base_url VARCHAR(500),
    model VARCHAR(100) NOT NULL,
    max_tokens INTEGER DEFAULT 2000,
    temperature DECIMAL(3,2) DEFAULT 0.7,
    timeout_seconds INTEGER DEFAULT 60,
    is_default BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_llm_tenant ON llm_configs(tenant_id);
CREATE INDEX idx_llm_default ON llm_configs(tenant_id, is_default) WHERE is_default = TRUE;
```

### 3.5 database_connections - 数据库连接配置表

```sql
CREATE TABLE database_connections (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    db_type VARCHAR(50) NOT NULL,  -- postgresql, mysql, sqlite, clickhouse
    host VARCHAR(255),
    port INTEGER,
    database_name VARCHAR(255) NOT NULL,
    username VARCHAR(100),
    password_encrypted TEXT,  -- AES-256 加密
    charset VARCHAR(20) DEFAULT 'utf8mb4',
    pool_size INTEGER DEFAULT 5,
    max_overflow INTEGER DEFAULT 10,
    is_default BOOLEAN DEFAULT FALSE,
    is_readonly BOOLEAN DEFAULT TRUE,  -- 强制只读
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    -- SQLite 只需要 database_name
    CONSTRAINT chk_sqlite CHECK (
        (db_type = 'sqlite' AND host IS NULL) OR
        (db_type != 'sqlite' AND host IS NOT NULL)
    )
);

CREATE INDEX idx_db_tenant ON database_connections(tenant_id);
CREATE INDEX idx_db_default ON database_connections(tenant_id, is_default) WHERE is_default = TRUE;
```

### 3.6 schema_configs - Schema 配置表

```sql
CREATE TABLE schema_configs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id) ON DELETE CASCADE,
    connection_id VARCHAR(36) NOT NULL REFERENCES database_connections(id) ON DELETE CASCADE,
    name VARCHAR(100) NOT NULL,
    description TEXT,
    yaml_content TEXT NOT NULL,  -- schema.yaml 内容
    version INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,

    UNIQUE(tenant_id, connection_id)
);

CREATE INDEX idx_schema_tenant ON schema_configs(tenant_id);
CREATE INDEX idx_schema_connection ON schema_configs(connection_id);
```

### 3.7 query_history - 查询历史表

```sql
CREATE TABLE query_history (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    session_id VARCHAR(36),
    natural_query TEXT NOT NULL,
    generated_sql TEXT,
    tables_used TEXT[],  -- PostgreSQL 数组类型
    row_count INTEGER,
    execution_time_ms INTEGER,
    llm_config_id VARCHAR(36) REFERENCES llm_configs(id),
    connection_id VARCHAR(36) REFERENCES database_connections(id),
    intent VARCHAR(50),
    confidence DECIMAL(3,2),
    status VARCHAR(20) DEFAULT 'success',  -- success, failed, blocked
    error_message TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_history_user ON query_history(user_id);
CREATE INDEX idx_history_tenant ON query_history(tenant_id);
CREATE INDEX idx_history_session ON query_history(session_id);
CREATE INDEX idx_history_created ON query_history(created_at DESC);
```

### 3.8 sessions - 会话表

```sql
CREATE TABLE sessions (
    id VARCHAR(36) PRIMARY KEY,
    user_id VARCHAR(36) NOT NULL REFERENCES users(id),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    title VARCHAR(255),
    message_count INTEGER DEFAULT 0,
    last_message_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    expires_at TIMESTAMP
);

CREATE INDEX idx_sessions_user ON sessions(user_id);
CREATE INDEX idx_sessions_tenant ON sessions(tenant_id);
```

### 3.9 api_keys - API Key 表

```sql
CREATE TABLE api_keys (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) NOT NULL REFERENCES tenants(id),
    user_id VARCHAR(36) REFERENCES users(id),
    name VARCHAR(100) NOT NULL,
    key_hash VARCHAR(64) NOT NULL UNIQUE,  -- SHA-256 哈希
    key_prefix VARCHAR(10) NOT NULL,  -- 显示前缀 mgbi_sk_xxxx
    scope VARCHAR(50) DEFAULT 'readonly',  -- readonly, readwrite
    allowed_ips JSONB,  -- ["192.168.1.1", "10.0.0.0/8"]
    expires_at TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    last_used_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_apikey_tenant ON api_keys(tenant_id);
CREATE INDEX idx_apikey_hash ON api_keys(key_hash);
```

### 3.10 audit_logs - 审计日志表

```sql
CREATE TABLE audit_logs (
    id VARCHAR(36) PRIMARY KEY DEFAULT gen_random_uuid(),
    tenant_id VARCHAR(36) REFERENCES tenants(id),
    user_id VARCHAR(36) REFERENCES users(id),
    ip_address VARCHAR(45),
    user_agent TEXT,
    event_type VARCHAR(100) NOT NULL,  -- auth.login, query.submitted, security.blocked
    resource VARCHAR(100),
    action VARCHAR(50),
    result VARCHAR(20) DEFAULT 'success',  -- success, failed, blocked
    error_code VARCHAR(50),
    error_message TEXT,
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX idx_audit_tenant ON audit_logs(tenant_id);
CREATE INDEX idx_audit_user ON audit_logs(user_id);
CREATE INDEX idx_audit_event ON audit_logs(event_type);
CREATE INDEX idx_audit_created ON audit_logs(created_at DESC);
```

---

## 四、多租户数据隔离

### 4.1 租户隔离策略

```python
# 每个查询自动注入 tenant_id 过滤

class TenantIsolationMiddleware:
    """租户隔离中间件"""

    async def __call__(self, request, call_next):
        # 从 JWT Token 或 API Key 中提取 tenant_id
        tenant_id = self._extract_tenant_id(request)

        # 注入到请求上下文
        request.state.tenant_id = tenant_id

        response = await call_next(request)
        return response
```

### 4.2 数据访问控制

```python
# 所有数据库查询自动添加 tenant_id 条件

class TenantAwareRepository:
    """租户感知的仓库基类"""

    def __init__(self, tenant_id: str):
        self.tenant_id = tenant_id

    async def find_all(self):
        # 自动添加租户过滤
        query = f"WHERE tenant_id = '{self.tenant_id}'"
        return await self.db.execute(f"SELECT * FROM {self.table} {query}")

    async def find_by_id(self, id: str):
        query = f"WHERE id = '{id}' AND tenant_id = '{self.tenant_id}'"
        return await self.db.execute(f"SELECT * FROM {self.table} {query}")
```

---

## 五、配置管理 API

### 5.1 LLM 配置管理

```
# 租户管理员配置 LLM
POST   /api/v1/tenants/{tenant_id}/llm-configs      # 创建 LLM 配置
GET    /api/v1/tenants/{tenant_id}/llm-configs      # 列出 LLM 配置
PUT    /api/v1/tenants/{tenant_id}/llm-configs/{id} # 更新配置
DELETE /api/v1/tenants/{tenant_id}/llm-configs/{id} # 删除配置
POST   /api/v1/tenants/{tenant_id}/llm-configs/{id}/test # 测试连接
```

### 5.2 数据库连接管理

```
# 租户管理员配置业务数据库
POST   /api/v1/tenants/{tenant_id}/connections        # 创建连接
GET    /api/v1/tenants/{tenant_id}/connections        # 列出连接
PUT    /api/v1/tenants/{tenant_id}/connections/{id}  # 更新连接
DELETE /api/v1/tenants/{tenant_id}/connections/{id}  # 删除连接
POST   /api/v1/tenants/{tenant_id}/connections/{id}/test # 测试连接
POST   /api/v1/tenants/{tenant_id}/connections/{id}/refresh-schema # 刷新 Schema
```

### 5.3 Schema 配置管理

```
# 管理 Schema 配置
GET    /api/v1/tenants/{tenant_id}/schemas             # 列出 Schema
POST   /api/v1/tenants/{tenant_id}/schemas             # 创建 Schema
PUT    /api/v1/tenants/{tenant_id}/schemas/{id}        # 更新 Schema
DELETE /api/v1/tenants/{tenant_id}/schemas/{id}        # 删除 Schema
POST   /api/v1/tenants/{tenant_id}/schemas/{id}/extract # 从数据库抽取
```

---

## 六、加密存储

### 6.1 敏感字段加密

```python
from cryptography.fernet import Fernet
import base64
import hashlib

class SecretManager:
    """密钥管理器"""

    def __init__(self, master_key: str):
        # 从主密钥派生加密密钥
        key = hashlib.sha256(master_key.encode()).digest()
        self.fernet = Fernet(base64.urlsafe_b64encode(key))

    def encrypt(self, plaintext: str) -> str:
        """加密敏感数据"""
        return self.fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, ciphertext: str) -> str:
        """解密敏感数据"""
        return self.fernet.decrypt(ciphertext.encode()).decode()

# 加密存储的字段：
# - llm_configs.api_key_encrypted
# - database_connections.password_encrypted
# - api_keys.key_hash (只存储哈希)
```

### 6.2 API Key 验证

```python
import hashlib

def hash_api_key(key: str) -> str:
    """API Key 只存储哈希，不存储明文"""
    return hashlib.sha256(key.encode()).hexdigest()

def verify_api_key(key: str, stored_hash: str) -> bool:
    """验证 API Key"""
    return hashlib.sha256(key.encode()).hexdigest() == stored_hash
```

---

## 七、初始化数据

### 7.1 创建系统表

```bash
# 使用 SQLite 作为系统数据库
DATABASE_URL=sqlite:///./microgenbi.db

# 或者 PostgreSQL
DATABASE_URL=postgresql://user:pass@localhost/microgenbi
```

### 7.2 初始管理员

```sql
-- 创建默认租户
INSERT INTO tenants (id, name, description)
VALUES ('default', '默认租户', '系统默认租户');

-- 创建管理员用户（密码：admin123）
INSERT INTO users (id, tenant_id, username, email, password_hash, role)
VALUES (
    'admin',
    'default',
    'admin',
    'admin@example.com',
    -- BCrypt 哈希
    '$2b$12$LQv3c1yqBWVHxkd0LHAkCOYz6TtxMQJqhN8/X4.S0P0O4VfGrHOuy',
    'admin'
);

-- 添加管理员到租户
INSERT INTO tenant_members (tenant_id, user_id, role)
VALUES ('default', 'admin', 'admin');
```

---

*本文档定义了 Micro-GenBI 系统数据库的完整设计，支持多租户架构。*
