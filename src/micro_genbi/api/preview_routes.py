"""Preview API Routes - 实时数据预览路由

提供 FastAPI 路由端点：
- POST /api/v1/preview - 预览端点
- GET /api/v1/preview/{query_id} - 通过历史查询 ID 预览
"""

from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, HTTPException, Depends, Query
from pydantic import BaseModel, Field

from micro_genbi import get_logger
from micro_genbi.errors import GenBIError, SQLValidationError, SQLExecutionError
from micro_genbi.api.dependencies import get_current_user
from micro_genbi.api.preview import (
    PreviewAPI,
    PreviewResult,
    get_preview_api,
    DEFAULT_PREVIEW_LIMIT,
    MAX_PREVIEW_LIMIT,
)

logger = get_logger(__name__)
router = APIRouter(prefix="/preview", tags=["预览"])


# =============================================================================
# 请求/响应模型
# =============================================================================

class PreviewRequest(BaseModel):
    """预览请求"""
    sql: str = Field(..., description="SQL 查询语句", min_length=1)
    db_profile: str = Field("default", description="数据库配置名称")
    limit: int = Field(
        DEFAULT_PREVIEW_LIMIT,
        ge=1,
        le=MAX_PREVIEW_LIMIT,
        description=f"预览行数限制（1-{MAX_PREVIEW_LIMIT}）"
    )


class PreviewResponse(BaseModel):
    """预览响应"""
    sql: str = Field(..., description="执行的 SQL 语句")
    columns: list[str] = Field(..., description="列名列表")
    rows: list[dict] = Field(..., description="预览数据行")
    row_count: int = Field(..., description="总行数（截断前）")
    preview_count: int = Field(..., description="返回行数")
    execution_time_ms: int = Field(..., description="执行耗时（毫秒）")
    generated_at: str = Field(..., description="结果生成时间（ISO 格式）")
    is_truncated: bool = Field(..., description="是否被截断")

    model_config = {
        "json_schema_extra": {
            "example": {
                "sql": "SELECT * FROM orders LIMIT 5",
                "columns": ["id", "customer_id", "amount", "created_at"],
                "rows": [
                    {"id": 1, "customer_id": 101, "amount": 250.00, "created_at": "2024-01-15"},
                    {"id": 2, "customer_id": 102, "amount": 180.50, "created_at": "2024-01-16"},
                ],
                "row_count": 1542,
                "preview_count": 5,
                "execution_time_ms": 45,
                "generated_at": "2024-01-20T10:30:00",
                "is_truncated": True,
            }
        }
    }


class PreviewErrorResponse(BaseModel):
    """预览错误响应"""
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    details: Optional[dict] = Field(None, description="错误详情")


# =============================================================================
# 依赖项
# =============================================================================

def get_preview_service() -> PreviewAPI:
    """获取 PreviewAPI 服务实例"""
    return get_preview_api()


# =============================================================================
# 路由
# =============================================================================

@router.post(
    "/preview",
    response_model=PreviewResponse,
    responses={
        400: {"model": PreviewErrorResponse, "description": "SQL 执行错误"},
        401: {"model": PreviewErrorResponse, "description": "未认证"},
        422: {"model": PreviewErrorResponse, "description": "SQL 验证失败"},
        500: {"model": PreviewErrorResponse, "description": "服务器内部错误"},
    },
    summary="预览查询结果",
    description="""
执行快速数据预览。

特性：
- 限制返回行数（默认 5 行），加快响应速度
- 自动验证 SQL 安全性
- 返回总行数与预览行数，用于判断是否截断

适用场景：
- 用户在执行完整查询前预览数据
- 快速检查查询结果是否符合预期
- 查看大表的样本数据
    """,
)
async def preview_data(
    request: PreviewRequest,
    current_user: dict = Depends(get_current_user),
    preview_api: PreviewAPI = Depends(get_preview_service),
) -> PreviewResponse:
    """
    执行数据预览

    Args:
        request: 预览请求，包含 SQL、数据库配置、限制行数
        current_user: 当前用户（来自认证依赖）
        preview_api: PreviewAPI 实例

    Returns:
        PreviewResponse: 预览结果

    Raises:
        HTTPException: 验证或执行失败
    """
    try:
        logger.info(f"预览请求: user={current_user.get('user_id')}, sql={request.sql[:50]}...")

        result = await preview_api.preview(
            sql=request.sql,
            db_profile=request.db_profile,
            limit=request.limit,
        )

        return _to_preview_response(result)

    except SQLValidationError as e:
        logger.warning(f"SQL 验证失败: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "SQL_VALIDATION_ERROR",
                "message": e.message,
                "details": {
                    "violation_type": getattr(e, "violation_type", "unknown"),
                    "sql": request.sql,
                },
            },
        )

    except SQLExecutionError as e:
        logger.error(f"SQL 执行失败: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "SQL_EXECUTION_ERROR",
                "message": e.message,
                "details": {
                    "sql": request.sql,
                    "phase": e.phase,
                },
            },
        )

    except GenBIError as e:
        logger.error(f"预览失败: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": e.code,
                "message": e.message,
                "details": e.details,
            },
        )

    except Exception as e:
        logger.error(f"预览请求异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "预览请求处理失败",
            },
        )


