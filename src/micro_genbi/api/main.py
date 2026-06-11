"""FastAPI 主应用

Micro-GenBI REST API 入口。
"""

from __future__ import annotations

import time
from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import JSONResponse
from fastapi.openapi.docs import get_swagger_ui_html, get_redoc_html

from micro_genbi import __version__, setup_logging, get_logger
from micro_genbi.models import SystemHealth, HealthCheckResult
from micro_genbi.errors import GenBIError, GenBIReRetry

from micro_genbi.api import routes, config_routes, schema_routes
from micro_genbi.api.preview_routes import router as preview_router

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """应用生命周期"""
    # 启动
    setup_logging()
    logger.info(f"Micro-GenBI v{__version__} 启动中...")

    # 启动多库连接工厂清理任务
    from micro_genbi.db.connection_factory import get_multi_db_factory
    factory = get_multi_db_factory()
    factory.start_cleanup()
    logger.info("多库连接工厂已启动")

    # 初始化系统数据库（包含跨库关联表）
    try:
        from micro_genbi.database.models import init_async_db
        from micro_genbi.database.cross_db_models import (
            CrossDBRelation, ConnectionGroup, ConnectionGroupMember,
        )
        from micro_genbi.api.dependencies import get_db_session, _get_session_maker

        # 确保所有表都已创建
        engine = _get_session_maker().kw.get("bind")
        if engine is None:
            engine = _get_session_maker().bind

        async with engine.begin() as conn:
            # 确保 Base 元数据包含所有模型
            from micro_genbi.database.models import Base
            # 手动注册跨库关联模型到 Base
            Base.metadata._add_table(
                CrossDBRelation.__table__.name,
                CrossDBRelation.__table__.schema,
                CrossDBRelation.__table__
            )
            Base.metadata._add_table(
                ConnectionGroup.__table__.name,
                ConnectionGroup.__table__.schema,
                ConnectionGroup.__table__
            )
            Base.metadata._add_table(
                ConnectionGroupMember.__table__.name,
                ConnectionGroupMember.__table__.schema,
                ConnectionGroupMember.__table__
            )
            await conn.run_sync(Base.metadata.create_all)
        logger.info("系统数据库初始化完成")
    except Exception as e:
        logger.warning(f"数据库初始化警告: {e}")

    # 自动创建默认 admin 用户（如果不存在）
    try:
        from micro_genbi.database.services import TenantService, UserService
        from micro_genbi.database import CreateTenantInput, CreateUserInput
        import bcrypt

        async with get_db_session() as session:
            tenant_service = TenantService(session)
            tenants = await tenant_service.list_all()
            tenant = next((t for t in tenants if t.name == "系统运维处"), None)
            if not tenant:
                tenant = await tenant_service.create(
                    CreateTenantInput(name="系统运维处", description="系统管理租户")
                )
                logger.info(f"自动创建默认租户: {tenant.name} (id={tenant.id})")

            user_service = UserService(session)
            admin_user = await user_service.get_by_username("admin")
            if not admin_user:
                admin = await user_service.create(
                    input=CreateUserInput(
                        username="admin",
                        email="admin@microgenbi.cn",
                        password="admin123",
                        role="admin",
                    ),
                    tenant_id=tenant.id,
                )
                logger.info(f"自动创建默认管理员用户: admin / admin123 (id={admin.id})")
            else:
                logger.info("管理员用户已存在，跳过创建")
    except Exception as e:
        logger.warning(f"自动创建默认用户失败: {e}")

    yield

    # 关闭
    logger.info("Micro-GenBI 关闭中...")
    await factory.stop_cleanup()
    await factory.dispose_all()
    logger.info("多库连接工厂已关闭")


app = FastAPI(
    title="Micro-GenBI Text-to-SQL API",
    description="""
## 简介

Micro-GenBI 是一个企业级 Text2SQL 智能分析平台，提供自然语言数据查询能力。

## 认证方式

### 方式一：JWT Token
```
Authorization: Bearer <access_token>
```

### 方式二：API Key
```
X-API-Key: <your-api-key>
X-User-Id: <user-id>
X-User-Role: <role>
```

## 注意事项

- 所有请求必须使用 HTTPS
- 请求 Content-Type: application/json
- 响应均为 JSON 格式
    """,
    version=__version__,
    lifespan=lifespan,
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

# 中间件
app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 生产环境应限制
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)


