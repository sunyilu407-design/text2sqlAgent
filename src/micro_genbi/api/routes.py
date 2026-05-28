"""API 路由定义"""

from __future__ import annotations

import os
import asyncio
import json
import uuid
from typing import Optional, Any
from functools import lru_cache

from fastapi import APIRouter, HTTPException, BackgroundTasks, Depends, Query
from fastapi.responses import StreamingResponse

from micro_genbi.models import (
    QueryRequest,
    QueryResponse,
    TaskInfo,
    TaskResult,
    TaskProgressEvent,
    SchemaResponse,
    ExportRequest,
    ExportResponse,
    ChartType,
)
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
from micro_genbi.semantic.schema_registry import SchemaRegistry
from micro_genbi.chart import ChartEngine
from micro_genbi.database.services import QueryHistoryService
from micro_genbi.db.connection_factory import get_multi_db_factory

logger = get_logger(__name__)
router = APIRouter()

# 模拟任务存储（生产环境应使用 Redis）
_tasks: dict[str, dict] = {}


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
                async for session in get_db_session():
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
                    break
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
        async for session in get_db_session():
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


@router.post("/query/async", response_model=TaskInfo, tags=["查询"])
async def query_async(
    request: QueryRequest,
    background_tasks: BackgroundTasks,
):
    """
    异步执行查询

    返回任务 ID，客户端通过 GET /api/v1/query/async/{task_id} 轮询状态。
    """
    task_id = f"task_{uuid.uuid4().hex[:12]}"

    user_id = request.user_id or "anonymous"
    tenant_id = request.user_id or "default"
    role = request.role or "user"

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
        async for session in get_db_session():
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
):
    """获取会话列表"""
    # TODO: 实现会话列表
    return {
        "items": [],
        "total": 0,
    }


@router.get("/sessions/{session_id}", tags=["会话"])
async def get_session(session_id: str):
    """获取会话详情"""
    # TODO: 实现会话详情
    raise HTTPException(status_code=404, detail="会话不存在")


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

    # TODO: 实现认证逻辑
    return {
        "access_token": "mock_token",
        "refresh_token": "mock_refresh_token",
        "expires_in": 3600,
        "user": {
            "id": "user_001",
            "username": username,
            "role": "user",
            "tenant_id": "tenant_001",
        },
    }


@router.post("/auth/refresh", tags=["认证"])
async def refresh_token(request: dict):
    """刷新 Token"""
    # TODO: 实现 Token 刷新
    return {
        "access_token": "new_token",
        "expires_in": 3600,
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
async def export_data(request: ExportRequest):
    """导出查询结果"""
    export_id = f"exp_{uuid.uuid4().hex[:12]}"

    return ExportResponse(
        export_id=export_id,
        status="pending",
    )


@router.get("/export/{export_id}", tags=["导出"])
async def get_export_status(export_id: str):
    """获取导出状态"""
    # TODO: 实现导出状态查询
    return {
        "export_id": export_id,
        "status": "completed",
        "download_url": f"/api/v1/export/{export_id}/download",
    }


# =============================================================================
# 辅助函数
# =============================================================================

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
