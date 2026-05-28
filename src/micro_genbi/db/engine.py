"""Micro-GenBI 数据库引擎模块

SQLAlchemy Engine 工厂，支持多数据库类型和异步执行。
"""

from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from typing import Optional, Any, AsyncIterator
from functools import lru_cache

from sqlalchemy import create_engine, text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    create_async_engine,
    async_sessionmaker,
)
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.pool import (
    NullPool,
    QueuePool,
    AsyncAdaptedQueuePool,
)
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import URL

from micro_genbi.models import DatabaseType
from micro_genbi.db.config import DatabaseProfile, get_database_config


class DatabaseEngineFactory:
    """
    数据库引擎工厂

    创建并管理 SQLAlchemy Engine 实例。
    """

    _engines: dict[str, AsyncEngine] = {}
    _sync_engines: dict[str, Engine] = {}

    @classmethod
    def create_async_engine(
        cls,
        profile: Optional[DatabaseProfile] = None,
        name: Optional[str] = None,
        **kwargs,
    ) -> AsyncEngine:
        """
        创建异步引擎

        Args:
            profile: 数据库配置
            name: 配置名称（用于多库模式）
            **kwargs: 额外参数
        """
        if profile is None:
            profile = get_database_config(name)

        engine_key = f"{name or 'default'}_async"

        # 检查缓存
        if engine_key in cls._engines:
            return cls._engines[engine_key]

        # 创建引擎
        url = profile.get_url()

        # 连接池配置
        pool_class = AsyncAdaptedQueuePool
        pool_size = profile.pool_size
        max_overflow = profile.max_overflow
        pool_timeout = profile.pool_timeout
        pool_recycle = profile.pool_recycle
        pool_pre_ping = profile.pool_pre_ping

        # SQLite 不使用连接池
        if profile.type == DatabaseType.SQLITE:
            pool_class = NullPool

        engine = create_async_engine(
            url,
            poolclass=pool_class,
            pool_size=pool_size,
            max_overflow=max_overflow,
            pool_timeout=pool_timeout,
            pool_recycle=pool_recycle,
            pool_pre_ping=pool_pre_ping,
            echo=kwargs.get("echo", False),
            **kwargs,
        )

        cls._engines[engine_key] = engine
        return engine

    @classmethod
    def create_sync_engine(
        cls,
        profile: Optional[DatabaseProfile] = None,
        name: Optional[str] = None,
        **kwargs,
    ) -> Engine:
        """
        创建同步引擎

        Args:
            profile: 数据库配置
            name: 配置名称（用于多库模式）
            **kwargs: 额外参数
        """
        if profile is None:
            profile = get_database_config(name)

        engine_key = f"{name or 'default'}_sync"

        # 检查缓存
        if engine_key in cls._sync_engines:
            return cls._sync_engines[engine_key]

        # 创建引擎
        url = profile.get_sync_url()

        # 连接池配置
        pool_class = QueuePool
        if profile.type == DatabaseType.SQLITE:
            pool_class = NullPool

        engine = create_engine(
            url,
            poolclass=pool_class,
            pool_size=profile.pool_size,
            max_overflow=profile.max_overflow,
            pool_timeout=profile.pool_timeout,
            pool_recycle=profile.pool_recycle,
            pool_pre_ping=profile.pool_pre_ping,
            echo=kwargs.get("echo", False),
            **kwargs,
        )

        cls._sync_engines[engine_key] = engine
        return engine

    @classmethod
    def get_async_engine(cls, name: Optional[str] = None) -> AsyncEngine:
        """获取异步引擎"""
        engine_key = f"{name or 'default'}_async"
        if engine_key not in cls._engines:
            return cls.create_async_engine(name=name)
        return cls._engines[engine_key]

    @classmethod
    def get_sync_engine(cls, name: Optional[str] = None) -> Engine:
        """获取同步引擎"""
        engine_key = f"{name or 'default'}_sync"
        if engine_key not in cls._sync_engines:
            return cls.create_sync_engine(name=name)
        return cls._sync_engines[engine_key]

    @classmethod
    def create_session_factory(
        cls,
        engine: Optional[AsyncEngine] = None,
        name: Optional[str] = None,
        expire_on_commit: bool = False,
    ) -> async_sessionmaker[AsyncSession]:
        """创建会话工厂"""
        if engine is None:
            engine = cls.get_async_engine(name)

        return async_sessionmaker(
            bind=engine,
            class_=AsyncSession,
            expire_on_commit=expire_on_commit,
            autoflush=False,
            autocommit=False,
        )

    @classmethod
    def dispose_all(cls) -> None:
        """释放所有引擎"""
        for engine in cls._engines.values():
            asyncio.create_task(engine.dispose())
        cls._engines.clear()

        for engine in cls._sync_engines.values():
            engine.dispose()
        cls._sync_engines.clear()