@router.get(
    "/preview/{query_id}",
    response_model=PreviewResponse,
    responses={
        400: {"model": PreviewErrorResponse, "description": "预览失败"},
        401: {"model": PreviewErrorResponse, "description": "未认证"},
        404: {"model": PreviewErrorResponse, "description": "查询记录不存在"},
        500: {"model": PreviewErrorResponse, "description": "服务器内部错误"},
    },
    summary="通过历史查询 ID 预览",
    description="""
通过历史查询记录 ID 获取数据预览。

从查询历史中获取原始 SQL，然后执行预览。
适用于：
- 查看之前执行过的查询结果
- 快速重现有趣的查询
- 基于历史查询进行二次预览
    """,
)
async def preview_by_query_id(
    query_id: int,
    current_user: dict = Depends(get_current_user),
    preview_api: PreviewAPI = Depends(get_preview_service),
) -> PreviewResponse:
    """
    通过历史查询 ID 获取预览

    Args:
        query_id: 历史查询记录 ID
        current_user: 当前用户（来自认证依赖）
        preview_api: PreviewAPI 实例

    Returns:
        PreviewResponse: 预览结果

    Raises:
        HTTPException: 记录不存在或预览失败
    """
    try:
        logger.info(f"历史查询预览: user={current_user.get('user_id')}, query_id={query_id}")

        result = await preview_api.preview_by_query_id(query_id=query_id)

        return _to_preview_response(result)

    except GenBIError as e:
        if e.code == "RECORD_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "RECORD_NOT_FOUND",
                    "message": e.message,
                },
            )
        elif e.code == "SQL_NOT_FOUND":
            raise HTTPException(
                status_code=404,
                detail={
                    "error": "SQL_NOT_FOUND",
                    "message": e.message,
                },
            )
        else:
            raise HTTPException(
                status_code=400,
                detail={
                    "error": e.code,
                    "message": e.message,
                },
            )

    except SQLValidationError as e:
        logger.warning(f"SQL 验证失败: {e}")
        raise HTTPException(
            status_code=422,
            detail={
                "error": "SQL_VALIDATION_ERROR",
                "message": e.message,
            },
        )

    except SQLExecutionError as e:
        logger.error(f"SQL 执行失败: {e}")
        raise HTTPException(
            status_code=400,
            detail={
                "error": "SQL_EXECUTION_ERROR",
                "message": e.message,
            },
        )

    except Exception as e:
        logger.error(f"历史查询预览异常: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "INTERNAL_ERROR",
                "message": "预览请求处理失败",
            },
        )


@router.get(
    "/preview-options",
    summary="预览配置选项",
    description="获取预览功能的配置信息",
)
async def get_preview_options() -> dict:
    """
    获取预览配置选项

    Returns:
        dict: 预览配置信息
    """
    return {
        "default_limit": DEFAULT_PREVIEW_LIMIT,
        "max_limit": MAX_PREVIEW_LIMIT,
        "timeout_seconds": 10,
        "features": {
            "sql_validation": True,
            "truncation_info": True,
            "history_preview": True,
        },
    }


# =============================================================================
# 辅助函数
# =============================================================================

def _to_preview_response(result: PreviewResult) -> PreviewResponse:
    """将 PreviewResult 转换为 PreviewResponse"""
    return PreviewResponse(
        sql=result.sql,
        columns=result.columns,
        rows=result.rows,
        row_count=result.row_count,
        preview_count=result.preview_count,
        execution_time_ms=result.execution_time_ms,
        generated_at=result.generated_at.isoformat(),
        is_truncated=result.is_truncated,
    )
