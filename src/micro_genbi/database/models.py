"""系统数据库 ORM 模型

使用 SQLAlchemy 定义系统数据库结构。
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from enum import Enum

from sqlalchemy import (
    Column, String, Text, Boolean, Integer, DateTime,
    ForeignKey, JSON, UniqueConstraint, Index, CheckConstraint,
    create_engine, func,
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, Session
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.pool import NullPool

Base = declarative_base()


class UserRole(str, Enum):
    """用户角色"""
    ADMIN = "admin"
    USER = "user"
    READONLY = "readonly"


class TenantMemberRole(str, Enum):
    """租户成员角色"""
    ADMIN = "admin"
    MEMBER = "member"


class LLMProvider(str, Enum):
    """LLM 提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    OLLAMA = "ollama"


class DatabaseType(str, Enum):
    """数据库类型"""
    POSTGRESQL = "postgresql"
    MYSQL = "mysql"
    SQLITE = "sqlite"
    CLICKHOUSE = "clickhouse"


class QueryStatus(str, Enum):
    """查询状态"""
    SUCCESS = "success"
    FAILED = "failed"
    BLOCKED = "blocked"


# =============================================================================
# 租户/用户相关模型
# =============================================================================

class Tenant(Base):
    """租户/用户组"""
    __tablename__ = "tenants"

    id = Column(String(36), primary_key=True)
    name = Column(String(255), nullable=False, unique=True)
    description = Column(Text)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    users = relationship("User", back_populates="tenant")
    members = relationship("TenantMember", back_populates="tenant", cascade="all, delete-orphan")
    llm_configs = relationship("LLMConfig", back_populates="tenant", cascade="all, delete-orphan")
    database_connections = relationship("DatabaseConnection", back_populates="tenant", cascade="all, delete-orphan")
    schema_configs = relationship("SchemaConfig", back_populates="tenant", cascade="all, delete-orphan")
    api_keys = relationship("APIKey", back_populates="tenant", cascade="all, delete-orphan")
    projects = relationship("Project", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    """用户"""
    __tablename__ = "users"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    username = Column(String(100), nullable=False, unique=True)
    email = Column(String(255), unique=True)
    password_hash = Column(String(255), nullable=False)
    role = Column(String(50), default=UserRole.USER.value)
    is_active = Column(Boolean, default=True)
    last_login_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="users")
    query_history = relationship("QueryHistory", back_populates="user")
    sessions = relationship("Session", back_populates="user")
    api_keys = relationship("APIKey", back_populates="user")

    __table_args__ = (
        Index("idx_users_tenant", "tenant_id"),
        Index("idx_users_username", "username"),
    )


class TenantMember(Base):
    """租户成员"""
    __tablename__ = "tenant_members"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    role = Column(String(50), default=TenantMemberRole.MEMBER.value)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="members")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_member"),
        Index("idx_members_tenant", "tenant_id"),
        Index("idx_members_user", "user_id"),
    )


# =============================================================================
# 项目分组
# =============================================================================

class Project(Base):
    """项目

    用于对数据源进行分组管理。
    例如：油库生产系统、财务系统、HR系统等。
    """
    __tablename__ = "projects"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    icon = Column(String(50), default="📁")  # 图标
    color = Column(String(20), default="#4CAF50")  # 颜色
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="projects")
    database_connections = relationship("DatabaseConnection", back_populates="project", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_projects_tenant", "tenant_id"),
    )


class ProjectMember(Base):
    """项目成员

    指定哪些用户可以访问哪些项目。
    """
    __tablename__ = "project_members"

    id = Column(String(36), primary_key=True)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    can_query = Column(Boolean, default=True)  # 是否有查询权限
    can_manage = Column(Boolean, default=False)  # 是否有管理权限
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    project = relationship("Project")
    user = relationship("User")

    __table_args__ = (
        UniqueConstraint("project_id", "user_id", name="uq_project_user"),
        Index("idx_project_members_project", "project_id"),
        Index("idx_project_members_user", "user_id"),
    )


# =============================================================================
# LLM 和数据库配置
# =============================================================================

class LLMConfig(Base):
    """LLM 配置"""
    __tablename__ = "llm_configs"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    name = Column(String(100), nullable=False)
    provider = Column(String(50), nullable=False)
    api_key_encrypted = Column(Text)  # 加密存储
    base_url = Column(String(500))
    model = Column(String(100), nullable=False)
    max_tokens = Column(Integer, default=2000)
    temperature = Column(String(10), default="0.7")
    timeout_seconds = Column(Integer, default=60)
    is_default = Column(Boolean, default=False)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="llm_configs")

    __table_args__ = (
        Index("idx_llm_tenant", "tenant_id"),
    )


class DatabaseConnection(Base):
    """数据库连接配置"""
    __tablename__ = "database_connections"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.id"), nullable=True)  # 所属项目
    name = Column(String(100), nullable=False)
    db_type = Column(String(50), nullable=False)
    host = Column(String(255))
    port = Column(Integer)
    database_name = Column(String(255), nullable=False)
    username = Column(String(100))
    password_encrypted = Column(Text)  # 加密存储
    charset = Column(String(20), default="utf8mb4")
    pool_size = Column(Integer, default=5)
    max_overflow = Column(Integer, default=10)
    is_default = Column(Boolean, default=False)
    is_readonly = Column(Boolean, default=True)  # 强制只读
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="database_connections")
    project = relationship("Project", back_populates="database_connections")
    schema_configs = relationship("SchemaConfig", back_populates="connection", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_db_tenant", "tenant_id"),
        Index("idx_db_project", "project_id"),
    )

    def get_connection_url(self) -> str:
        """生成连接 URL"""
        if self.db_type == DatabaseType.POSTGRESQL.value:
            return f"postgresql+asyncpg://{self.username}:{self.password_encrypted}@{self.host}:{self.port}/{self.database_name}"
        elif self.db_type == DatabaseType.MYSQL.value:
            return f"mysql+aiomysql://{self.username}:{self.password_encrypted}@{self.host}:{self.port}/{self.database_name}?charset={self.charset}"
        elif self.db_type == DatabaseType.SQLITE.value:
            return f"sqlite+aiosqlite:///{self.database_name}"
        elif self.db_type == DatabaseType.CLICKHOUSE.value:
            return f"clickhouse+asynch://{self.username}:{self.password_encrypted}@{self.host}:{self.port}/{self.database_name}"
        raise ValueError(f"Unsupported database type: {self.db_type}")


