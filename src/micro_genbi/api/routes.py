"""API 路由定义"""

from __future__ import annotations

import os
import asyncio
import json
import uuid
import csv
import io
from typing import Optional, Any
from functools import lru_cache

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse, JSONResponse

from micro_genbi.models import (
    QueryRequest,
    QueryResponse,
    TaskInfo,
    TaskResult,
    TaskProgressEvent,
    SchemaResponse,
    ChartType,
    ExportRequest,
    ExportResponse,
)
from pydantic import BaseModel, Field
from micro_genbi.errors import SQLValidationError, GenBIError
from micro_genbi import get_logger
from micro_genbi.api.dependencies import (
    get_current_user,
    get_db_session,
    get_tenant_context,
    TenantContext,
)
from micro_genbi.service.ask_service import AskService
from micro_genbi.service.multi_ask_service import MultiDBAskService
from micro_genbi.service.subscription import SubscriptionService
from micro_genbi.service.sql_versioning import SQLVersioningService
from micro_genbi.service.operation_trace import OperationTraceService
from micro_genbi.semantic.schema_registry import SchemaRegistry
from micro_genbi.chart import ChartEngine
from micro_genbi.chart.smart_recommender import ChartRecommender
from micro_genbi.intent.query_suggester import QuerySuggester
from micro_genbi.database.services import QueryHistoryService, AuditLogService, AuditService, UserManagementService, UserService, TenantService
from micro_genbi.database import CreateUserInput, CreateTenantInput
from micro_genbi.db.connection_factory import get_multi_db_factory

logger = get_logger(__name__)
router = APIRouter()

# 模拟任务存储（生产环境应使用 Redis）
_tasks: dict[str, dict] = {}

# 导出任务存储
_export_tasks: dict[str, dict] = {}

# 全局服务实例
_sql_versioning_service: SQLVersioningService | None = None
_operation_trace_service: OperationTraceService | None = None
_query_suggester: QuerySuggester | None = None


def _get_sql_versioning() -> SQLVersioningService:
    global _sql_versioning_service
    if _sql_versioning_service is None:
        _sql_versioning_service = SQLVersioningService()
    return _sql_versioning_service


def _get_operation_trace() -> OperationTraceService:
    global _operation_trace_service
    if _operation_trace_service is None:
        _operation_trace_service = OperationTraceService()
    return _operation_trace_service


def _get_query_suggester() -> QuerySuggester:
    global _query_suggester
    if _query_suggester is None:
        _query_suggester = QuerySuggester()
    return _query_suggester


@lru_cache()
def _get_schema_registry() -> SchemaRegistry:
    """获取缓存的 SchemaRegistry"""
    schema_path = os.getenv("SCHEMA_PATH", "schema.yaml")
    registry = SchemaRegistry(schema_path=schema_path)
    registry.load()
    return registry


@lru_cache()
def _get_ask_service() -> AskService:
    """获取缓存的 AskService"""
    schema_registry = _get_schema_registry()
    return AskService(schema_registry=schema_registry)


@lru_cache()
def _get_chart_engine() -> ChartEngine:
    """获取缓存的 ChartEngine"""
    return ChartEngine()


# =============================================================================
# 查询接口
# =============================================================================

@router.post("/query", response_model=QueryResponse, tags=["查询"])
async def query(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
) -> QueryResponse:
    """
    同步执行自然语言查询

    输入自然语言问题，返回 SQL 查询结果。
    """
    try:
        logger.info(f"处理查询: {request.query[:50]}...")

        user_id = request.user_id or current_user.get("user_id")
        tenant_id = current_user.get("tenant_id", "default")
        role = request.role or current_user.get("role", "user")

        # 获取 AskService
        service = _get_ask_service()

        # 执行查询
        result = await service.ask(
            query=request.query,
            user_id=user_id,
            role=role,
            session_id=request.session_id,
        )

        # 生成图表
        if request.generate_chart and result.data:
            chart_engine = _get_chart_engine()
            intent_str = result.summary or ""
            chart = chart_engine.generate(
                data=result.data,
                intent=intent_str,
                forced_type=request.chart_type,
            )
            if chart:
                result.chart = chart

        # 保存查询历史
        if user_id and tenant_id:
            try:
                async with get_db_session() as session:
                    history_service = QueryHistoryService(session)
                    await history_service.create(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        natural_query=request.query,
                        generated_sql=result.sql,
                        row_count=result.row_count,
                        execution_time_ms=result.execution_time_ms,
                        status="success",
                        session_id=request.session_id,
                    )
            except Exception as hist_err:
                logger.warning(f"保存查询历史失败: {hist_err}")

        return result

    except SQLValidationError as e:
        logger.error(f"SQL 验证失败: {e}")
        raise HTTPException(status_code=422, detail=e.to_dict())
    except GenBIError as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/multi", response_model=QueryResponse, tags=["查询"])