class DatabaseExecutor:
    """
    异步数据库执行器

    提供简洁的数据库操作接口。
    """

    def __init__(
        self,
        session_factory: Optional[async_sessionmaker[AsyncSession]] = None,
        name: Optional[str] = None,
    ):
        self._session_factory = session_factory
        self._name = name

    @property
    def session_factory(self) -> async_sessionmaker[AsyncSession]:
        """获取会话工厂"""
        if self._session_factory is None:
            engine = DatabaseEngineFactory.get_async_engine(self._name)
            self._session_factory = DatabaseEngineFactory.create_session_factory(engine)
        return self._session_factory

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """获取数据库会话（上下文管理器）"""
        async with self.session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    async def execute(
        self,
        sql: str,
        params: Optional[dict] = None,
        timeout: Optional[int] = None,
    ) -> list[dict[str, Any]]:
        """
        执行 SQL 查询并返回结果

        Args:
            sql: SQL 语句
            params: 参数（用于参数化查询）
            timeout: 超时时间（秒）

        Returns:
            查询结果列表
        """
        async with self.session() as session:
            result = await session.execute(text(sql), params or {})
            columns = result.keys()
            rows = result.fetchall()
            return [dict(zip(columns, row)) for row in rows]

    async def execute_one(
        self,
        sql: str,
        params: Optional[dict] = None,
    ) -> Optional[dict[str, Any]]:
        """执行 SQL 查询并返回单条结果"""
        async with self.session() as session:
            result = await session.execute(text(sql), params or {})
            row = result.fetchone()
            if row:
                return dict(zip(result.keys(), row))
            return None

    async def execute_scalar(
        self,
        sql: str,
        params: Optional[dict] = None,
    ) -> Any:
        """执行 SQL 查询并返回标量值"""
        async with self.session() as session:
            result = await session.execute(text(sql), params or {})
            return result.scalar()

    async def test_connection(self) -> bool:
        """测试数据库连接"""
        try:
            await self.execute_scalar("SELECT 1")
            return True
        except Exception:
            return False

    async def get_table_names(self) -> list[str]:
        """获取所有表名"""
        config = get_database_config(self._name)
        if config.type == DatabaseType.POSTGRESQL:
            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :schema
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """
            params = {"schema": config.schema or "public"}
        elif config.type == DatabaseType.MYSQL:
            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = :database
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """
            params = {"database": config.database}
        else:
            # 通用实现
            sql = "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
            params = {}

        results = await self.execute(sql, params)
        return [r["table_name" if "table_name" in r else "name"] for r in results]

    async def get_table_columns(self, table_name: str) -> list[dict[str, Any]]:
        """获取表的列信息"""
        config = get_database_config(self._name)
        if config.type == DatabaseType.POSTGRESQL:
            sql = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = :schema
                AND table_name = :table
                ORDER BY ordinal_position
            """
            params = {"schema": config.schema or "public", "table": table_name}
        elif config.type == DatabaseType.MYSQL:
            sql = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length
                FROM information_schema.columns
                WHERE table_schema = :database
                AND table_name = :table
                ORDER BY ordinal_position
            """
            params = {"database": config.database, "table": table_name}
        else:
            return []

        return await self.execute(sql, params)

    async def get_table_count(self, table_name: str) -> int:
        """获取表的行数"""
        sql = f"SELECT COUNT(*) as cnt FROM {table_name}"
        result = await self.execute_one(sql)
        return result["cnt"] if result else 0


async def get_engine(connection_id: str) -> Any:
    """
    根据 connection_id 从系统数据库获取配置，创建业务数据库引擎。

    这是一个工厂函数，从系统数据库读取 DatabaseConnection 记录，
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
        return DatabaseEngineFactory.create_async_engine(profile, name=connection_id)


# =============================================================================
# 全局执行器
# =============================================================================

@lru_cache()
def get_executor(name: Optional[str] = None) -> DatabaseExecutor:
    """获取全局执行器（带缓存）"""
    return DatabaseExecutor(name=name)
