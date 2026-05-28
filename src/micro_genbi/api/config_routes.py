"""配置管理 API 路由

提供租户、用户、LLM 配置、数据库连接、项目分组等管理接口。
"""

from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Query, BackgroundTasks
from pydantic import BaseModel, Field

from micro_genbi import get_logger
from micro_genbi.database import (
    TenantService, UserService, ProjectService,
    LLMConfigService, DatabaseConnectionService,
    APIKeyService, AuditService,
    CreateTenantInput, CreateUserInput, CreateProjectInput,
    CreateLLMConfigInput, CreateDatabaseConnectionInput,
)
from micro_genbi.database.models import init_async_db
from micro_genbi.api.dependencies import get_db_session, get_current_user

logger = get_logger(__name__)
router = APIRouter(prefix="/api/v1/admin", tags=["配置管理"])


# =============================================================================
# Pydantic 请求/响应模型
# =============================================================================

class TenantCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=255)
    description: Optional[str] = None


class TenantResponse(BaseModel):
    id: str
    name: str
    description: Optional[str]
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


# =============================================================================
# 项目相关模型
# =============================================================================

class ProjectCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    description: Optional[str] = None
    icon: str = "📁"
    color: str = "#4CAF50"


class ProjectResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    icon: str
    color: str
    is_active: bool
    created_at: str

    class Config:
        from_attributes = True


class ProjectWithConnections(BaseModel):
    id: str
    tenant_id: str
    name: str
    description: Optional[str]
    icon: str
    color: str
    is_active: bool
    connections: list["DatabaseConnectionResponse"]


class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=100)
    email: str
    password: str = Field(..., min_length=6)
    role: str = "user"


class UserResponse(BaseModel):
    id: str
    username: str
    email: str
    role: str
    is_active: bool
    last_login_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    provider: str = Field(..., pattern="^(deepseek|openai|ollama)$")
    api_key: str = Field(..., min_length=1)
    base_url: Optional[str] = None
    model: str = "deepseek-chat"
    max_tokens: int = Field(2000, ge=100, le=32000)
    temperature: float = Field(0.7, ge=0.0, le=2.0)
    is_default: bool = False


class LLMConfigResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    provider: str
    base_url: Optional[str]
    model: str
    max_tokens: int
    temperature: float
    is_default: bool
    is_active: bool
    created_at: str

    # 不返回加密的 api_key
    class Config:
        from_attributes = True
        exclude = {"api_key_encrypted"}


class DatabaseConnectionCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    project_id: Optional[str] = None  # 所属项目
    db_type: str = Field(..., pattern="^(postgresql|mysql|sqlite|clickhouse)$")
    host: Optional[str] = None
    port: Optional[int] = None
    database_name: str = Field(..., min_length=1)
    username: Optional[str] = None
    password: Optional[str] = None
    charset: str = "utf8mb4"
    is_default: bool = False


class DatabaseConnectionResponse(BaseModel):
    id: str
    tenant_id: str
    project_id: Optional[str]  # 所属项目
    name: str
    db_type: str
    host: Optional[str]
    port: Optional[int]
    database_name: str
    username: Optional[str]
    is_default: bool
    is_active: bool
    created_at: str

    # 不返回加密的 password
    class Config:
        from_attributes = True
        exclude = {"password_encrypted"}


class APIKeyCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    scope: str = "readonly"
    expires_in_days: Optional[int] = None


class APIKeyResponse(BaseModel):
    id: str
    tenant_id: str
    name: str
    key_prefix: str  # mgbi_sk_xxxx
    scope: str
    expires_at: Optional[str]
    is_active: bool
    last_used_at: Optional[str]
    created_at: str

    class Config:
        from_attributes = True


class ConnectionTestResult(BaseModel):
    success: bool
    latency_ms: Optional[int] = None
    error: Optional[str] = None
    tables_count: Optional[int] = None


# =============================================================================
# 租户管理
# =============================================================================