async def query_multi(
    request: QueryRequest,
    current_user: dict = Depends(get_current_user),
) -> QueryResponse:
    """
    多数据库感知查询接口。

    自动检测查询模式（SINGLE / AGGREGATE / FEDERATED），
    支持跨库查询（需要预先配置跨库关联）。

    请求体与 /query 相同，响应增加了以下字段：
    - query_mode: single | aggregate | federated
    - query_mode_label: 显示用的模式名称
    - query_mode_emoji: 模式图标
    - is_multi_db: 是否为多库查询
    - sub_results: 各子查询的执行结果
    - rejected_reason: 当查询被拒绝时的原因
    """
    try:
        logger.info(f"[MultiDB] 处理查询: {request.query[:50]}...")

        user_id = request.user_id or current_user.get("user_id")
        tenant_id = current_user.get("tenant_id", "default")
        role = request.role or current_user.get("role", "user")

        # 获取 DB session 并创建 MultiDBAskService
        async with get_db_session() as session:
            service = MultiDBAskService(
                session=session,
                schema_registry=_get_schema_registry(),
                default_connection_id=request.connection_id,
            )

            result = await service.ask(
                query=request.query,
                user_id=user_id,
                role=role,
                session_id=request.session_id,
                connection_id=request.connection_id,
                tenant_id=tenant_id,
            )

            # 生成图表
            if request.generate_chart and result.data and not result.rejected_reason:
                chart_engine = _get_chart_engine()
                intent_str = result.summary or ""
                chart = chart_engine.generate(
                    data=result.data,
                    intent=intent_str,
                    forced_type=request.chart_type,
                )
                if chart:
                    result.chart = chart

            # 保存查询历史
            if user_id and tenant_id:
                try:
                    history_service = QueryHistoryService(session)
                    await history_service.create(
                        user_id=user_id,
                        tenant_id=tenant_id,
                        natural_query=request.query,
                        generated_sql=result.sql,
                        row_count=result.row_count,
                        execution_time_ms=result.execution_time_ms,
                        status="success" if not result.rejected_reason else "rejected",
                        session_id=request.session_id,
                    )
                except Exception as hist_err:
                    logger.warning(f"保存查询历史失败: {hist_err}")

            return result

    except SQLValidationError as e:
        logger.error(f"SQL 验证失败: {e}")
        raise HTTPException(status_code=422, detail=e.to_dict())
    except GenBIError as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"查询失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


class SQLPreviewRequest(BaseModel):
    query: str = Field(..., description="自然语言查询")
    connection_id: Optional[str] = Field(None, description="数据库连接 ID")


class SQLPreviewResponse(BaseModel):
    sql: str = Field(..., description="生成的 SQL")


@router.post("/query/preview-sql", response_model=SQLPreviewResponse, tags=["查询"])
async def preview_sql(
    request: SQLPreviewRequest,
    current_user: dict = Depends(get_current_user),
):
    """
    仅生成 SQL（不执行），用于 workbench 实时预览。
    """
    try:
        from micro_genbi.service.ask_service import AskService
        from micro_genbi.llm.factory import create_llm_client
        from micro_genbi.semantic.schema_registry import SchemaRegistry

        llm_client = create_llm_client()
        schema_registry = SchemaRegistry()
        schema_registry.load()

        service = AskService(llm_client, schema_registry)
        try:
            result = await service.ask(
                query=request.query,
                user_id=current_user.get("user_id"),
                role=current_user.get("role", "user"),
                session_id=None,
                skip_execution=True,
            )
            return SQLPreviewResponse(sql=result.sql)
        finally:
            await service.close()

    except SQLValidationError as e:
        raise HTTPException(status_code=422, detail=e.to_dict())
    except GenBIError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"SQL 预览失败: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/query/async", response_model=TaskInfo, tags=["查询"])
