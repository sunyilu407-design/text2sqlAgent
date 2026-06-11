# Micro-GenBI — 缓存策略文档

> 版本：v1.0
> 日期：2026-05-28
> 模块：`src/micro_genbi/monitoring/cache.py`

---

## 一、概述

`cache.py` 实现了 Micro-GenBI 的**三级缓存策略**，覆盖从 SQL 结果到 LLM 响应再到 Schema 配置的全链路缓存能力。

### 设计目标

- **高性能**：内存级缓存，毫秒级响应
- **可演进**：支持未来平滑迁移到 Redis
- **安全可靠**：LRU 淘汰防止内存膨胀，TTL 防止数据过期
- **线程安全**：支持高并发访问

---

## 二、缓存层级架构

```
┌─────────────────────────────────────────────┐
│           Application Layer                 │
│                                             │
│  ┌──────────────┐  ┌──────────────┐       │
│  │ SQL Result   │  │ LLM Response │       │
│  │ Cache        │  │ Cache         │       │
│  │ TTL: 300s   │  │ TTL: 600s    │       │
│  │ Max: 500    │  │ Max: 200     │       │
│  └──────┬───────┘  └──────┬───────┘       │
│         │                  │               │
│         └────────┬─────────┘               │
│                  ▼                          │
│         ┌──────────────┐                   │
│         │Schema Config │                   │
│         │ Cache        │                   │
│         │ TTL: 300s   │                   │
│         │ Max: 50    │                   │
│         └──────────────┘                   │
│                  │                          │
└──────────────────┼──────────────────────────┘
                   ▼
         ┌─────────────────┐
         │  Memory Cache   │  ← TTLCache (默认)
         │  (OrderedDict)  │
         └────────┬────────┘
                   │  可选
                   ▼
         ┌─────────────────┐
         │     Redis       │  ← 生产环境可选升级
         └─────────────────┘
```

---

## 三、TTLCache 核心实现

### 3.1 特性列表

| 特性 | 说明 |
|------|------|
| **TTL 过期** | 每个条目有独立的过期时间，到期自动失效 |
| **LRU 淘汰** | 超过 `max_size` 时，淘汰最旧的条目 |
| **NULL 值标记** | 使用哨兵对象标记 NULL，防止缓存穿透 |
| **线程安全** | 使用 `threading.RLock` 保护所有操作 |
| **惰性清理** | 访问时检查过期，无需定时任务 |

### 3.2 核心参数

```python
TTLCache(
    max_size: int = 1000,      # 最大条目数
    default_ttl: float = 300.0, # 默认过期时间（秒）
    sentinel: Any = object(),    # NULL 哨兵对象
)
```

### 3.3 全局缓存实例

| 缓存 | Key 格式 | 用途 | 默认 TTL | 最大条目 |
|------|---------|------|---------|---------|
| `_sql_result_cache` | `hash(sql)` | SQL 查询结果缓存 | 300s | 500 |
| `_llm_response_cache` | `hash(question + schema_version)` | LLM 生成结果缓存 | 600s | 200 |
| `_schema_cache` | 表名/配置名 | Schema 配置缓存 | 300s | 50 |

---

## 四、API 参考

### 4.1 TTLCache 方法

#### `get(key: str) -> T | None`

获取缓存值。

- **命中**：返回缓存值，移动到 LRU 末尾
- **过期**：自动删除，返回 `None`
- **未命中**：返回 `None`

```python
cache: TTLCache[list[dict]] = get_sql_result_cache()
result = cache.get("abc123")
```

#### `set(key: str, value: T | None, ttl: float | None = None) -> None`

设置缓存值。

- `value=None` 使用哨兵对象标记（防止穿透）
- `ttl=None` 使用默认 TTL

```python
cache.set("key", {"rows": [...]}, ttl=60.0)
cache.set("key", None)  # 标记为 NULL
```

#### `delete(key: str) -> bool`

删除指定条目，返回是否删除成功。

#### `clear() -> None`

清空整个缓存。

#### `cleanup_expired() -> int`

清理所有过期条目，返回清理数量。

#### `stats() -> dict`

获取缓存统计：

```python
{
    "size": 150,        # 当前条目数
    "max_size": 500,    # 最大条目数
    "total_hits": 2000, # 累计命中次数
}
```

### 4.2 辅助函数

#### `hash_sql(sql: str) -> str`