@router.post("/tenants", response_model=TenantResponse)
async def create_tenant(
    tenant: TenantCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建租户（系统管理员）"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    async for session in get_db_session():
        service = TenantService(session)
        result = await service.create(CreateTenantInput(
            name=tenant.name,
            description=tenant.description,
        ))
        return TenantResponse(
            id=result.id,
            name=result.name,
            description=result.description,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/tenants", response_model=list[TenantResponse])
async def list_tenants(
    current_user: dict = Depends(get_current_user),
):
    """列出所有租户"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")

    async for session in get_db_session():
        service = TenantService(session)
        tenants = await service.list_all()
        return [
            TenantResponse(
                id=t.id,
                name=t.name,
                description=t.description,
                is_active=t.is_active,
                created_at=t.created_at.isoformat() if t.created_at else "",
            )
            for t in tenants
        ]


# =============================================================================
# 项目管理
# =============================================================================

@router.post("/projects", response_model=ProjectResponse)
async def create_project(
    project: ProjectCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建项目"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = ProjectService(session)
        result = await service.create(
            input=CreateProjectInput(
                tenant_id=tenant_id,
                name=project.name,
                description=project.description,
                icon=project.icon,
                color=project.color,
            )
        )
        return ProjectResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            description=result.description,
            icon=result.icon,
            color=result.color,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    current_user: dict = Depends(get_current_user),
):
    """列出项目"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = ProjectService(session)
        projects = await service.get_by_tenant(tenant_id)
        return [
            ProjectResponse(
                id=p.id,
                tenant_id=p.tenant_id,
                name=p.name,
                description=p.description,
                icon=p.icon,
                color=p.color,
                is_active=p.is_active,
                created_at=p.created_at.isoformat() if p.created_at else "",
            )
            for p in projects
        ]


@router.get("/projects/with-connections")
async def list_projects_with_connections(
    current_user: dict = Depends(get_current_user),
):
    """列出项目及其数据源"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        project_service = ProjectService(session)
        db_service = DatabaseConnectionService(session)

        projects = await project_service.get_by_tenant(tenant_id)
        result = []

        for p in projects:
            connections = await db_service.get_by_project(p.id)
            conn_responses = [
                DatabaseConnectionResponse(
                    id=c.id,
                    tenant_id=c.tenant_id,
                    project_id=c.project_id,
                    name=c.name,
                    db_type=c.db_type,
                    host=c.host,
                    port=c.port,
                    database_name=c.database_name,
                    username=c.username,
                    is_default=c.is_default,
                    is_active=c.is_active,
                    created_at=c.created_at.isoformat() if c.created_at else "",
                )
                for c in connections
            ]
            result.append({
                "id": p.id,
                "tenant_id": p.tenant_id,
                "name": p.name,
                "description": p.description,
                "icon": p.icon,
                "color": p.color,
                "is_active": p.is_active,
                "connections": conn_responses,
            })

        return result


@router.delete("/projects/{project_id}")
async def delete_project(
    project_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除项目"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = ProjectService(session)
        project = await service.get_by_id(project_id)
        if not project or project.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="项目不存在")

        project.is_active = False
        await session.commit()
        return {"message": "项目已删除"}


# =============================================================================
# 用户管理
# =============================================================================

@router.post("/users", response_model=UserResponse)
async def create_user(
    user: UserCreate,
    tenant_id: str = Query(..., description="租户 ID"),
    current_user: dict = Depends(get_current_user),
):
    """创建用户"""
    # 检查权限：管理员或租户管理员
    if current_user.get("role") not in ["admin"] and current_user.get("tenant_id") != tenant_id:
        raise HTTPException(status_code=403, detail="权限不足")

    async for session in get_db_session():
        service = UserService(session)
        result = await service.create(
            input=CreateUserInput(
                username=user.username,
                email=user.email,
                password=user.password,
                role=user.role,
            ),
            tenant_id=tenant_id,
        )
        return UserResponse(
            id=result.id,
            username=result.username,
            email=result.email,
            role=result.role,
            is_active=result.is_active,
            last_login_at=result.last_login_at.isoformat() if result.last_login_at else None,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/users")
async def list_users(
    tenant_id: Optional[str] = Query(None),
    current_user: dict = Depends(get_current_user),
):
    """列出用户"""
    # TODO: 实现用户列表
    return {"users": [], "total": 0}


# =============================================================================
# LLM 配置管理
# =============================================================================

@router.post("/llm-configs", response_model=LLMConfigResponse)
async def create_llm_config(
    config: LLMConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建 LLM 配置"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = LLMConfigService(session)
        result = await service.create(CreateLLMConfigInput(
            tenant_id=tenant_id,
            name=config.name,
            provider=config.provider,
            api_key=config.api_key,
            base_url=config.base_url,
            model=config.model,
            max_tokens=config.max_tokens,
            temperature=config.temperature,
            is_default=config.is_default,
        ))
        return LLMConfigResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            provider=result.provider,
            base_url=result.base_url,
            model=result.model,
            max_tokens=result.max_tokens,
            temperature=float(result.temperature) if result.temperature else 0.7,
            is_default=result.is_default,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/llm-configs", response_model=list[LLMConfigResponse])
async def list_llm_configs(
    current_user: dict = Depends(get_current_user),
):
    """列出 LLM 配置"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = LLMConfigService(session)
        configs = await service.get_by_tenant(tenant_id)
        return [
            LLMConfigResponse(
                id=c.id,
                tenant_id=c.tenant_id,
                name=c.name,
                provider=c.provider,
                base_url=c.base_url,
                model=c.model,
                max_tokens=c.max_tokens,
                temperature=float(c.temperature) if c.temperature else 0.7,
                is_default=c.is_default,
                is_active=c.is_active,
                created_at=c.created_at.isoformat() if c.created_at else "",
            )
            for c in configs
        ]


@router.put("/llm-configs/{config_id}", response_model=LLMConfigResponse)
async def update_llm_config(
    config_id: str,
    config: LLMConfigCreate,
    current_user: dict = Depends(get_current_user),
):
    """更新 LLM 配置"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = LLMConfigService(session)

        # 验证所有权
        existing = await service.get_by_id(config_id)
        if not existing or existing.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="配置不存在")

        updates = config.model_dump(exclude_unset=True)
        if "api_key" in updates:
            updates["api_key_encrypted"] = updates.pop("api_key")

        result = await service.update(config_id, **updates)
        if not result:
            raise HTTPException(status_code=404, detail="配置不存在")

        return LLMConfigResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            provider=result.provider,
            base_url=result.base_url,
            model=result.model,
            max_tokens=result.max_tokens,
            temperature=float(result.temperature) if result.temperature else 0.7,
            is_default=result.is_default,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.delete("/llm-configs/{config_id}")
async def delete_llm_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除 LLM 配置"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = LLMConfigService(session)

        existing = await service.get_by_id(config_id)
        if not existing or existing.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="配置不存在")

        await service.update(config_id, is_active=False)
        return {"message": "配置已删除"}


@router.post("/llm-configs/{config_id}/test")
async def test_llm_config(
    config_id: str,
    current_user: dict = Depends(get_current_user),
):
    """测试 LLM 配置"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = LLMConfigService(session)

        config = await service.get_by_id(config_id)
        if not config or config.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="配置不存在")

        # TODO: 实际测试 LLM 连接
        return {
            "success": True,
            "latency_ms": 500,
            "model": config.model,
        }


# =============================================================================
# 数据库连接管理
# =============================================================================

@router.post("/connections", response_model=DatabaseConnectionResponse)
async def create_connection(
    connection: DatabaseConnectionCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建数据库连接"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = DatabaseConnectionService(session)
        result = await service.create(CreateDatabaseConnectionInput(
            tenant_id=tenant_id,
            project_id=connection.project_id,  # 所属项目
            name=connection.name,
            db_type=connection.db_type,
            host=connection.host,
            port=connection.port,
            database_name=connection.database_name,
            username=connection.username,
            password=connection.password,
            charset=connection.charset,
            is_default=connection.is_default,
        ))
        return DatabaseConnectionResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            project_id=result.project_id,
            name=result.name,
            db_type=result.db_type,
            host=result.host,
            port=result.port,
            database_name=result.database_name,
            username=result.username,
            is_default=result.is_default,
            is_active=result.is_active,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/connections", response_model=list[DatabaseConnectionResponse])
async def list_connections(
    current_user: dict = Depends(get_current_user),
):
    """列出数据库连接"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = DatabaseConnectionService(session)
        connections = await service.get_by_tenant(tenant_id)
        return [
            DatabaseConnectionResponse(
                id=c.id,
                tenant_id=c.tenant_id,
                name=c.name,
                db_type=c.db_type,
                host=c.host,
                port=c.port,
                database_name=c.database_name,
                username=c.username,
                is_default=c.is_default,
                is_active=c.is_active,
                created_at=c.created_at.isoformat() if c.created_at else "",
            )
            for c in connections
        ]


@router.post("/connections/{connection_id}/test")
async def test_connection(
    connection_id: str,
    current_user: dict = Depends(get_current_user),
) -> ConnectionTestResult:
    """测试数据库连接"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = DatabaseConnectionService(session)
        result = await service.test_connection(connection_id)
        return ConnectionTestResult(**result)


@router.delete("/connections/{connection_id}")
async def delete_connection(
    connection_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除数据库连接"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = DatabaseConnectionService(session)

        existing = await service.get_by_id(connection_id)
        if not existing or existing.tenant_id != tenant_id:
            raise HTTPException(status_code=404, detail="连接不存在")

        await service.update(connection_id, is_active=False)
        return {"message": "连接已删除"}


# =============================================================================
# API Key 管理
# =============================================================================

@router.post("/api-keys", response_model=APIKeyResponse)
async def create_api_key(
    api_key: APIKeyCreate,
    current_user: dict = Depends(get_current_user),
):
    """创建 API Key"""
    tenant_id = current_user.get("tenant_id")
    user_id = current_user.get("user_id")
    if not tenant_id or not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    async for session in get_db_session():
        service = APIKeyService(session)
        result, raw_key = await service.create(
            tenant_id=tenant_id,
            user_id=user_id,
            name=api_key.name,
            scope=api_key.scope,
            expires_in_days=api_key.expires_in_days,
        )
        return APIKeyResponse(
            id=result.id,
            tenant_id=result.tenant_id,
            name=result.name,
            key_prefix=result.key_prefix,
            scope=result.scope,
            expires_at=result.expires_at.isoformat() if result.expires_at else None,
            is_active=result.is_active,
            last_used_at=result.last_used_at.isoformat() if result.last_used_at else None,
            created_at=result.created_at.isoformat() if result.created_at else "",
        )


@router.get("/api-keys", response_model=list[APIKeyResponse])
async def list_api_keys(
    current_user: dict = Depends(get_current_user),
):
    """列出 API Key"""
    tenant_id = current_user.get("tenant_id")
    if not tenant_id:
        raise HTTPException(status_code=401, detail="未登录")

    # TODO: 实现 API Key 列表
    return []


@router.delete("/api-keys/{api_key_id}")
async def revoke_api_key(
    api_key_id: str,
    current_user: dict = Depends(get_current_user),
):
    """撤销 API Key"""
    tenant_id = current_user.get("tenant_id")

    async for session in get_db_session():
        service = APIKeyService(session)
        success = await service.revoke(api_key_id)
        if not success:
            raise HTTPException(status_code=404, detail="API Key 不存在")
        return {"message": "API Key 已撤销"}