# 请求日志中间件
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """记录请求日志"""
    start_time = time.time()

    # 跳过日志的路径
    skip_logging = ["/health", "/metrics", "/docs", "/openapi.json", "/redoc"]
    should_log = not any(request.url.path.startswith(p) for p in skip_logging)

    if should_log:
        logger.info(f"请求: {request.method} {request.url.path}")

    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"请求异常: {request.method} {request.url.path} - {e}")
        raise

    if should_log:
        duration = (time.time() - start_time) * 1000
        logger.info(
            f"响应: {request.method} {request.url.path} "
            f"- {response.status_code} ({duration:.1f}ms)"
        )

    return response


# 异常处理
@app.exception_handler(GenBIError)
async def genbi_error_handler(request: Request, exc: GenBIError) -> JSONResponse:
    """GenBI 异常处理"""
    return JSONResponse(
        status_code=400 if "VALIDATION" in exc.code else 500,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "phase": exc.phase,
                "details": exc.details,
            }
        },
    )


@app.exception_handler(GenBIReRetry)
async def retry_error_handler(request: Request, exc: GenBIReRetry) -> JSONResponse:
    """可重试异常处理"""
    return JSONResponse(
        status_code=503,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "phase": exc.phase,
                "can_retry": exc.can_retry,
                "retry_count": exc.retry_count,
            }
        },
    )


@app.exception_handler(Exception)
async def general_error_handler(request: Request, exc: Exception) -> JSONResponse:
    """通用异常处理"""
    logger.error(f"未处理异常: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={
            "error": {
                "code": "INTERNAL_ERROR",
                "message": "服务器内部错误",
            }
        },
    )


# 健康检查
@app.get("/health", response_model=SystemHealth, tags=["系统"])
async def health_check() -> SystemHealth:
    """
    综合健康检查

    返回系统各组件的健康状态。
    """
    checks: dict[str, HealthCheckResult] = {}

    # 1. 数据库检查（示例）
    try:
        from micro_genbi.db import get_executor
        executor = get_executor()
        start = time.time()
        await executor.test_connection()
        latency = int((time.time() - start) * 1000)
        checks["database"] = HealthCheckResult(
            status="healthy",
            latency_ms=latency,
        )
    except Exception as e:
        checks["database"] = HealthCheckResult(
            status="unhealthy",
            message=str(e),
        )

    # 2. LLM 检查（示例）
    try:
        from micro_genbi.llm.base import create_llm_client
        client = create_llm_client()
        checks["llm"] = HealthCheckResult(
            status="healthy",
            latency_ms=None,
        )
    except Exception as e:
        checks["llm"] = HealthCheckResult(
            status="degraded",
            message="LLM 未配置或不可用",
        )

    # 总体状态
    statuses = [c.status for c in checks.values()]
    if "unhealthy" in statuses:
        overall = "unhealthy"
    elif "degraded" in statuses:
        overall = "degraded"
    else:
        overall = "healthy"

    return SystemHealth(
        status=overall,
        checks=checks,
        version=__version__,
    )


# 根路径
@app.get("/", tags=["系统"])
async def root():
    """API 根路径"""
    return {
        "name": "Micro-GenBI",
        "version": __version__,
        "docs": "/docs",
        "health": "/health",
    }


# 注册路由
app.include_router(routes.router, prefix="/api/v1")
app.include_router(config_routes.router, prefix="/api/v1")
app.include_router(schema_routes.router, prefix="/api/v1")
app.include_router(preview_router)


# 自定义 Swagger UI
@app.get("/docs", include_in_schema=False)
async def custom_swagger_ui_html():
    """自定义 Swagger UI"""
    return get_swagger_ui_html(
        openapi_url="/openapi.json",
        title="Micro-GenBI API 文档",
        swagger_ui_parameters={
            "defaultModelsExpandDepth": 1,
            "defaultModelExpandDepth": 1,
            "docExpansion": "list",
            "filter": True,
            "showExtensions": True,
            "showCommonExtensions": True,
        },
    )


def create_app() -> FastAPI:
    """创建应用（用于 uvicorn）"""
    return app
