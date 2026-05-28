"""Micro-GenBI 数据库配置模块

基于 WrenAI 移植的 ProfileManager，实现 3 层回退配置机制。
支持单库和多库模式。
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Any
from functools import lru_cache

import yaml
from pydantic import BaseModel, Field, field_validator
from pydantic_settings import BaseSettings

from micro_genbi.models import DatabaseType


# =============================================================================
# 配置模型
# =============================================================================

class DatabaseProfile(BaseModel):
    """数据库连接配置"""
    name: str = Field(..., description="配置名称")
    type: DatabaseType = Field(..., description="数据库类型")
    host: str = Field("localhost", description="主机")
    port: int = Field(5432, description="端口")
    database: str = Field(..., description="数据库名")
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    schema: Optional[str] = Field(None, description="Schema（PostgreSQL 专用）")
    charset: str = Field("utf8mb4", description="字符集")

    # 连接池配置
    pool_size: int = Field(5, ge=1, le=100, description="连接池大小")
    max_overflow: int = Field(10, ge=0, le=50, description="最大溢出连接数")
    pool_timeout: int = Field(30, ge=1, description="连接超时（秒）")
    pool_recycle: int = Field(3600, description="连接回收时间（秒）")
    pool_pre_ping: bool = Field(True, description="连接前检测")

    # 读写分离（可选）
    read_replica: Optional[str] = Field(None, description="只读副本地址")

    @field_validator("port")
    @classmethod
    def validate_port(cls, v: int) -> int:
        if not (1 <= v <= 65535):
            raise ValueError(f"Port must be between 1 and 65535, got {v}")
        return v

    def get_url(self, readonly: bool = False) -> str:
        """生成数据库连接 URL"""
        if readonly and self.read_replica:
            host = self.read_replica
        else:
            host = self.host

        if self.type == DatabaseType.POSTGRESQL:
            return (
                f"postgresql+asyncpg://{self.username}:{self.password}"
                f"@{host}:{self.port}/{self.database}"
            )
        elif self.type == DatabaseType.MYSQL:
            return (
                f"mysql+aiomysql://{self.username}:{self.password}"
                f"@{host}:{self.port}/{self.database}?charset={self.charset}"
            )
        elif self.type == DatabaseType.SQLITE:
            return f"sqlite+aiosqlite:///{self.database}"
        elif self.type == DatabaseType.CLICKHOUSE:
            return (
                f"clickhouse+asynch://{self.username}:{self.password}"
                f"@{host}:{self.port}/{self.database}"
            )
        else:
            raise ValueError(f"Unsupported database type: {self.type}")

    def get_sync_url(self, readonly: bool = False) -> str:
        """生成同步数据库连接 URL"""
        if readonly and self.read_replica:
            host = self.read_replica
        else:
            host = self.host

        if self.type == DatabaseType.POSTGRESQL:
            return (
                f"postgresql://{self.username}:{self.password}"
                f"@{host}:{self.port}/{self.database}"
            )
        elif self.type == DatabaseType.MYSQL:
            return (
                f"mysql+pymysql://{self.username}:{self.password}"
                f"@{host}:{self.port}/{self.database}?charset={self.charset}"
            )
        elif self.type == DatabaseType.SQLITE:
            return f"sqlite:///{self.database}"
        else:
            raise ValueError(f"Unsupported database type: {self.type}")


class LLMProfile(BaseModel):
    """LLM 配置"""
    provider: str = Field("deepseek", description="提供商: deepseek|openai|ollama")
    api_key: Optional[str] = Field(None, description="API Key")
    base_url: Optional[str] = Field(None, description="API 基础 URL")
    model: str = Field("deepseek-chat", description="模型名称")
    max_tokens: int = Field(2000, ge=100, le=32000, description="最大 Token 数")
    temperature: float = Field(0.7, ge=0.0, le=2.0, description="温度参数")
    timeout: int = Field(60, ge=10, description="超时（秒）")


class SchemaProfile(BaseModel):
    """Schema 配置"""
    path: str = Field("./schema.yaml", description="Schema 文件路径")
    auto_refresh: bool = Field(False, description="是否自动刷新")
    refresh_interval: int = Field(3600, description="刷新间隔（秒）")


class SecurityProfile(BaseModel):
    """安全配置"""
    max_limit: int = Field(1000, ge=1, description="最大 LIMIT")
    max_join_count: int = Field(10, ge=1, description="最大 JOIN 数")
    allowed_tables: Optional[list[str]] = Field(None, description="允许的表（白名单）")
    blocked_keywords: list[str] = Field(
        default_factory=lambda: [
            "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
            "ALTER", "CREATE", "GRANT", "REVOKE", "EXEC", "EXECUTE",
        ],
        description="禁止的关键词"
    )


class GenBIConfig(BaseModel):
    """完整配置"""
    app_name: str = Field("Micro-GenBI", description="应用名称")
    environment: str = Field("development", description="环境")
    debug: bool = Field(False, description="调试模式")

    # 数据库配置（支持多库）
    database: Optional[DatabaseProfile] = Field(None, description="单库配置")
    databases: Optional[dict[str, DatabaseProfile]] = Field(None, description="多库配置")
    mode: str = Field("single", description="模式: single|aggregate|federated")

    # LLM 配置
    llm: LLMProfile = Field(default_factory=LLMProfile)

    # Schema 配置
    schema: SchemaProfile = Field(default_factory=SchemaProfile)

    # 安全配置
    security: SecurityProfile = Field(default_factory=SecurityProfile)


# =============================================================================
# 配置加载器
# =============================================================================

class ConfigLoader:
    """
    配置加载器

    实现 3 层回退机制：
    1. 显式传入的配置（最高优先级）
    2. 环境变量
    3. 配置文件（.yaml / .env）
    """

    _instance: Optional[GenBIConfig] = None

    @classmethod
    def load(
        cls,
        config_path: Optional[str] = None,
        env_prefix: str = "GENBI",
        **overrides,
    ) -> GenBIConfig:
        """
        加载配置

        Args:
            config_path: 配置文件路径
            env_prefix: 环境变量前缀
            **overrides: 显式配置覆盖
        """
        # 1. 从配置文件加载
        config_dict = {}
        if config_path and Path(config_path).exists():
            with open(config_path, "r", encoding="utf-8") as f:
                if config_path.endswith(".yaml") or config_path.endswith(".yml"):
                    config_dict = yaml.safe_load(f) or {}
                else:
                    raise ValueError(f"Unsupported config format: {config_path}")

        # 2. 从环境变量回退
        config_dict = cls._apply_env_overrides(config_dict, env_prefix)

        # 3. 应用显式覆盖
        config_dict.update(overrides)

        # 4. 解析配置
        config = GenBIConfig(**config_dict)

        # 5. 单库模式兼容
        if config.mode == "single" and config.database is None:
            # 从环境变量或配置创建单库配置
            config.database = cls._create_default_database()

        cls._instance = config
        return config

    @classmethod
    def _apply_env_overrides(
        cls,
        config_dict: dict,
        prefix: str,
    ) -> dict:
        """应用环境变量覆盖"""
        env_mappings = {
            f"{prefix}_DB_TYPE": ("database", "type"),
            f"{prefix}_DB_HOST": ("database", "host"),
            f"{prefix}_DB_PORT": ("database", "port"),
            f"{prefix}_DB_NAME": ("database", "database"),
            f"{prefix}_DB_USER": ("database", "username"),
            f"{prefix}_DB_PASSWORD": ("database", "password"),
            f"{prefix}_LLM_PROVIDER": ("llm", "provider"),
            f"{prefix}_LLM_API_KEY": ("llm", "api_key"),
            f"{prefix}_LLM_MODEL": ("llm", "model"),
            f"{prefix}_MAX_LIMIT": ("security", "max_limit"),
        }

        for env_key, (section, key) in env_mappings.items():
            value = os.environ.get(env_key)
            if value:
                if section not in config_dict:
                    config_dict[section] = {}
                if value.isdigit():
                    value = int(value)
                config_dict[section][key] = value

        return config_dict

    @classmethod
    def _create_default_database(cls) -> DatabaseProfile:
        """创建默认数据库配置（从环境变量）"""
        return DatabaseProfile(
            name="default",
            type=DatabaseType(os.environ.get("GENBI_DB_TYPE", "postgresql")),
            host=os.environ.get("GENBI_DB_HOST", "localhost"),
            port=int(os.environ.get("GENBI_DB_PORT", "5432")),
            database=os.environ.get("GENBI_DB_NAME", "test"),
            username=os.environ.get("GENBI_DB_USER", "readonly"),
            password=os.environ.get("GENBI_DB_PASSWORD", ""),
        )

    @classmethod
    def get_instance(cls) -> GenBIConfig:
        """获取已加载的配置实例"""
        if cls._instance is None:
            return cls.load()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置配置（用于测试）"""
        cls._instance = None


# =============================================================================
# 全局配置访问
# =============================================================================

@lru_cache()
def get_config() -> GenBIConfig:
    """获取全局配置（带缓存）"""
    return ConfigLoader.get_instance()


def get_database_config(name: Optional[str] = None) -> DatabaseProfile:
    """获取数据库配置"""
    config = get_config()

    if config.mode == "single":
        if config.database is None:
            raise ValueError("No database configured in single mode")
        return config.database

    if config.mode in ("aggregate", "federated"):
        if config.databases is None:
            raise ValueError("No databases configured in multi-database mode")
        if name is None:
            # 返回默认数据库
            return next(iter(config.databases.values()))
        if name not in config.databases:
            raise ValueError(f"Database not found: {name}")
        return config.databases[name]

    raise ValueError(f"Unknown mode: {config.mode}")
