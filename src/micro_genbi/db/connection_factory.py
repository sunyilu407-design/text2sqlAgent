"""多数据库连接工厂

按 connection_id 管理多个业务数据库引擎，支持多库并发查询。

设计原则：
- 引擎懒加载：首次访问时才创建
- 连接池隔离：每个 connection_id 独立的连接池
- 自动释放：长时间不用的引擎自动清理
- 并发安全：使用锁保护引擎字典
"""

from __future__ import annotations

import asyncio
import time
from contextlib import asynccontextmanager
from typing import Optional, Any, AsyncIterator
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from micro_genbi.models import DatabaseType
from micro_genbi.db.config import DatabaseProfile
from micro_genbi.db.engine import DatabaseEngineFactory


@dataclass
class EngineMetadata:
    """引擎元数据"""
    engine: AsyncEngine
    connection_id: str
    connection_name: str
    db_type: str
    profile: DatabaseProfile
    created_at: float = field(default_factory=time.time)
    last_used: float = field(default_factory=time.time)


class MultiDBConnectionFactory:
    """
    多数据库连接工厂。

    核心职责：
    1. 按 connection_id 管理多个 SQLAlchemy AsyncEngine
    2. 为每个引擎创建对应的执行器（DatabaseExecutor）
    3. 提供并发执行接口
    4. 自动清理闲置引擎

    使用方式：
        factory = MultiDBConnectionFactory()

        # 创建/获取引擎
        executor = await factory.get_executor(connection_id="uuid-xxx")

        # 并发执行多个查询
        results = await factory.execute_all([
            (conn_id_a, sql_a),
            (conn_id_b, sql_b),
        ])
    """

    _instance: Optional[MultiDBConnectionFactory] = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __init__(self, max_idle_seconds: int = 300):
        """
        Args:
            max_idle_seconds: 引擎闲置超过此时间后自动释放（默认 5 分钟）
        """
        self._engines: dict[str, EngineMetadata] = {}
        self._session_factories: dict[str, async_sessionmaker[AsyncSession]] = {}
        self._executor_cache: dict[str, Any] = {}
        self._max_idle_seconds = max_idle_seconds
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    @classmethod
    def get_instance(cls) -> "MultiDBConnectionFactory":
        """获取单例实例"""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def _create_engine(self, connection_id: str) -> EngineMetadata:
        """
        根据 connection_id 创建引擎。

        从系统数据库（DatabaseConnection）读取配置，
        然后创建对应的业务数据库引擎。
        """
        from micro_genbi.database import get_db_session
        from micro_genbi.database import DatabaseConnectionService

        async for session in get_db_session():
            db_service = DatabaseConnectionService(session)
            conn = await db_service.get_by_id(connection_id)
            if not conn:
                raise ValueError(f"Connection not found: {connection_id}")

            profile = DatabaseProfile(
                name=conn.name,
                type=DatabaseType(conn.db_type),
                host=conn.host or "localhost",
                port=conn.port or 5432,
                database=conn.database_name,
                username=conn.username or "",
                password=conn.password_encrypted or "",
                charset=conn.charset or "utf8mb4",
                pool_size=conn.pool_size or 5,
                max_overflow=conn.max_overflow or 10,
            )

            engine = DatabaseEngineFactory.create_async_engine(
                profile, name=connection_id
            )
            session_factory = DatabaseEngineFactory.create_session_factory(
                engine, name=connection_id
            )

            metadata = EngineMetadata(
                engine=engine,
                connection_id=connection_id,
                connection_name=conn.name,
                db_type=conn.db_type,
                profile=profile,
            )
            self._session_factories[connection_id] = session_factory
            return metadata

        raise RuntimeError("Failed to get database session")

    async def get_engine(self, connection_id: str) -> AsyncEngine:
        """获取指定 connection_id 的引擎（懒加载）"""
        async with self._lock:
            if connection_id in self._engines:
                self._engines[connection_id].last_used = time.time()
                return self._engines[connection_id].engine

            metadata = await self._create_engine(connection_id)
            self._engines[connection_id] = metadata
            return metadata.engine

    async def get_session_factory(
        self, connection_id: str
    ) -> async_sessionmaker[AsyncSession]:
        """获取指定 connection_id 的会话工厂"""
        await self.get_engine(connection_id)
        return self._session_factories[connection_id]

    @asynccontextmanager
    async def session(
        self, connection_id: str
    ) -> AsyncIterator[AsyncSession]:
        """获取指定连接的事务会话"""
        factory = await self.get_session_factory(connection_id)
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def execute(
        self,
        connection_id: str,
        sql: str,
        params: Optional[dict] = None,
    ) -> list[dict[str, Any]]:
        """
        在指定连接上执行 SQL。

        Args:
            connection_id: 数据库连接 ID
            sql: SQL 语句
            params: 参数化查询参数

        Returns:
            查询结果列表
        """
        from sqlalchemy import text

        async with self.session(connection_id) as session:
            result = await session.execute(text(sql), params or {})
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def execute_all(
        self, queries: list[tuple[str, str]]
    ) -> list[list[dict[str, Any]]]:
        """
        并发执行多个查询（每个在不同连接上）。

        Args:
            queries: [(connection_id, sql), ...]

        Returns:
            结果列表，与输入顺序对应
        """
        tasks = [self.execute(conn_id, sql) for conn_id, sql in queries]
        return await asyncio.gather(*tasks, return_exceptions=True)

    async def test_connection(self, connection_id: str) -> dict[str, Any]:
        """
        测试数据库连接。

        Returns:
            {"success": bool, "latency_ms": float, "tables_count": int, "error": str|None}
        """
        from sqlalchemy import text

        start = time.time()
        try:
            async with self.session(connection_id) as session:
                await session.execute(text("SELECT 1"))
            latency_ms = int((time.time() - start) * 1000)

            # 尝试获取表数量
            tables_count = 0
            try:
                config = self._engines.get(connection_id)
                if config and config.db_type == "postgresql":
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                    ))
                elif config and config.db_type == "mysql":
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM information_schema.tables "
                        "WHERE table_schema = DATABASE() AND table_type = 'BASE TABLE'"
                    ))
                else:
                    result = await session.execute(text(
                        "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
                    ))
                tables_count = result.scalar() or 0
            except Exception:
                pass

            return {
                "success": True,
                "latency_ms": latency_ms,
                "tables_count": tables_count,
                "error": None,
            }
        except Exception as e:
            return {
                "success": False,
                "latency_ms": int((time.time() - start) * 1000),
                "tables_count": 0,
                "error": str(e),
            }

    def get_stats(self) -> dict[str, Any]:
        """获取连接工厂统计信息"""
        return {
            "engine_count": len(self._engines),
            "connections": [
                {
                    "id": meta.connection_id,
                    "name": meta.connection_name,
                    "db_type": meta.db_type,
                    "idle_seconds": int(time.time() - meta.last_used),
                    "created_seconds": int(time.time() - meta.created_at),
                }
                for meta in self._engines.values()
            ],
        }

    async def dispose_engine(self, connection_id: str) -> None:
        """释放指定引擎"""
        async with self._lock:
            if connection_id in self._engines:
                engine = self._engines[connection_id].engine
                await engine.dispose()
                del self._engines[connection_id]
                self._session_factories.pop(connection_id, None)
                self._executor_cache.pop(connection_id, None)

    async def dispose_all(self) -> None:
        """释放所有引擎"""
        async with self._lock:
            for metadata in self._engines.values():
                await metadata.engine.dispose()
            self._engines.clear()
            self._session_factories.clear()
            self._executor_cache.clear()

    # ── 闲置引擎自动清理 ──────────────────────────────────────────────

    async def _cleanup_loop(self) -> None:
        """后台清理闲置引擎"""
        while self._running:
            try:
                await asyncio.sleep(60)
                await self._cleanup_idle()
            except asyncio.CancelledError:
                break
            except Exception:
                pass

    async def _cleanup_idle(self) -> None:
        """清理闲置引擎"""
        now = time.time()
        to_dispose = []

        async with self._lock:
            for conn_id, meta in self._engines.items():
                if now - meta.last_used > self._max_idle_seconds:
                    to_dispose.append(conn_id)

        for conn_id in to_dispose:
            await self.dispose_engine(conn_id)
            import logging
            logging.getLogger(__name__).debug(
                f"Disposed idle engine: {conn_id}"
            )

    def start_cleanup(self) -> None:
        """启动后台清理任务"""
        if not self._running:
            self._running = True
            self._cleanup_task = asyncio.create_task(self._cleanup_loop())

    async def stop_cleanup(self) -> None:
        """停止后台清理任务"""
        self._running = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass


def get_multi_db_factory() -> MultiDBConnectionFactory:
    """获取全局多库连接工厂（与 FastAPI 生命周期绑定）"""
    return MultiDBConnectionFactory.get_instance()
