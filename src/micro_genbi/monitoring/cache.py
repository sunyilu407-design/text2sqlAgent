"""三级缓存策略

提供三层缓存：
1. SQL 结果缓存（内存 dict，TTL 300s）
2. LLM 响应缓存（相同 SQL 直接返回）
3. Schema 配置缓存（启动时全量加载，变更时失效）

可选 Redis 支持（生产环境）。
"""

from __future__ import annotations

import hashlib
import threading
import time
import logging
from typing import Optional, Any, Generic, TypeVar
from dataclasses import dataclass
from collections import OrderedDict

logger = logging.getLogger(__name__)

T = TypeVar("T")


@dataclass
class CacheEntry(Generic[T]):
    """缓存条目"""
    value: T
    created_at: float
    expires_at: float
    hit_count: int = 0

    def is_expired(self, now: float | None = None) -> bool:
        if now is None:
            now = time.time()
        return now >= self.expires_at


class TTLCache(Generic[T]):
    """
    TTL + LRU 内存缓存

    特性：
    - TTL 过期（默认 300s）
    - LRU 淘汰（超过 max_size 时淘汰最旧条目）
    - 线程安全
    - NULL 值标记（防止缓存穿透）
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: float = 300.0,
        sentinel: Any = object(),
    ):
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._sentinel = sentinel  # 用于标记 NULL 值
        self._cache: OrderedDict[str, CacheEntry[T]] = OrderedDict()
        self._lock = threading.RLock()

    def _make_key(self, key: str) -> str:
        """生成缓存 key（支持前缀隔离）"""
        return key

    def get(self, key: str) -> T | None:
        """获取缓存值"""
        with self._lock:
            entry = self._cache.get(key)
            if entry is None:
                return None

            now = time.time()
            if entry.is_expired(now):
                del self._cache[key]
                return None

            # LRU: 移到末尾
            self._cache.move_to_end(key)
            entry.hit_count += 1
            if entry.value is self._sentinel:
                return None
            return entry.value

    def set(
        self,
        key: str,
        value: T | None,
        ttl: float | None = None,
    ) -> None:
        """设置缓存值"""
        if value is None:
            value = self._sentinel  # NULL 值用哨兵标记

        ttl = ttl if ttl is not None else self._default_ttl
        now = time.time()

        with self._lock:
            # 如果已存在，先删除再添加（更新位置到末尾）
            if key in self._cache:
                del self._cache[key]

            # LRU 淘汰
            while len(self._cache) >= self._max_size:
                evicted_key = next(iter(self._cache))
                del self._cache[evicted_key]
                logger.debug(f"LRU 淘汰: {evicted_key}")

            self._cache[key] = CacheEntry(
                value=value,
                created_at=now,
                expires_at=now + ttl,
            )

    def delete(self, key: str) -> bool:
        """删除缓存条目"""
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                return True
            return False

    def clear(self) -> None:
        """清空缓存"""
        with self._lock:
            self._cache.clear()

    def cleanup_expired(self) -> int:
        """清理过期条目，返回清理数量"""
        removed = 0
        now = time.time()
        with self._lock:
            expired_keys = [
                k for k, v in self._cache.items()
                if v.is_expired(now)
            ]
            for k in expired_keys:
                del self._cache[k]
                removed += 1
        return removed

    def stats(self) -> dict[str, Any]:
        """获取缓存统计"""
        with self._lock:
            total_hits = sum(e.hit_count for e in self._cache.values())
            return {
                "size": len(self._cache),
                "max_size": self._max_size,
                "total_hits": total_hits,
            }


# ── 全局缓存实例 ──────────────────────────────────────────────

# SQL 结果缓存（key: hash(sql)）
_sql_result_cache: TTLCache[list[dict]] | None = None
_cache_lock = threading.Lock()


def get_sql_result_cache() -> TTLCache[list[dict]]:
    """获取 SQL 结果缓存（延迟创建）"""
    global _sql_result_cache
    if _sql_result_cache is None:
        with _cache_lock:
            if _sql_result_cache is None:
                _sql_result_cache = TTLCache[list[dict]](
                    max_size=500,
                    default_ttl=300.0,
                )
                logger.info("SQL 结果缓存已初始化（max=500, ttl=300s）")
    return _sql_result_cache


# LLM 响应缓存（key: hash(question + schema_version)）
_llm_response_cache: TTLCache[str] | None = None


def get_llm_response_cache() -> TTLCache[str]:
    """获取 LLM 响应缓存（延迟创建）"""
    global _llm_response_cache
    if _llm_response_cache is None:
        with _cache_lock:
            if _llm_response_cache is None:
                _llm_response_cache = TTLCache[str](
                    max_size=200,
                    default_ttl=600.0,
                )
                logger.info("LLM 响应缓存已初始化（max=200, ttl=600s）")
    return _llm_response_cache


# Schema 缓存（TTL 300s，变更时主动失效）
_schema_cache: TTLCache[dict] | None = None


def get_schema_cache() -> TTLCache[dict]:
    """获取 Schema 缓存（延迟创建）"""
    global _schema_cache
    if _schema_cache is None:
        with _cache_lock:
            if _schema_cache is None:
                _schema_cache = TTLCache[dict](
                    max_size=50,
                    default_ttl=300.0,
                )
                logger.info("Schema 配置缓存已初始化（max=50, ttl=300s）")
    return _schema_cache


# ── 缓存辅助函数 ──────────────────────────────────────────────

def hash_sql(sql: str) -> str:
    """对 SQL 进行哈希（用于缓存 key）"""
    normalized = sql.strip().upper()
    return hashlib.sha256(normalized.encode()).hexdigest()[:32]


def hash_llm_key(question: str, schema_version: str = "") -> str:
    """生成 LLM 缓存 key"""
    combined = f"{question}|{schema_version}"
    return hashlib.sha256(combined.encode()).hexdigest()[:32]


def invalidate_schema_cache() -> None:
    """主动失效 Schema 缓存"""
    cache = get_schema_cache()
    cache.clear()
    logger.info("Schema 缓存已失效")


# ── Redis 可选支持 ──────────────────────────────────────────────

_redis_client: Optional[Any] = None


def init_redis(url: str | None = None) -> bool:
    """
    初始化 Redis 客户端（可选，用于生产环境）

    Returns:
        True 如果 Redis 连接成功，False 否则
    """
    global _redis_client
    if url is None:
        return False

    try:
        import redis
        _redis_client = redis.from_url(url)
        _redis_client.ping()
        logger.info("Redis 缓存已连接")
        return True
    except Exception as e:
        logger.warning(f"Redis 连接失败，使用内存缓存: {e}")
        _redis_client = None
        return False


def is_redis_available() -> bool:
    """检查 Redis 是否可用"""
    if _redis_client is None:
        return False
    try:
        _redis_client.ping()
        return True
    except Exception:
        return False


def reset_all_caches() -> None:
    """重置所有缓存（用于测试或配置变更时）"""
    get_sql_result_cache().clear()
    get_llm_response_cache().clear()
    get_schema_cache().clear()
    logger.info("所有缓存已重置")
