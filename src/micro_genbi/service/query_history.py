"""查询历史与收藏服务

提供：
1. 查询历史存储与检索（SQLite 持久化）
2. 查询收藏与标签管理
3. 常用查询推荐
4. 历史记录清理策略
"""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Any
from contextlib import contextmanager

logger = logging.getLogger(__name__)


# ── 数据模型 ─────────────────────────────────────────────────

@dataclass
class QueryRecord:
    """查询记录"""
    id: int = 0
    user_id: str = "default"
    question: str = ""
    sql: str = ""
    db_profile: str = "default"
    intent_type: str = ""
    row_count: int = 0
    duration_ms: float = 0.0
    status: str = "success"         # success / failed / partial
    error_message: str = ""
    created_at: datetime = field(default_factory=datetime.now)
    starred: bool = False
    tags: list[str] = field(default_factory=list)
    session_id: str = ""
    metadata: dict = field(default_factory=dict)


@dataclass
class FavoriteQuery:
    """收藏查询"""
    id: int = 0
    user_id: str = "default"
    question: str = ""
    sql: str = ""
    description: str = ""
    tags: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    last_used: Optional[datetime] = None
    use_count: int = 0


# ── 数据库管理 ───────────────────────────────────────────────

class _HistoryDB:
    """查询历史 SQLite 数据库"""

    _instances: dict[str, _HistoryDB] = {}
    _lock = threading.Lock()

    def __init__(self, db_path: str):
        self.db_path = db_path
        self._local = threading.local()
        self._init_db()

    @classmethod
    def get_instance(cls, db_path: Optional[str] = None) -> _HistoryDB:
        """获取单例"""
        if db_path is None:
            db_path = cls._default_path()

        with cls._lock:
            if db_path not in cls._instances:
                cls._instances[db_path] = cls(db_path)
            return cls._instances[db_path]

    @classmethod
    def _default_path(cls) -> str:
        cache_dir = Path.home() / ".micro_genbi" / "data"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return str(cache_dir / "query_history.db")

    def _get_conn(self) -> sqlite3.Connection:
        """获取线程本地连接"""
        if not hasattr(self._local, "conn") or self._local.conn is None:
            self._local.conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._local.conn.row_factory = sqlite3.Row
            # 性能优化
            self._local.conn.execute("PRAGMA journal_mode=WAL")
            self._local.conn.execute("PRAGMA synchronous=NORMAL")
        return self._local.conn

    @contextmanager
    def _transaction(self):
        """事务上下文管理器"""
        conn = self._get_conn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    def _init_db(self) -> None:
        """初始化数据库表"""
        with self._transaction() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS query_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    question TEXT NOT NULL,
                    sql TEXT,
                    db_profile TEXT DEFAULT 'default',
                    intent_type TEXT DEFAULT '',
                    row_count INTEGER DEFAULT 0,
                    duration_ms REAL DEFAULT 0.0,
                    status TEXT DEFAULT 'success',
                    error_message TEXT DEFAULT '',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    starred INTEGER DEFAULT 0,
                    tags TEXT DEFAULT '[]',
                    session_id TEXT DEFAULT '',
                    metadata TEXT DEFAULT '{}'
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_user_id
                ON query_history(user_id, created_at DESC)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_history_starred
                ON query_history(user_id, starred)
            """)

            conn.execute("""
                CREATE TABLE IF NOT EXISTS favorite_queries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL DEFAULT 'default',
                    question TEXT NOT NULL,
                    sql TEXT,
                    description TEXT DEFAULT '',
                    tags TEXT DEFAULT '[]',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_used TIMESTAMP,
                    use_count INTEGER DEFAULT 0
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_favorite_user_id
                ON favorite_queries(user_id, created_at DESC)
            """)

        logger.info(f"查询历史数据库已初始化: {self.db_path}")


# ── 查询历史服务 ─────────────────────────────────────────────

class QueryHistory:
    """
    查询历史服务

    功能：
    - 记录每次查询（question, sql, duration, status）
    - 按用户/时间/意图检索历史
    - 星标重要查询
    - 自动清理过期记录（默认保留 90 天）
    """

    def __init__(
        self,
        db_path: Optional[str] = None,
        retention_days: int = 90,
    ):
        self._db = _HistoryDB.get_instance(db_path)
        self._retention_days = retention_days

    def record(
        self,
        question: str,
        sql: str,
        user_id: str = "default",
        db_profile: str = "default",
        intent_type: str = "",
        row_count: int = 0,
        duration_ms: float = 0.0,
        status: str = "success",
        error_message: str = "",
        session_id: str = "",
        metadata: Optional[dict] = None,
    ) -> int:
        """
        记录一条查询

        Returns:
            新记录的 id
        """
        with self._db._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO query_history
                (user_id, question, sql, db_profile, intent_type, row_count,
                 duration_ms, status, error_message, session_id, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', ?)
                """,
                (
                    user_id,
                    question,
                    sql,
                    db_profile,
                    intent_type,
                    row_count,
                    duration_ms,
                    status,
                    error_message,
                    session_id,
                    json.dumps(metadata or {}, ensure_ascii=False),
                ),
            )
            record_id = cursor.lastrowid

        logger.debug(f"查询记录已保存: id={record_id}, question={question[:50]}")
        return record_id

    def get_history(
        self,
        user_id: str = "default",
        limit: int = 50,
        offset: int = 0,
        starred_only: bool = False,
        intent_type: Optional[str] = None,
        search: Optional[str] = None,
    ) -> list[QueryRecord]:
        """
        获取查询历史

        Args:
            user_id: 用户 ID
            limit: 返回条数
            offset: 偏移量
            starred_only: 仅返回星标
            intent_type: 按意图类型过滤
            search: 搜索关键词

        Returns:
            QueryRecord 列表
        """
        conn = self._db._get_conn()
        query = "SELECT * FROM query_history WHERE user_id = ?"
        params: list[Any] = [user_id]

        if starred_only:
            query += " AND starred = 1"
        if intent_type:
            query += " AND intent_type = ?"
            params.append(intent_type)
        if search:
            query += " AND (question LIKE ? OR sql LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([limit, offset])

        rows = conn.execute(query, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def star(self, record_id: int, starred: bool = True) -> bool:
        """星标/取消星标查询"""
        conn = self._db._get_conn()
        cursor = conn.execute(
            "UPDATE query_history SET starred = ? WHERE id = ?",
            (1 if starred else 0, record_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def delete(self, record_id: int) -> bool:
        """删除记录"""
        conn = self._db._get_conn()
        cursor = conn.execute(
            "DELETE FROM query_history WHERE id = ?",
            (record_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def clear_old(self, user_id: str = "default") -> int:
        """
        清理过期记录

        Args:
            user_id: 用户 ID（None 表示所有用户）

        Returns:
            清理的记录数
        """
        cutoff = datetime.now() - timedelta(days=self._retention_days)
        conn = self._db._get_conn()

        if user_id:
            cursor = conn.execute(
                "DELETE FROM query_history WHERE user_id = ? AND created_at < ? AND starred = 0",
                (user_id, cutoff),
            )
        else:
            cursor = conn.execute(
                "DELETE FROM query_history WHERE created_at < ? AND starred = 0",
                (cutoff,),
            )
        conn.commit()
        removed = cursor.rowcount
        if removed > 0:
            logger.info(f"已清理 {removed} 条过期查询记录")
        return removed

    def get_stats(self, user_id: str = "default") -> dict[str, Any]:
        """获取用户查询统计"""
        conn = self._db._get_conn()
        row = conn.execute(
            """
            SELECT
                COUNT(*) as total,
                SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) as success_count,
                SUM(CASE WHEN starred = 1 THEN 1 ELSE 0 END) as starred_count,
                AVG(duration_ms) as avg_duration_ms,
                SUM(row_count) as total_rows
            FROM query_history
            WHERE user_id = ?
            """,
            (user_id,),
        ).fetchone()

        return {
            "total_queries": row["total"] or 0,
            "success_count": row["success_count"] or 0,
            "starred_count": row["starred_count"] or 0,
            "avg_duration_ms": round(row["avg_duration_ms"] or 0, 2),
            "total_rows": row["total_rows"] or 0,
        }

    def _row_to_record(self, row: sqlite3.Row) -> QueryRecord:
        """将数据库行转换为 QueryRecord"""
        return QueryRecord(
            id=row["id"],
            user_id=row["user_id"],
            question=row["question"],
            sql=row["sql"] or "",
            db_profile=row["db_profile"],
            intent_type=row["intent_type"] or "",
            row_count=row["row_count"] or 0,
            duration_ms=row["duration_ms"] or 0.0,
            status=row["status"] or "success",
            error_message=row["error_message"] or "",
            created_at=datetime.fromisoformat(row["created_at"]),
            starred=bool(row["starred"]),
            tags=json.loads(row["tags"] or "[]"),
            session_id=row["session_id"] or "",
            metadata=json.loads(row["metadata"] or "{}"),
        )


# ── 收藏服务 ─────────────────────────────────────────────────

class QueryFavorites:
    """
    查询收藏服务

    功能：
    - 保存/删除收藏查询
    - 按标签分类
    - 记录使用次数
    - 导出收藏为模板
    """

    def __init__(self, db_path: Optional[str] = None):
        self._db = _HistoryDB.get_instance(db_path)

    def add(
        self,
        question: str,
        sql: str,
        user_id: str = "default",
        description: str = "",
        tags: Optional[list[str]] = None,
    ) -> int:
        """
        添加收藏

        Returns:
            收藏记录的 id
        """
        with self._db._transaction() as conn:
            cursor = conn.execute(
                """
                INSERT INTO favorite_queries
                (user_id, question, sql, description, tags)
                VALUES (?, ?, ?, ?, ?)
                """,
                (user_id, question, sql, description, json.dumps(tags or [], ensure_ascii=False)),
            )
            fav_id = cursor.lastrowid
        logger.debug(f"查询已收藏: id={fav_id}, question={question[:50]}")
        return fav_id

    def remove(self, fav_id: int) -> bool:
        """移除收藏"""
        conn = self._db._get_conn()
        cursor = conn.execute(
            "DELETE FROM favorite_queries WHERE id = ?",
            (fav_id,),
        )
        conn.commit()
        return cursor.rowcount > 0

    def list_favorites(
        self,
        user_id: str = "default",
        tags: Optional[list[str]] = None,
        search: Optional[str] = None,
        limit: int = 50,
    ) -> list[FavoriteQuery]:
        """列出收藏"""
        conn = self._db._get_conn()
        query = "SELECT * FROM favorite_queries WHERE user_id = ?"
        params: list[Any] = [user_id]

        if search:
            query += " AND (question LIKE ? OR description LIKE ?)"
            params.extend([f"%{search}%", f"%{search}%"])

        query += " ORDER BY use_count DESC, created_at DESC LIMIT ?"
        params.append(limit)

        rows = conn.execute(query, params).fetchall()
        favorites = [self._row_to_favorite(row) for row in rows]

        if tags:
            favorites = [
                f for f in favorites
                if any(t in f.tags for t in tags)
            ]
        return favorites

    def record_usage(self, fav_id: int) -> None:
        """记录一次使用"""
        conn = self._db._get_conn()
        conn.execute(
            """
            UPDATE favorite_queries
            SET use_count = use_count + 1, last_used = ?
            WHERE id = ?
            """,
            (datetime.now(), fav_id),
        )
        conn.commit()

    def update_tags(self, fav_id: int, tags: list[str]) -> bool:
        """更新标签"""
        conn = self._db._get_conn()
        cursor = conn.execute(
            "UPDATE favorite_queries SET tags = ? WHERE id = ?",
            (json.dumps(tags, ensure_ascii=False), fav_id),
        )
        conn.commit()
        return cursor.rowcount > 0

    def get_all_tags(self, user_id: str = "default") -> list[str]:
        """获取用户所有标签"""
        conn = self._db._get_conn()
        rows = conn.execute(
            "SELECT tags FROM favorite_queries WHERE user_id = ?",
            (user_id,),
        ).fetchall()
        tag_set = set()
        for row in rows:
            tag_set.update(json.loads(row["tags"] or "[]"))
        return sorted(tag_set)

    def _row_to_favorite(self, row: sqlite3.Row) -> FavoriteQuery:
        """将数据库行转换为 FavoriteQuery"""
        return FavoriteQuery(
            id=row["id"],
            user_id=row["user_id"],
            question=row["question"],
            sql=row["sql"] or "",
            description=row["description"] or "",
            tags=json.loads(row["tags"] or "[]"),
            created_at=datetime.fromisoformat(row["created_at"]),
            last_used=datetime.fromisoformat(row["last_used"]) if row["last_used"] else None,
            use_count=row["use_count"] or 0,
        )


# ── 便捷函数 ─────────────────────────────────────────────────

_history_singleton: Optional[QueryHistory] = None
_favorites_singleton: Optional[QueryFavorites] = None
_singleton_lock = threading.Lock()


def get_query_history(retention_days: int = 90) -> QueryHistory:
    """获取 QueryHistory 单例"""
    global _history_singleton
    if _history_singleton is None:
        with _singleton_lock:
            if _history_singleton is None:
                _history_singleton = QueryHistory(retention_days=retention_days)
    return _history_singleton


def get_query_favorites() -> QueryFavorites:
    """获取 QueryFavorites 单例"""
    global _favorites_singleton
    if _favorites_singleton is None:
        with _singleton_lock:
            if _favorites_singleton is None:
                _favorites_singleton = QueryFavorites()
    return _favorites_singleton
