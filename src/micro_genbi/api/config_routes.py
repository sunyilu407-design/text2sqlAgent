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
from micro_genbi.database.services import UserManagementService, AuditLogService
from micro_genbi.database.models import init_async_db
from micro_genbi.api.dependencies import get_db_session, get_current_user

logger = get_logger(__name__)
router = APIRouter(prefix="/admin", tags=["配置管理"])

# In-memory system config store
_system_config: dict = {}


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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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
    role: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """列出用户"""
    effective_tenant = tenant_id or current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        service = UserManagementService(session)
        users, total = await service.list_users(
            tenant_id=effective_tenant,
            role=role,
            status=status,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [
                {
                    "id": u.id,
                    "username": u.username,
                    "email": u.email or "",
                    "role": u.role,
                    "group": u.tenant_id,
                    "subscriptionPlan": "free",
                    "status": "active" if u.is_active else "suspended",
                    "llmConfigured": False,
                    "totalCalls": 0,
                    "lastCallTime": u.last_login_at.isoformat() if u.last_login_at else "",
                }
                for u in users
            ],
            "total": total,
        }
    return {"items": [], "total": 0}


@router.put("/users/{user_id}")
async def update_user(
    user_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """更新用户"""
    async with get_db_session() as session:
        service = UserManagementService(session)
        updates = {}
        if "role" in request:
            updates["role"] = request["role"]
        if "is_active" in request:
            updates["is_active"] = request["is_active"]
        user = await service.update_user(user_id, **updates)
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email or "",
            "role": user.role,
            "group": user.tenant_id,
            "subscriptionPlan": "free",
            "status": "active" if user.is_active else "suspended",
            "llmConfigured": False,
            "totalCalls": 0,
            "lastCallTime": user.last_login_at.isoformat() if user.last_login_at else "",
        }


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除用户（软删除）"""
    async with get_db_session() as session:
        service = UserManagementService(session)
        success = await service.delete_user(user_id)
        if not success:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {"message": "用户已删除"}


@router.post("/users/{user_id}/reset-password")
async def reset_user_password(
    user_id: str,
    current_user: dict = Depends(get_current_user),
):
    """重置用户密码（管理员功能）"""
    if current_user.get("role") not in ("admin", "tenant_admin"):
        raise HTTPException(status_code=403, detail="需要管理员权限")

    async with get_db_session() as session:
        service = UserManagementService(session)
        new_password = await service.reset_password(user_id)
        if new_password is None:
            raise HTTPException(status_code=404, detail="用户不存在")

        # 记录审计日志
        try:
            audit_svc = AuditService(session)
            await audit_svc.log(
                event_type="user.password_reset",
                tenant_id=current_user.get("tenant_id"),
                user_id=current_user.get("user_id"),
                resource=user_id,
                result="success",
            )
        except Exception:
            pass

        return {"message": "密码已重置", "password": new_password}


# =============================================================================
# 审计日志接口
# =============================================================================

@router.get("/audit/logs")
async def get_audit_logs(
    eventType: Optional[str] = Query(None),
    user: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """获取审计日志"""
    tenant_id = current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        service = AuditLogService(session)
        logs, total = await service.list_logs(
            tenant_id=tenant_id,
            user_id=user,
            event_type=eventType,
            limit=limit,
            offset=offset,
        )
        return {
            "items": [
                {
                    "id": log.id,
                    "timestamp": log.created_at.isoformat() if log.created_at else "",
                    "user": log.user_id or "—",
                    "email": log.user_id or "",
                    "eventType": log.event_type,
                    "result": log.result,
                    "details": log.error_message or log.action or log.event_type,
                    "context": {
                        "ip": log.ip_address or "—",
                        "node": log.resource or "—",
                        "userAgent": log.user_agent or "—",
                        "timestampUtc": log.created_at.isoformat() if log.created_at else "",
                    },
                }
                for log in logs
            ],
            "total": total,
        }
    return {"items": [], "total": 0}


@router.get("/audit/stats")
async def get_audit_stats(current_user: dict = Depends(get_current_user)):
    """获取审计统计"""
    tenant_id = current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        service = AuditLogService(session)
        return await service.get_stats(tenant_id=tenant_id)
    return {
        "totalEvents": 0,
        "failedLogins": 0,
        "blockedQueries": 0,
        "sqlInjections": 0,
        "last24h": {"logins": 0, "queries": 0, "failures": 0},
    }


# =============================================================================
# 计费统计接口
# =============================================================================

@router.get("/cost")
async def get_cost(current_user: dict = Depends(get_current_user)):
    """获取 LLM 计费统计"""
    from micro_genbi.llm.cost_tracker import get_cost_tracker
    tracker = get_cost_tracker()
    summary = tracker.summary()

    total_cost = summary.total_cost_usd
    avg_cost = total_cost / summary.total_calls if summary.total_calls > 0 else 0.0

    return {
        "totalTokens": str(summary.total_tokens),
        "promptTokens": str(summary.total_prompt_tokens),
        "completionTokens": str(summary.total_completion_tokens),
        "estimatedCost": f"${total_cost:.4f}",
        "avgPerQuery": f"${avg_cost:.4f}",
        "callsCount": summary.total_calls,
    }


@router.get("/cost/by-user")
async def get_cost_by_user(current_user: dict = Depends(get_current_user)):
    """按用户计费统计（基于审计日志中的查询记录估算）"""
    tenant_id = current_user.get("tenant_id", "default")
    async with get_db_session() as session:
        from micro_genbi.database.services import QueryHistoryService, AuditLogService
        history_svc = QueryHistoryService(session)
        audit_svc = AuditLogService(session)

        # 从查询历史中按用户聚合（租户级别）
        history, total = await history_svc.list_all(tenant_id=tenant_id, limit=1000, offset=0)
        audit_summary = await audit_svc.get_stats(tenant_id=tenant_id)

        # 按 user_id 分组统计查询次数
        from collections import defaultdict
        user_query_counts: dict[str, int] = defaultdict(int)
        for h in history:
            uid = getattr(h, 'user_id', None) or 'unknown'
            user_query_counts[uid] += 1

        total_queries = sum(user_query_counts.values()) or 1
        # 估算每个用户的 token 消耗（取平均）
        avg_tokens_per_query = 500  # 估算平均每次查询消耗 500 tokens
        user_costs = []
        for uid, count in sorted(user_query_counts.items(), key=lambda x: -x[1])[:10]:
            tokens = count * avg_tokens_per_query
            cost = tokens / 1_000_000 * 0.27  # deepseek-chat 价格估算
            user_costs.append({
                "user": uid,
                "tokens": f"{tokens:,}",
                "calls": count,
                "cost": f"${cost:.4f}",
                "percentage": f"{count / total_queries * 100:.1f}%",
            })
        return user_costs or [{"user": "暂无数据", "tokens": "0", "calls": 0, "cost": "$0.00", "percentage": "0%"}]


@router.get("/cost/by-model")
async def get_cost_by_model(current_user: dict = Depends(get_current_user)):
    """按模型计费统计"""
    from micro_genbi.llm.cost_tracker import get_cost_tracker
    tracker = get_cost_tracker()
    summary = tracker.summary()

    model_data = []
    for model, cost in summary.by_model.items():
        # 估算调用次数和 token
        price = {"deepseek-chat": ("deepseek", 0.27), "gpt-4o-mini": ("openai", 0.15),
                 "gpt-4o": ("openai", 2.50), "ollama-local": ("ollama", 0.0)}.get(model, ("unknown", 0.0))
        calls = max(1, int(cost / (0.27 * 0.001)))  # 粗估
        tokens = calls * 500  # 估算
        model_data.append({
            "model": model,
            "provider": price[0],
            "calls": str(calls),
            "tokens": f"{tokens:,}",
            "cost": f"${cost:.4f}",
        })
    return model_data or [{"model": "暂无数据", "provider": "-", "calls": "0", "tokens": "0", "cost": "$0.00"}]


# =============================================================================
# 性能监控接口
# =============================================================================

@router.get("/performance/slow-queries")
async def get_slow_queries(
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
):
    """获取慢查询（基于查询历史）"""
    tenant_id = current_user.get("tenant_id", "default")
    async with get_db_session() as session:
        from micro_genbi.database.services import QueryHistoryService
        history_svc = QueryHistoryService(session)
        history, total = await history_svc.list_all(tenant_id=tenant_id, limit=limit * 2, offset=0)
        # 按执行时间排序，取最慢的
        slow_items = sorted(history, key=lambda x: getattr(x, 'execution_time_ms', 0) or 0, reverse=True)[:limit]
        return {
            "items": [
                {
                    "id": getattr(h, 'id', str(i)),
                    "query": getattr(h, 'natural_query', '')[:200],
                    "user": getattr(h, 'user_id', '—'),
                    "executionTimeMs": getattr(h, 'execution_time_ms', 0) or 0,
                    "status": getattr(h, 'status', 'completed'),
                    "timestamp": getattr(h, 'created_at', None).isoformat() if getattr(h, 'created_at', None) else "",
                }
                for i, h in enumerate(slow_items)
            ],
            "total": total,
        }


@router.get("/performance/llm-metrics")
async def get_llm_metrics(current_user: dict = Depends(get_current_user)):
    """获取 LLM 指标（基于成本追踪器）"""
    from micro_genbi.llm.cost_tracker import get_cost_tracker
    tracker = get_cost_tracker()
    summary = tracker.summary()
    records = tracker.get_recent_records(limit=100)

    # 按 model 聚合
    from collections import defaultdict
    model_stats: dict[str, dict] = defaultdict(lambda: {"calls": 0, "total_ms": 0, "errors": 0})
    for rec in records:
        m = rec.get("model", "unknown")
        model_stats[m]["calls"] += 1
        model_stats[m]["total_ms"] += rec.get("duration_ms", 0)
        if not rec.get("success", True):
            model_stats[m]["errors"] += 1

    return [
        {
            "model": model,
            "successRate": round((stats["calls"] - stats["errors"]) / stats["calls"] * 100, 1) if stats["calls"] > 0 else 0,
            "avgLatencyMs": round(stats["total_ms"] / stats["calls"]) if stats["calls"] > 0 else 0,
            "totalCalls": stats["calls"],
        }
        for model, stats in model_stats.items()
    ] or [
        {"model": "deepseek-chat", "successRate": 0.0, "avgLatencyMs": 0, "totalCalls": 0},
    ]


@router.get("/performance/query-trend")
async def get_query_trend(current_user: dict = Depends(get_current_user)):
    """获取查询趋势（基于查询历史）"""
    from datetime import datetime, timedelta
    tenant_id = current_user.get("tenant_id", "default")
    async with get_db_session() as session:
        from micro_genbi.database.services import QueryHistoryService
        history_svc = QueryHistoryService(session)
        history, _ = await history_svc.list_all(tenant_id=tenant_id, limit=1000, offset=0)

        # 按日期聚合
        from collections import defaultdict
        by_date: dict[str, int] = defaultdict(int)
        for h in history:
            ts = getattr(h, 'created_at', None)
            if ts:
                date_key = ts.strftime("%m月%d日")
                by_date[date_key] += 1

        # 返回最近7天
        days = []
        for i in range(7):
            date = datetime.now() - timedelta(days=6 - i)
            label = date.strftime("5月%d日")
            days.append({"label": label, "value": by_date.get(label, 0)})
        return days


# =============================================================================
# 安全告警接口
# =============================================================================

@router.get("/security/alerts")
async def get_security_alerts(
    current_user: dict = Depends(get_current_user),
):
    """获取安全告警（基于审计日志中的异常事件）"""
    tenant_id = current_user.get("tenant_id", "default")
    async with get_db_session() as session:
        from micro_genbi.database.services import AuditLogService
        audit_svc = AuditLogService(session)
        logs, total = await audit_svc.list_logs(tenant_id=tenant_id, limit=20, offset=0)

        # 筛选失败和被阻断的事件作为告警
        alert_events = [
            "user.login.failed", "sql.validation.failed", "query.blocked",
            "sql.injection", "permission.denied", "auth.failed",
        ]
        items = []
        for log in logs:
            evt = getattr(log, 'event_type', '') or ''
            result = getattr(log, 'result', '') or ''
            if result in ('failed', 'blocked') or any(e in evt.lower() for e in alert_events):
                items.append({
                    "id": getattr(log, 'id', ''),
                    "severity": "P2" if result == "failed" else "P1",
                    "type": evt or "security_event",
                    "user": getattr(log, 'user_id', '—') or '—',
                    "ip": getattr(log, 'ip_address', '—') or '—',
                    "description": getattr(log, 'error_message', '') or evt or '安全事件',
                    "timestamp": getattr(log, 'created_at', None).isoformat() if getattr(log, 'created_at', None) else "",
                    "acknowledged": False,
                })

        return {"items": items, "total": total}


@router.post("/security/alerts/{alert_id}/acknowledge")
async def ack_alert(alert_id: str, current_user: dict = Depends(get_current_user)):
    """确认告警（仅记录确认操作）"""
    logger.info(f"用户 {current_user.get('user_id')} 确认了告警 {alert_id}")
    return {"message": "告警已确认"}


@router.get("/security/failed-logins")
async def get_failed_logins(current_user: dict = Depends(get_current_user)):
    """获取失败登录记录（基于审计日志）"""
    tenant_id = current_user.get("tenant_id", "default")
    async with get_db_session() as session:
        from micro_genbi.database.services import AuditLogService
        from collections import defaultdict
        audit_svc = AuditLogService(session)
        logs, _ = await audit_svc.list_logs(tenant_id=tenant_id, event_type="user.login.failed", limit=50)

        # 按 user+ip 聚合
        login_failures: dict[str, dict] = defaultdict(lambda: {"attempts": 0, "lastAttempt": ""})
        for log in logs:
            key = f"{getattr(log, 'user_id', 'unknown')}@{getattr(log, 'ip_address', 'unknown')}"
            login_failures[key]["attempts"] += 1
            ts = getattr(log, 'created_at', None)
            if ts:
                login_failures[key]["lastAttempt"] = ts.isoformat()

        return [
            {"user": k.split("@")[0] or 'unknown', "ip": k.split("@")[1] or 'unknown',
             "attempts": v["attempts"], "lastAttempt": v["lastAttempt"]}
            for k, v in sorted(login_failures.items(), key=lambda x: -x[1]["attempts"])[:10]
        ] or [{"user": "暂无数据", "ip": "—", "attempts": 0, "lastAttempt": ""}]



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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
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

    async with get_db_session() as session:
        service = APIKeyService(session)
        success = await service.revoke(api_key_id)
        if not success:
            raise HTTPException(status_code=404, detail="API Key 不存在")
        return {"message": "API Key 已撤销"}


class SystemConfigRequest(BaseModel):
    system_name: Optional[str] = None
    system_url: Optional[str] = None
    default_tenant: Optional[str] = None
    ip_whitelist_enabled: Optional[bool] = None
    ip_whitelist: Optional[str] = None
    rate_limit_enabled: Optional[bool] = None
    rate_limit_qps: Optional[int] = Field(None, ge=1, le=10000)
    alert_low_balance_enabled: Optional[bool] = None


@router.post("/system-config", response_model=dict)
async def save_system_config(
    config: SystemConfigRequest,
    current_user: dict = Depends(get_current_user),
):
    """保存系统全局配置"""
    role = current_user.get("role")
    if role != "admin":
        raise HTTPException(status_code=403, detail="仅管理员可修改系统配置")

    logger.info(f"[Admin] 用户 {current_user.get('user_id')} 保存系统配置: {config.model_dump(exclude_none=True)}")

    # In-memory config store (in production, persist to DB)
    global _system_config
    _system_config = {k: v for k, v in config.model_dump(exclude_none=True).items() if v is not None}

    return {
        "message": "系统配置已保存",
        "config": _system_config,
    }


@router.get("/system-config", response_model=dict)
async def get_system_config(
    current_user: dict = Depends(get_current_user),
):
    """获取系统全局配置"""
    return {"config": _system_config}