async def query_async(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    异步执行查询

    返回任务 ID，客户端通过 GET /api/v1/query/async/{task_id} 轮询状态。
    """
    task_id = f"task_{uuid.uuid4().hex[:12]}"

    user_id = request.user_id or current_user.get("user_id", "anonymous")
    tenant_id = current_user.get("tenant_id", "default")
    role = request.role or current_user.get("role", "user")

    _tasks[task_id] = {
        "id": task_id,
        "status": "pending",
        "request": request.model_dump(),
        "user_id": user_id,
        "tenant_id": tenant_id,
        "role": role,
        "progress": 0,
        "current_step": None,
        "result": None,
        "error": None,
    }

    background_tasks.add_task(_execute_query_task, task_id)

    return TaskInfo(
        task_id=task_id,
        status="pending",
    )


@router.get("/query/async/{task_id}", response_model=TaskResult, tags=["查询"])
async def get_task_status(task_id: str):
    """获取异步任务状态"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = _tasks[task_id]

    return TaskResult(
        task_id=task_id,
        status=task["status"],
        progress=task.get("progress", 0),
        current_step=task.get("current_step"),
        result=task.get("result"),
        error=task.get("error"),
    )


@router.get("/query/async/{task_id}/stream", tags=["查询"])
async def stream_task_progress(task_id: str):
    """SSE 流式获取任务进度"""

    async def event_generator():
        if task_id not in _tasks:
            yield f"event: error\ndata: {json.dumps({'error': '任务不存在'})}\n\n"
            return

        task = _tasks[task_id]

        # 发送初始状态
        yield f"event: start\ndata: {json.dumps({'task_id': task_id})}\n\n"

        # 实时轮询任务状态
        prev_progress = 0
        while True:
            task = _tasks.get(task_id)
            if not task:
                yield f"event: error\ndata: {json.dumps({'error': '任务不存在'})}\n\n"
                return

            status = task.get("status", "pending")
            progress = task.get("progress", 0)
            current_step = task.get("current_step")

            # 只在进度变化时发送
            if progress != prev_progress or status in ("success", "failed", "cancelled"):
                message = f"步骤: {current_step}" if current_step else ""
                yield f"event: progress\ndata: {json.dumps({'progress': progress, 'message': message})}\n\n"
                prev_progress = progress

            if status in ("success", "failed", "cancelled"):
                result = task.get("result")
                error = task.get("error")
                yield f"event: complete\ndata: {json.dumps({'task_id': task_id, 'status': status, 'result': result, 'error': error})}\n\n"
                return

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.delete("/query/async/{task_id}", tags=["查询"])
async def cancel_task(task_id: str):
    """取消正在执行的任务"""
    if task_id not in _tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    _tasks[task_id]["status"] = "cancelled"
    return {"message": "任务已取消"}


# =============================================================================
# Schema 接口
# =============================================================================

@router.get("/schema", response_model=SchemaResponse, tags=["Schema"])
async def get_schema(
    include_relationships: bool = Query(False, description="是否包含关系"),
    include_columns: bool = Query(True, description="是否包含列信息"),
):
    """
    获取数据库 Schema 信息

    返回所有表及其列的详细信息。
    """
    registry = _get_schema_registry()

    databases = []
    for db in registry.get_all_databases():
        tables = []
        for table in db.tables:
            tables.append({
                "name": table.name,
                "display_name": getattr(table, "logical_name", table.name),
                "description": getattr(table, "description", ""),
                "columns": [
                    {
                        "name": col.name,
                        "display_name": getattr(col, "logical_name", col.name),
                        "data_type": col.col_type,
                        "description": getattr(col, "description", ""),
                        "nullable": col.is_nullable,
                        "primary_key": col.is_primary_key,
                    }
                    for col in table.columns
                ] if include_columns else [],
            })
        databases.append({
            "id": db.id,
            "name": db.display_name,
            "display_name": db.display_name,
            "type": db.db_category,
            "tables": tables,
        })

    return SchemaResponse(databases=databases)


@router.post("/schema/refresh", tags=["Schema"])
async def refresh_schema():
    """刷新 Schema 缓存"""
    _get_schema_registry.cache_clear()
    _get_ask_service.cache_clear()
    return {"message": "Schema 缓存已刷新"}


@router.post("/schema/test-connection", tags=["Schema"])
async def test_connection(connection: dict):
    """测试数据库连接（基于 DatabaseConnectionService）"""
    from micro_genbi.database import DatabaseConnectionService

    conn_id = connection.get("id")
    if not conn_id:
        raise HTTPException(status_code=400, detail="缺少 connection id")

    try:
        async with get_db_session() as session:
            db_service = DatabaseConnectionService(session)
            conn = await db_service.get_by_id(conn_id)
            if not conn:
                raise HTTPException(status_code=404, detail="数据源不存在")

            # 使用连接工厂进行真实连接测试
            factory = get_multi_db_factory()
            result = await factory.test_connection(conn_id)

            if result["success"]:
                return result
            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"连接失败: {result.get('error', '未知错误')}"
                )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =============================================================================
# 会话接口
# =============================================================================