class SchemaConfig(Base):
    """Schema 配置"""
    __tablename__ = "schema_configs"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    connection_id = Column(String(36), ForeignKey("database_connections.id"), nullable=False)
    name = Column(String(100), nullable=False)
    description = Column(Text)
    yaml_content = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="schema_configs")
    connection = relationship("DatabaseConnection", back_populates="schema_configs")

    __table_args__ = (
        UniqueConstraint("tenant_id", "connection_id", name="uq_schema_connection"),
        Index("idx_schema_tenant", "tenant_id"),
        Index("idx_schema_connection", "connection_id"),
    )


# =============================================================================
# 查询历史和会话
# =============================================================================

class QueryHistory(Base):
    """查询历史"""
    __tablename__ = "query_history"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    session_id = Column(String(36))
    natural_query = Column(Text, nullable=False)
    generated_sql = Column(Text)
    tables_used = Column(JSON)  # PostgreSQL ARRAY as JSON
    row_count = Column(Integer)
    execution_time_ms = Column(Integer)
    llm_config_id = Column(String(36), ForeignKey("llm_configs.id"))
    connection_id = Column(String(36), ForeignKey("database_connections.id"))
    intent = Column(String(50))
    confidence = Column(String(10))
    status = Column(String(20), default=QueryStatus.SUCCESS.value)
    error_message = Column(Text)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    user = relationship("User", back_populates="query_history")

    __table_args__ = (
        Index("idx_history_user", "user_id"),
        Index("idx_history_tenant", "tenant_id"),
        Index("idx_history_session", "session_id"),
        Index("idx_history_created", "created_at"),
    )


class Session(Base):
    """会话"""
    __tablename__ = "sessions"

    id = Column(String(36), primary_key=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    title = Column(String(255))
    message_count = Column(Integer, default=0)
    last_message_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    expires_at = Column(DateTime)

    # 关系
    user = relationship("User", back_populates="sessions")

    __table_args__ = (
        Index("idx_sessions_user", "user_id"),
        Index("idx_sessions_tenant", "tenant_id"),
    )


# =============================================================================
# API Key 和审计
# =============================================================================

class APIKey(Base):
    """API Key"""
    __tablename__ = "api_keys"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"), nullable=False)
    user_id = Column(String(36), ForeignKey("users.id"))
    name = Column(String(100), nullable=False)
    key_hash = Column(String(64), nullable=False, unique=True)  # SHA-256
    key_prefix = Column(String(10), nullable=False)  # mgbi_sk_xxxx
    scope = Column(String(50), default="readonly")
    allowed_ips = Column(JSON)  # ["192.168.1.1"]
    expires_at = Column(DateTime)
    is_active = Column(Boolean, default=True)
    last_used_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.utcnow)

    # 关系
    tenant = relationship("Tenant", back_populates="api_keys")
    user = relationship("User", back_populates="api_keys")

    __table_args__ = (
        Index("idx_apikey_tenant", "tenant_id"),
        Index("idx_apikey_hash", "key_hash"),
    )


class AuditLog(Base):
    """审计日志"""
    __tablename__ = "audit_logs"

    id = Column(String(36), primary_key=True)
    tenant_id = Column(String(36), ForeignKey("tenants.id"))
    user_id = Column(String(36), ForeignKey("users.id"))
    ip_address = Column(String(45))
    user_agent = Column(Text)
    event_type = Column(String(100), nullable=False)
    resource = Column(String(100))
    action = Column(String(50))
    result = Column(String(20), default="success")
    error_code = Column(String(50))
    error_message = Column(Text)
    extra_data = Column(JSON)
    created_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        Index("idx_audit_tenant", "tenant_id"),
        Index("idx_audit_user", "user_id"),
        Index("idx_audit_event", "event_type"),
        Index("idx_audit_created", "created_at"),
    )


# =============================================================================
# 数据库初始化
# =============================================================================

def init_db(database_url: str, echo: bool = False):
    """
    初始化数据库

    Args:
        database_url: 数据库连接 URL
        echo: 是否打印 SQL
    """
    if database_url.startswith("sqlite"):
        # SQLite 不支持 AsyncAdaptedQueuePool
        engine = create_engine(database_url, echo=echo)
    else:
        engine = create_engine(database_url, echo=echo, pool_pre_ping=True)

    Base.metadata.create_all(engine)
    return engine


async def init_async_db(database_url: str, echo: bool = False):
    """
    异步初始化数据库

    Args:
        database_url: 数据库连接 URL (需加 aio 前缀)
        echo: 是否打印 SQL
    """
    if database_url.startswith("sqlite"):
        engine = create_async_engine(database_url, echo=echo, poolclass=NullPool)
    else:
        engine = create_async_engine(database_url, echo=echo, pool_pre_ping=True)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    return engine