对 SQL 标准化后取 SHA-256 前 32 位作为缓存 Key：

```python
key = hash_sql("SELECT * FROM users WHERE id = 1")
# 标准化: "SELECT * FROM USERS WHERE ID = 1"
# 结果: "a3f2b8c1d4e5..."
```

#### `hash_llm_key(question: str, schema_version: str = "") -> str`

生成 LLM 缓存 Key（包含 schema 版本确保 schema 变更时失效）。

#### `invalidate_schema_cache() -> None`

主动失效所有 Schema 缓存（Schema 变更时调用）。

#### `reset_all_caches() -> None`

重置所有三级缓存（测试或配置变更时调用）。

---

## 五、Redis 可选支持

### 5.1 初始化

```python
from micro_genbi.monitoring.cache import init_redis, is_redis_available

success = init_redis(url="redis://localhost:6379")
# 连接成功返回 True，失败返回 False（自动降级到内存）
```

### 5.2 生产环境建议

| 环境 | 方案 | 说明 |
|------|------|------|
| 开发/测试 | 内存缓存 | 无额外依赖 |
| 小规模生产 | 内存缓存 | < 100 QPS |
| 中等规模生产 | Redis | 共享缓存，支持多实例 |
| 大规模生产 | Redis Cluster | 高可用 + 水平扩展 |

### 5.3 环境变量配置

```bash
# .env
REDIS_URL=redis://localhost:6379/0
```

---

## 六、缓存 Key 设计

### 6.1 SQL 结果缓存 Key

```
sql:{sha256_hash_of_normalized_sql}
```

示例：
```
sql:a3f2b8c1d4e5f6789012345678901234
```

### 6.2 LLM 响应缓存 Key

```
llm:{sha256_hash_of_question_and_schema_version}
```

示例：
```
llm:b4c3d2e1f0a9876543210987654321ab
```

### 6.3 Schema 缓存 Key

```
schema:{database_id}:{table_name}
```

示例：
```
schema:default:tank_inventory
schema:default:orders
```

---

## 七、使用场景

### 7.1 SQL 结果缓存

```python
from micro_genbi.monitoring.cache import (
    get_sql_result_cache, hash_sql, invalidate_schema_cache
)

cache = get_sql_result_cache()
key = hash_sql("SELECT * FROM orders WHERE status = 'completed'")

# 缓存命中
cached = cache.get(key)
if cached is not None:
    return cached

# 缓存未命中，执行查询
result = execute_query(key)
cache.set(key, result)

return result
```

### 7.2 Schema 变更时失效

```python
# 当 Schema 配置变更时
from micro_genbi.monitoring.cache import invalidate_schema_cache

async def update_schema(new_config: dict):
    await save_schema(new_config)
    invalidate_schema_cache()  # 清除所有 Schema 缓存
```

### 7.3 健康检查

```python
from micro_genbi.monitoring.cache import (
    get_sql_result_cache, get_llm_response_cache,
    get_schema_cache, is_redis_available
)

def get_cache_stats() -> dict:
    return {
        "sql_cache": get_sql_result_cache().stats(),
        "llm_cache": get_llm_response_cache().stats(),
        "schema_cache": get_schema_cache().stats(),
        "redis_available": is_redis_available(),
    }
```

---

## 八、配置参考

| 配置项 | 环境变量 | 默认值 | 说明 |
|--------|---------|--------|------|
| SQL 缓存 TTL | `SQL_CACHE_TTL` | 300 | 秒 |
| LLM 缓存 TTL | `LLM_CACHE_TTL` | 600 | 秒 |
| Schema 缓存 TTL | `SCHEMA_CACHE_TTL` | 300 | 秒 |
| SQL 缓存大小 | `SQL_CACHE_MAX_SIZE` | 500 | 条目数 |
| LLM 缓存大小 | `LLM_CACHE_MAX_SIZE` | 200 | 条目数 |
| Redis URL | `REDIS_URL` | None | 未设置则使用内存 |

---

## 九、监控指标

通过 `TTLCache.stats()` 可获取以下指标：

| 指标 | 说明 | 告警阈值建议 |
|------|------|-------------|
| `size` | 当前缓存条目数 | > 80% max_size |
| `max_size` | 配置的最大条目数 | — |
| `total_hits` | 累计命中次数 | — |

建议通过 `GET /groups/{group_id}/cache/stats` API 端点定期采集并上报到监控系统。
