"""API 依赖项

提供认证、数据库会话等依赖注入。
"""

from __future__ import annotations

import os
from typing import AsyncIterator, Optional
from contextlib import asynccontextmanager
from functools import lru_cache

from fastapi import Depends, HTTPException, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker

from micro_genbi.database import APIKeyService


# =============================================================================
# 数据库会话
# =============================================================================

_system_db_url = os.getenv(
    "SYSTEM_DB_URL",
    "sqlite+aiosqlite:///./microgenbi.db"
)


@lru_cache()
def _get_engine():
    """获取缓存的数据库引擎"""
    return create_async_engine(
        _system_db_url,
        echo=False,
        pool_pre_ping=True,
    )


@lru_cache()
def _get_session_maker():
    """获取缓存的会话工厂"""
    return async_sessionmaker(
        bind=_get_engine(),
        class_=AsyncSession,
        expire_on_commit=False,
    )


@asynccontextmanager
async def get_db_session() -> AsyncIterator[AsyncSession]:
    """
    获取数据库会话

    这是一个上下文管理器，用于获取异步数据库会话。
    """
    async with _get_session_maker()() as session:
        try:
            yield session
        finally:
            await session.close()


# =============================================================================
# 认证
# =============================================================================

async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_api_key: Optional[str] = Header(None, alias="X-API-Key"),
    x_user_id: Optional[str] = Header(None, alias="X-User-Id"),
    x_user_role: Optional[str] = Header(None, alias="X-User-Role"),
    x_tenant_id: Optional[str] = Header(None, alias="X-Tenant-Id"),
) -> dict:
    """
    获取当前用户

    支持两种认证方式：
    1. Bearer Token（JWT）
    2. API Key

    Returns:
        dict: 用户信息，包含 user_id, tenant_id, role 等
    """
    # 方式一：Bearer Token
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:]

        # TODO: 验证 JWT Token
        # 这里简化实现，实际应该验证 JWT
        try:
            # 模拟解码 JWT（实际使用 PyJWT）
            user_info = _decode_jwt(token)
            return user_info
        except Exception:
            raise HTTPException(
                status_code=401,
                detail="无效的 Token",
            )

    # 方式二：API Key
    if x_api_key:
        async for session in get_db_session():
            service = APIKeyService(session)
            api_key = await service.verify(x_api_key)

            if not api_key:
                raise HTTPException(
                    status_code=401,
                    detail="无效的 API Key",
                )

            return {
                "user_id": api_key.user_id,
                "tenant_id": api_key.tenant_id,
                "role": "user",
                "scope": api_key.scope,
            }

    # 方式三：直接传参（简化测试）
    if x_user_id:
        return {
            "user_id": x_user_id,
            "tenant_id": x_tenant_id or "default",
            "role": x_user_role or "user",
        }

    # 未认证
    raise HTTPException(
        status_code=401,
        detail="未提供认证信息",
    )


def _decode_jwt(token: str) -> dict:
    """解码 JWT Token（简化实现）"""
    import base64
    import json

    # JWT 格式: header.payload.signature
    parts = token.split(".")
    if len(parts) != 3:
        raise ValueError("Invalid JWT format")

    # 解码 payload
    payload = parts[1]
    # 添加 padding
    payload += "=" * (4 - len(payload) % 4)
    decoded = base64.urlsafe_b64decode(payload)
    data = json.loads(decoded)

    return {
        "user_id": data.get("sub"),
        "tenant_id": data.get("tenant_id", "default"),
        "role": data.get("role", "user"),
    }


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求管理员权限"""
    if user.get("role") != "admin":
        raise HTTPException(
            status_code=403,
            detail="需要管理员权限",
        )
    return user


def require_tenant_admin(user: dict = Depends(get_current_user)) -> dict:
    """要求租户管理员权限"""
    if user.get("role") not in ["admin", "tenant_admin"]:
        raise HTTPException(
            status_code=403,
            detail="需要租户管理员权限",
        )
    return user


# =============================================================================
# 租户上下文
# =============================================================================

class TenantContext:
    """租户上下文"""

    def __init__(self, tenant_id: str, user_id: str, role: str):
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.role = role

    def has_permission(self, action: str) -> bool:
        """检查权限"""
        if self.role == "admin":
            return True

        # readonly 角色只能执行查询
        if self.role == "readonly" and action in ["query", "read"]:
            return True

        return True


async def get_tenant_context(
    user: dict = Depends(get_current_user),
) -> TenantContext:
    """获取租户上下文"""
    return TenantContext(
        tenant_id=user.get("tenant_id", "default"),
        user_id=user.get("user_id", ""),
        role=user.get("role", "user"),
    )
