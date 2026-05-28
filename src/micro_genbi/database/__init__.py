"""系统数据库模块

包含系统数据库的 ORM 模型和服务。
"""

from micro_genbi.database.models import (
    Base,
    Tenant, User, TenantMember,
    Project, ProjectMember,
    LLMConfig, DatabaseConnection, SchemaConfig,
    QueryHistory, Session as SessionModel, APIKey, AuditLog,
    UserRole, LLMProvider, DatabaseType, QueryStatus,
    init_db, init_async_db,
)

from micro_genbi.database.services import (
    SecretManager,
    TenantService,
    UserService,
    ProjectService,
    LLMConfigService,
    DatabaseConnectionService,
    APIKeyService,
    AuditService,
    QueryHistoryService,
    CreateTenantInput,
    CreateUserInput,
    CreateLLMConfigInput,
    CreateDatabaseConnectionInput,
    CreateProjectInput,
)
from micro_genbi.database.cross_db_models import (
    CrossDBRelation,
    ConnectionGroup,
    ConnectionGroupMember,
    RelationCardinality,
    RelationStatus,
    DatabaseMode,
)
from micro_genbi.database.cross_db_services import (
    CrossDBRelationService,
    ConnectionGroupService,
    CreateRelationInput,
    CreateGroupInput,
    AddGroupMemberInput,
)

# Lazy import to avoid circular dependency
_db_session_factory = None

def set_db_session_factory(factory):
    """设置数据库会话工厂（由 main.py 在启动时调用）"""
    global _db_session_factory
    _db_session_factory = factory

async def get_db_session():
    """获取数据库会话（生成器）"""
    if _db_session_factory is None:
        raise RuntimeError("Database session factory not initialized. Call set_db_session_factory() first.")
    async with _db_session_factory() as session:
        yield session

__all__ = [
    # 模型
    "Base",
    "Tenant", "User", "TenantMember",
    "LLMConfig", "DatabaseConnection", "SchemaConfig",
    "QueryHistory", "SessionModel", "APIKey", "AuditLog",
    "UserRole", "LLMProvider", "DatabaseType", "QueryStatus",
    "init_db", "init_async_db",
    # 服务
    "SecretManager",
    "TenantService",
    "UserService",
    "LLMConfigService",
    "DatabaseConnectionService",
    "APIKeyService",
    "AuditService",
    "QueryHistoryService",
    # 数据类
    "CreateTenantInput",
    "CreateUserInput",
    "CreateLLMConfigInput",
    "CreateDatabaseConnectionInput",
    "CreateProjectInput",
    # 跨库关联
    "CrossDBRelation",
    "ConnectionGroup",
    "ConnectionGroupMember",
    "RelationCardinality",
    "RelationStatus",
    "DatabaseMode",
    "CrossDBRelationService",
    "ConnectionGroupService",
    "CreateRelationInput",
    "CreateGroupInput",
    "AddGroupMemberInput",
    # 会话管理
    "set_db_session_factory",
    "get_db_session",
]