@router.get("/sessions", tags=["会话"])
async def list_sessions(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """获取会话列表（基于查询历史中的 session_id）"""
    user_id = current_user.get("user_id")
    tenant_id = current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        from micro_genbi.database.services import QueryHistoryService
        history_svc = QueryHistoryService(session)

        # 获取所有历史
        all_items, total = await history_svc.list_all(tenant_id=tenant_id, limit=1000, offset=0)

        # 按 session_id 分组，取每个 session 的最新记录
        session_map: dict[str, dict] = {}
        for h in all_items:
            sid = getattr(h, 'session_id', None) or getattr(h, 'id', None) or str(id(h))
            if sid not in session_map:
                ts = getattr(h, 'created_at', None)
                session_map[sid] = {
                    "id": sid,
                    "title": (getattr(h, 'natural_query', '') or '')[:100],
                    "queryCount": 1,
                    "lastQuery": getattr(h, 'natural_query', '') or '',
                    "lastActive": ts.isoformat() if ts else "",
                    "createdAt": ts.isoformat() if ts else "",
                    "userId": getattr(h, 'user_id', user_id or 'anonymous'),
                }
            else:
                session_map[sid]["queryCount"] += 1

        sessions = list(session_map.values())
        sessions.sort(key=lambda x: x.get("lastActive", ""), reverse=True)
        return {
            "items": sessions[offset:offset + limit],
            "total": len(sessions),
        }


@router.get("/sessions/{session_id}", tags=["会话"])
async def get_session(
    session_id: str,
    current_user: dict = Depends(get_current_user),
):
    """获取会话详情（包含该 session 的所有查询）"""
    tenant_id = current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        from micro_genbi.database.services import QueryHistoryService
        history_svc = QueryHistoryService(session)
        all_items, _ = await history_svc.list_all(tenant_id=tenant_id, limit=1000, offset=0)

        # 筛选匹配 session_id 的记录
        matching = []
        for h in all_items:
            sid = getattr(h, 'session_id', None)
            if sid == session_id:
                ts = getattr(h, 'created_at', None)
                matching.append({
                    "id": getattr(h, 'id', ''),
                    "naturalQuery": getattr(h, 'natural_query', '') or '',
                    "sql": getattr(h, 'generated_sql', '') or '',
                    "status": getattr(h, 'status', 'success'),
                    "executionTimeMs": getattr(h, 'execution_time_ms', 0) or 0,
                    "createdAt": ts.isoformat() if ts else "",
                })

        if not matching:
            raise HTTPException(status_code=404, detail="会话不存在")

        # 按时间排序
        matching.sort(key=lambda x: x.get("createdAt", ""))

        # 从第一条记录提取会话信息
        first = matching[0]
        return {
            "id": session_id,
            "title": (first.get("naturalQuery", "") or "")[:100],
            "queries": matching,
            "queryCount": len(matching),
            "userId": current_user.get("user_id"),
        }


# =============================================================================
# 认证接口
# =============================================================================

@router.post("/auth/login", tags=["认证"])
async def login(request: dict):
    """用户登录"""
    username = request.get("username")
    password = request.get("password")

    if not username or not password:
        raise HTTPException(status_code=400, detail="用户名和密码不能为空")

    # 优先尝试数据库认证
    async with get_db_session() as session:
        user_service = UserService(session)
        user = await user_service.verify_password(username, password)
        if user:
            import time
            from jose import jwt
            secret = os.getenv("JWT_SECRET", "micro-genbi-dev-secret-change-in-production")
            token_payload = {
                "sub": user.id,
                "tenant_id": user.tenant_id,
                "role": user.role,
                "exp": int(time.time()) + 86400,
            }
            token = jwt.encode(token_payload, secret, algorithm="HS256")

            # 记录审计日志
            try:
                audit_service = AuditService(session)
                await audit_service.log(
                    event_type="user.login",
                    user_id=user.id,
                    tenant_id=user.tenant_id,
                    result="success",
                )
            except Exception:
                pass

            return {
                "access_token": token,
                "token_type": "Bearer",
                "expires_in": 86400,
                "user": {
                    "id": user.id,
                    "username": user.username,
                    "email": user.email,
                    "role": user.role,
                    "group": user.tenant_id,
                    "subscriptionPlan": "free",
                    "createdAt": user.created_at.isoformat() if user.created_at else "",
                },
            }

    # 认证失败
    raise HTTPException(status_code=401, detail="用户名或密码错误")


@router.get("/auth/me", tags=["认证"])
async def get_me(current_user: dict = Depends(get_current_user)):
    """获取当前用户信息"""
    user_id = current_user.get("user_id")
    if not user_id:
        raise HTTPException(status_code=401, detail="未登录")

    async with get_db_session() as session:
        from sqlalchemy import select
        from micro_genbi.database.models import User
        result = await session.execute(select(User).where(User.id == user_id))
        user = result.scalar_one_or_none()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return {
            "id": user.id,
            "username": user.username,
            "email": user.email or "",
            "role": user.role,
            "group": user.tenant_id,
            "subscriptionPlan": "free",
            "createdAt": user.created_at.isoformat() if user.created_at else "",
        }


@router.post("/auth/register", tags=["认证"])
async def register(request: dict):
    """用户注册"""
    username = request.get("username")
    email = request.get("email")
    password = request.get("password")
    role = request.get("role", "user")
    group = request.get("group", "default")

    if not username or not password or not email:
        raise HTTPException(status_code=400, detail="用户名、邮箱和密码不能为空")

    # 查找或创建租户
    async with get_db_session() as session:
        from micro_genbi.database.services import TenantService
        from micro_genbi.database import CreateTenantInput

        tenant_service = TenantService(session)
        tenants = await tenant_service.list_all()
        tenant = next((t for t in tenants if t.name == group), None)
        if not tenant:
            new_tenant = await tenant_service.create(
                CreateTenantInput(name=group, description=f"租户: {group}")
            )
            tenant_id = new_tenant.id
        else:
            tenant_id = tenant.id

        # 创建用户
        user_service = UserService(session)
        try:
            result = await user_service.create(
                input=CreateUserInput(
                    username=username,
                    email=email,
                    password=password,
                    role=role,
                ),
                tenant_id=tenant_id,
            )
        except Exception as e:
            raise HTTPException(status_code=400, detail=f"注册失败: {str(e)}")

        import time
        from jose import jwt
        secret = os.getenv("JWT_SECRET", "micro-genbi-dev-secret-change-in-production")
        token_payload = {
            "sub": result.id,
            "tenant_id": result.tenant_id,
            "role": result.role,
            "exp": int(time.time()) + 86400,
        }
        token = jwt.encode(token_payload, secret, algorithm="HS256")

        return {
            "access_token": token,
            "token_type": "Bearer",
            "expires_in": 86400,
            "user": {
                "id": result.id,
                "username": result.username,
                "email": result.email,
                "role": result.role,
                "group": result.tenant_id,
                "subscriptionPlan": "free",
                "createdAt": result.created_at.isoformat() if result.created_at else "",
            },
        }


@router.post("/auth/refresh", tags=["认证"])
async def refresh_token(request: dict):
    """刷新 Token"""
    import time
    from jose import jwt, JWTError

    old_token = request.get("token")
    if not old_token:
        raise HTTPException(status_code=400, detail="缺少 token 参数")

    secret = os.getenv("JWT_SECRET", "micro-genbi-dev-secret-change-in-production")
    try:
        payload = jwt.decode(old_token, secret, algorithms=["HS256"])
    except JWTError:
        raise HTTPException(status_code=401, detail="无效的 Token")

    # 检查是否已过期太久
    exp = payload.get("exp", 0)
    if exp < time.time() - 86400 * 7:
        raise HTTPException(status_code=401, detail="Token 已过期超过7天，需要重新登录")

    # 生成新 token
    new_payload = {
        "sub": payload.get("sub"),
        "tenant_id": payload.get("tenant_id", "default"),
        "role": payload.get("role", "user"),
        "exp": int(time.time()) + 86400,
    }
    new_token = jwt.encode(new_payload, secret, algorithm="HS256")

    return {
        "access_token": new_token,
        "token_type": "Bearer",
        "expires_in": 86400,
    }


@router.get("/auth/api-keys", tags=["认证"])
async def list_api_keys():
    """获取 API Key 列表"""
    # TODO: 实现 API Key 列表
    return {"keys": []}


@router.post("/auth/api-keys", tags=["认证"])
async def create_api_key(request: dict):
    """创建 API Key"""
    # TODO: 实现 API Key 创建
    return {
        "id": "key_001",
        "name": request.get("name", "New Key"),
        "key": "mgbi_sk_xxxx...",
        "created_at": "2026-05-25T00:00:00Z",
    }


# =============================================================================
# 导出接口
# =============================================================================

@router.post("/export", response_model=ExportResponse, tags=["导出"])
async def export_data(
    request: ExportRequest,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(get_current_user),
):
    """
    异步导出查询结果

    支持 CSV、JSON、Excel、SQL、PDF 格式。
    创建导出任务后返回 export_id，客户端通过 GET /export/{export_id} 查询状态。
    """
    export_id = f"exp_{uuid.uuid4().hex[:12]}"
    user_id = current_user.get("user_id", "anonymous")

    # 获取查询数据
    data = []
    columns = []
    if request.query_id:
        # 从历史记录获取 SQL 并重新执行
        async with get_db_session() as session:
            history_svc = QueryHistoryService(session)
            # 查找历史记录
            all_items, _ = await history_svc.list_all(
                tenant_id=current_user.get("tenant_id", "default"),
                limit=1000, offset=0
            )
            for h in all_items:
                if getattr(h, 'id', None) == request.query_id:
                    sql = getattr(h, 'generated_sql', None)
                    if sql:
                        # 重新执行 SQL
                        try:
                            executor = await get_multi_db_factory().get_executor(None)
                            data = await executor.execute(sql, limit=request.max_rows)
                            if data:
                                columns = list(data[0].keys())
                        except Exception as e:
                            logger.warning(f"导出重执行失败: {e}")
                    break

    # 如果没有从 query_id 获取数据，使用直接传入的 SQL
    if not data and request.sql:
        try:
            executor = await get_multi_db_factory().get_executor(None)
            data = await executor.execute(request.sql, limit=request.max_rows)
            if data:
                columns = list(data[0].keys())
        except Exception as e:
            logger.warning(f"导出 SQL 执行失败: {e}")

    # 如果仍无数据，返回空结果
    if not data:
        return ExportResponse(export_id=export_id, status="completed")

    # 存储导出任务
    _export_tasks[export_id] = {
        "id": export_id,
        "status": "processing",
        "user_id": user_id,
        "data": data,
        "columns": columns,
        "format": request.format,
        "include_headers": request.include_headers,
        "mask_sensitive": request.mask_sensitive,
        "max_rows": request.max_rows,
    }

    # 在后台生成文件
    background_tasks.add_task(_generate_export_file, export_id)

    return ExportResponse(export_id=export_id, status="processing")


@router.get("/export/{export_id}", tags=["导出"])
async def get_export_status(export_id: str):
    """获取导出状态"""
    task = _export_tasks.get(export_id)
    if not task:
        raise HTTPException(status_code=404, detail="导出任务不存在")

    response = {
        "export_id": export_id,
        "status": task["status"],
    }
    if task["status"] == "completed":
        response["download_url"] = f"/api/v1/export/{export_id}/download"
        response["file_size"] = task.get("file_size", 0)
        response["row_count"] = task.get("row_count", 0)
    elif task["status"] == "failed":
        response["error"] = task.get("error", "导出失败")

    return response


@router.get("/export/{export_id}/download", tags=["导出"])
async def download_export(export_id: str):
    """下载导出的文件"""
    task = _export_tasks.get(export_id)
    if not task:
        raise HTTPException(status_code=404, detail="导出任务不存在")

    if task["status"] != "completed":
        raise HTTPException(status_code=400, detail=f"导出未完成，当前状态: {task['status']}")

    content = task.get("content")
    if not content:
        raise HTTPException(status_code=404, detail="文件内容不存在，可能已过期")

    filename = f"export_{export_id}.{task.get('format', 'csv')}"
    media_types = {
        "csv": "text/csv",
        "json": "application/json",
        "excel": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "sql": "application/sql",
        "pdf": "application/pdf",
    }
    return StreamingResponse(
        io.BytesIO(content),
        media_type=media_types.get(task.get("format", "csv"), "application/octet-stream"),
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


async def _generate_export_file(export_id: str) -> None:
    """后台生成导出文件"""
    task = _export_tasks.get(export_id)
    if not task:
        return

    try:
        data = task.get("data", [])
        columns = task.get("columns", [])
        fmt = task.get("format", "csv")
        include_headers = task.get("include_headers", True)

        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            if include_headers and columns:
                writer.writerow(columns)
            for row in data:
                writer.writerow([row.get(col, "") for col in columns])
            task["content"] = output.getvalue().encode("utf-8")
        elif fmt == "json":
            content = json.dumps(data, ensure_ascii=False, indent=2)
            task["content"] = content.encode("utf-8")
        else:
            # 其他格式暂时返回 CSV（Excel/PDF 需要额外库）
            output = io.StringIO()
            writer = csv.writer(output)
            if include_headers and columns:
                writer.writerow(columns)
            for row in data:
                writer.writerow([row.get(col, "") for col in columns])
            task["content"] = output.getvalue().encode("utf-8")

        task["file_size"] = len(task.get("content", b""))
        task["row_count"] = len(data)
        task["status"] = "completed"

    except Exception as e:
        logger.error(f"导出生成失败: {export_id}: {e}")
        task["status"] = "failed"
        task["error"] = str(e)


# =============================================================================
# 历史记录接口
# =============================================================================

@router.get("/history", tags=["历史"])
async def get_history(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    current_user: dict = Depends(get_current_user),
):
    """获取查询历史"""
    user_id = current_user.get("user_id")
    tenant_id = current_user.get("tenant_id", "default")

    async with get_db_session() as session:
        service = QueryHistoryService(session)
        if user_id:
            items = await service.get_by_user(user_id, limit=limit, offset=offset)
            if items:
                return {"items": [_h_to_dict(h) for h in items], "total": len(items)}
        # 降级到租户级查询
        items, total = await service.list_all(tenant_id=tenant_id, limit=limit, offset=offset)
        return {"items": [_h_to_dict(h) for h in items], "total": total}
    return {"items": [], "total": 0}


@router.delete("/history/{history_id}", tags=["历史"])
async def delete_history(
    history_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除历史记录"""
    async with get_db_session() as session:
        service = QueryHistoryService(session)
        success = await service.delete(history_id)
        if not success:
            raise HTTPException(status_code=404, detail="历史记录不存在")
        return {"message": "已删除"}


# =============================================================================
# 注册表接口
# =============================================================================

@router.get("/registry", tags=["注册表"])
async def get_registry(current_user: dict = Depends(get_current_user)):
    """获取语义注册表（跨库关系配置）"""
    registry = _get_schema_registry()
    # _cross_db_relations 是内部属性，直接访问
    relations = getattr(registry, "_cross_db_relations", [])
    return [
        {
            "virtualSchema": getattr(r, "name", str(r)) if hasattr(r, "name") else str(r),
            "sourceNode": getattr(r, "source", "") if hasattr(r, "source") else "",
            "sourceEntity": getattr(r, "source_table", "") if hasattr(r, "source_table") else "",
            "type": getattr(r, "type", "cross_db") if hasattr(r, "type") else "cross_db",
        }
        for r in (relations or [])
    ]


# =============================================================================
# 订阅接口
# =============================================================================

@router.get("/subscriptions", tags=["订阅"])
async def list_subscriptions(current_user: dict = Depends(get_current_user)):
    """获取订阅列表"""
    try:
        service = SubscriptionService()
        subs = service.list_subscriptions()
        return {"items": [_sub_to_dict(s) for s in subs]}
    except Exception as e:
        logger.warning(f"订阅列表获取失败: {e}")
        return {"items": []}


@router.post("/subscriptions", tags=["订阅"])
async def create_subscription(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """创建订阅"""
    try:
        service = SubscriptionService()
        sub = service.create_subscription(
            user_id=current_user.get("user_id", "anonymous"),
            name=request.get("name", ""),
            query=request.get("query_description", ""),
            schedule=request.get("schedule", "0 * * * *"),
        )
        return _sub_to_dict(sub)
    except Exception as e:
        logger.warning(f"创建订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"创建订阅失败: {str(e)}")


@router.patch("/subscriptions/{subscription_id}", tags=["订阅"])
async def update_subscription(
    subscription_id: str,
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """更新订阅状态"""
    try:
        service = SubscriptionService()
        sub_id = int(subscription_id)
        # 区分 status 更新和其他更新
        if "status" in request:
            if request["status"] == "paused":
                service.pause_subscription(sub_id)
            else:
                service.resume_subscription(sub_id)
        updated = service.get_subscription(sub_id)
        if not updated:
            raise HTTPException(status_code=404, detail="订阅不存在")
        return _sub_to_dict(updated)
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的订阅ID")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"更新订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新订阅失败: {str(e)}")


@router.delete("/subscriptions/{subscription_id}", tags=["订阅"])
async def delete_subscription(
    subscription_id: str,
    current_user: dict = Depends(get_current_user),
):
    """删除订阅"""
    try:
        service = SubscriptionService()
        success = service.delete_subscription(int(subscription_id))
        if not success:
            raise HTTPException(status_code=404, detail="订阅不存在")
        return {"message": "订阅已删除"}
    except ValueError:
        raise HTTPException(status_code=400, detail="无效的订阅ID")
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"删除订阅失败: {e}")
        raise HTTPException(status_code=500, detail=f"删除订阅失败: {str(e)}")


# =============================================================================
# 图表推荐接口
# =============================================================================

@router.post("/chart/recommend", tags=["图表"])
async def recommend_chart(request: dict):
    """推荐图表类型"""
    columns = request.get("columns", [])
    data = request.get("data", [])
    intent = request.get("intent")

    try:
        recommender = ChartRecommender()
        result = recommender.recommend(columns=columns, data=data, intent=intent)
        return result
    except Exception as e:
        logger.warning(f"图表推荐失败: {e}")
        # 降级返回默认推荐
        return {
            "recommended": "table",
            "confidence": 0.5,
            "reason": "基于数据特征推荐",
            "alternatives": ["bar", "line"],
            "suggested_configs": {},
        }


# =============================================================================
# 异常检测接口
# =============================================================================

from micro_genbi.service.anomaly_detector import AnomalyDetector

_anomaly_detector = AnomalyDetector()


@router.post("/query/anomaly-detect", tags=["查询"])
async def detect_anomalies(
    request: dict,
    current_user: dict = Depends(get_current_user),
):
    """
    对查询结果数据进行异常检测。

    支持 Z-Score 和 IQR 两种检测方法，返回异常记录列表和摘要。
    """
    data = request.get("data", [])
    columns = request.get("columns", [])
    method = request.get("method", "zscore")
    threshold = request.get("threshold", 3.0)

    if not data or not columns:
        return {"anomalies": [], "summary": {}, "severity_counts": {}}

    try:
        result = _anomaly_detector.detect_anomalies(
            data=data,
            columns=columns,
            method=method,
            threshold=threshold,
        )
        return {
            "anomalies": [
                {
                    "row_index": a.row_index,
                    "column": a.column,
                    "value": a.value,
                    "expected_range": list(a.expected_range),
                    "score": a.score,
                    "severity": a.severity,
                }
                for a in result.anomalies
            ],
            "summary": result.summary,
            "severity_counts": result.severity_counts,
        }
    except Exception as e:
        logger.warning(f"异常检测失败: {e}")
        return {"anomalies": [], "summary": {}, "severity_counts": {}}


# =============================================================================
# 查询建议接口
# =============================================================================

@router.get("/query/suggestions", tags=["查询"])
async def get_query_suggestions(
    q: str = Query(..., description="用户输入的查询文本"),
    current_user: dict = Depends(get_current_user),
):
    """
    获取查询建议列表。

    根据用户输入返回查询建议，包括：
    - 常用查询模板匹配
    - Schema 字段联想
    - 历史查询推荐
    - 时间限定词扩展
    """
    try:
        suggester = _get_query_suggester()
        user_id = current_user.get("user_id", "default")
        suggestions = suggester.get_suggestions(q, user_id=user_id)
        return {
            "suggestions": [
                {
                    "text": s.text,
                    "type": s.type,
                    "confidence": s.confidence,
                    "metadata": s.metadata,
                }
                for s in suggestions
            ]
        }
    except Exception as e:
        logger.warning(f"查询建议获取失败: {e}")
        return {"suggestions": []}


# =============================================================================
# SQL 版本管理接口
# =============================================================================

@router.get("/history/versions", tags=["历史"])
async def list_sql_versions(
    question: str = Query(..., description="查询问题（用于匹配相关版本）"),
    limit: int = Query(20, ge=1, le=100, description="返回数量"),
    current_user: dict = Depends(get_current_user),
):
    """
    获取指定问题相关的 SQL 版本列表。
    """
    try:
        service = _get_sql_versioning()
        user_id = current_user.get("user_id", "default")
        versions = service.list_versions(question=question, user_id=user_id, limit=limit)
        return {
            "items": [
                {
                    "id": v.id,
                    "question": v.question,
                    "sql": v.sql,
                    "created_at": v.created_at.isoformat() if v.created_at else "",
                    "parent_version_id": v.parent_version_id,
                    "change_summary": v.change_summary,
                }
                for v in versions
            ],
            "total": len(versions),
        }
    except Exception as e:
        logger.warning(f"SQL 版本列表获取失败: {e}")
        return {"items": [], "total": 0}


@router.get("/history/versions/compare", tags=["历史"])
async def compare_sql_versions(
    version_id1: int = Query(..., description="版本1 ID"),
    version_id2: int = Query(..., description="版本2 ID"),
    current_user: dict = Depends(get_current_user),
):
    """
    对比两个 SQL 版本的差异。
    """
    try:
        service = _get_sql_versioning()
        diff = service.compare_versions(version_id1=version_id1, version_id2=version_id2)
        return diff
    except Exception as e:
        logger.warning(f"SQL 版本对比失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/history/versions/{version_id}/rollback", tags=["历史"])
async def rollback_sql_version(
    version_id: int,
    current_user: dict = Depends(get_current_user),
):
    """
    回滚到指定 SQL 版本。
    """
    try:
        service = _get_sql_versioning()
        version = service.get_version(version_id)
        if not version:
            raise HTTPException(status_code=404, detail="版本不存在")
        return {
            "sql": version.sql,
            "message": f"已回滚到版本 {version_id}",
            "version_id": version_id,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"SQL 版本回滚失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 操作追踪接口
# =============================================================================

@router.get("/trace/{task_id}", tags=["追踪"])
async def get_operation_trace(
    task_id: str,
    current_user: dict = Depends(get_current_user),
):
    """
    获取指定任务的完整操作追踪信息。
    """
    try:
        service = _get_operation_trace()
        trace = service.get_trace(task_id)
        if not trace:
            raise HTTPException(status_code=404, detail="追踪记录不存在")
        return {
            "id": trace.id,
            "operation_id": trace.operation_id,
            "operation_type": trace.operation_type,
            "total_duration_ms": trace.total_duration_ms,
            "status": trace.status.value if hasattr(trace.status, "value") else str(trace.status),
            "steps": [
                {
                    "id": s.id,
                    "type": s.type.value if hasattr(s.type, "value") else str(s.type),
                    "input_summary": s.input_summary,
                    "output_summary": s.output_summary,
                    "duration_ms": s.duration_ms,
                    "status": s.status.value if hasattr(s.status, "value") else str(s.status),
                    "metadata": s.metadata,
                }
                for s in trace.steps
            ],
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"操作追踪获取失败: {e}")
        raise HTTPException(status_code=400, detail=str(e))


# =============================================================================
# 辅助函数
# =============================================================================

def _h_to_dict(h) -> dict:
    """QueryHistory → dict"""
    return {
        "id": h.id,
        "naturalQuery": h.natural_query,
        "sql": h.generated_sql or "",
        "intent": h.intent or "",
        "status": h.status or "success",
        "executionTimeMs": h.execution_time_ms or 0,
        "createdAt": h.created_at.isoformat() if h.created_at else "",
    }


def _sub_to_dict(s) -> dict:
    """Subscription → dict"""
    return {
        "id": s.id,
        "name": s.name,
        "query_description": getattr(s, "query_description", ""),
        "schedule": getattr(s, "schedule", ""),
        "schedule_label": getattr(s, "schedule_label", ""),
        "status": getattr(s, "status", "active"),
        "last_run_at": getattr(s, "last_run_at", None),
        "next_run_at": getattr(s, "next_run_at", None),
    }


async def _execute_query_task(task_id: str):
    """后台执行查询任务"""
    try:
        _tasks[task_id]["status"] = "running"
        _tasks[task_id]["progress"] = 10
        _tasks[task_id]["current_step"] = "intent_classification"

        task_data = _tasks[task_id]
        request = task_data.get("request", {})
        user_id = task_data.get("user_id")
        tenant_id = task_data.get("tenant_id")
        role = task_data.get("role", "user")

        query_text = request.get("query", "")

        # 步骤进度映射
        steps = [
            ("intent_classification", 10, 30),
            ("schema_retrieval", 30, 40),
            ("sql_generation", 40, 70),
            ("sql_validation", 70, 75),
            ("sql_execution", 75, 90),
            ("data_masking", 90, 95),
            ("building_response", 95, 100),
        ]

        # 执行查询
        service = _get_ask_service()
        _tasks[task_id]["progress"] = 30
        _tasks[task_id]["current_step"] = "sql_generation"

        result = await service.ask(
            query=query_text,
            user_id=user_id,
            role=role,
        )

        _tasks[task_id]["progress"] = 95
        _tasks[task_id]["current_step"] = "building_response"

        # 生成图表
        if result.data:
            chart_engine = _get_chart_engine()
            chart = chart_engine.generate(data=result.data, intent=result.summary)
            if chart:
                result.chart = chart

        _tasks[task_id]["status"] = "success"
        _tasks[task_id]["progress"] = 100
        _tasks[task_id]["current_step"] = "complete"
        _tasks[task_id]["result"] = {
            "sql": result.sql,
            "row_count": result.row_count,
            "summary": result.summary,
            "chart": result.chart,
        }

    except Exception as e:
        _tasks[task_id]["status"] = "failed"
        _tasks[task_id]["error"] = {
            "code": "INTERNAL_ERROR",
            "message": str(e),
        }
