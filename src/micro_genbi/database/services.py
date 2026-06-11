"""系统数据库服务

提供系统数据库的 CRUD 操作和管理功能。
"""

from __future__ import annotations

import uuid
import secrets
import hashlib
from datetime import datetime
from typing import Optional, Any
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, delete, and_, or_, func
from sqlalchemy.orm import Session

from micro_genbi.database.models import (
    Base, Tenant, User, TenantMember,
    Project, ProjectMember,
    LLMConfig, DatabaseConnection, SchemaConfig,
    QueryHistory, Session as SessionModel, APIKey, AuditLog,
    UserRole, QueryStatus,
)


@dataclass
class CreateTenantInput:
    """创建租户输入"""
    name: str
    description: Optional[str] = None


@dataclass
class CreateUserInput:
    """创建用户输入"""
    username: str
    email: str
    password: str
    role: str = "user"
    tenant_id: Optional[str] = None


@dataclass
class CreateProjectInput:
    """创建项目输入"""
    tenant_id: str
    name: str
    description: Optional[str] = None
    icon: str = "📁"
    color: str = "#4CAF50"


@dataclass
class CreateLLMConfigInput:
    """创建 LLM 配置输入"""
    tenant_id: str
    name: str
    provider: str
    api_key: str
    base_url: Optional[str] = None
    model: str = "deepseek-chat"
    max_tokens: int = 2000
    temperature: float = 0.7
    is_default: bool = False


@dataclass
class CreateDatabaseConnectionInput:
    """创建数据库连接输入"""
    tenant_id: str
    name: str
    db_type: str
    database_name: str
    project_id: Optional[str] = None  # 所属项目
    host: Optional[str] = None
    port: Optional[int] = None
    username: Optional[str] = None
    password: Optional[str] = None
    charset: str = "utf8mb4"
    is_default: bool = False


class SecretManager:
    """密钥管理器（简化版，实际使用 Fernet）"""

    @staticmethod
    def encrypt(plaintext: str) -> str:
        """简单加密（实际应使用 Fernet）"""
        # 这里是简化实现，实际应该使用 cryptography.fernet
        import base64
        import hashlib
        key = hashlib.sha256(b"microgenbi-secret-key").digest()
        # 简单 XOR 加密作为示例
        encrypted = "".join(chr(ord(c) ^ key[i % len(key)]) for i, c in enumerate(plaintext))
        return base64.b64encode(encrypted.encode()).decode()

    @staticmethod
    def decrypt(ciphertext: str) -> str:
        """简单解密"""
        import base64
        import hashlib
        key = hashlib.sha256(b"microgenbi-secret-key").digest()
        encrypted = base64.b64decode(ciphertext.encode()).decode()
        return "".join(chr(ord(c) ^ key[i % len(key)]) for i, c in enumerate(encrypted))


class TenantService:
    """租户服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, input: CreateTenantInput) -> Tenant:
        """创建租户"""
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name=input.name,
            description=input.description,
        )
        self.session.add(tenant)
        await self.session.commit()
        await self.session.refresh(tenant)
        return tenant

    async def get_by_id(self, tenant_id: str) -> Optional[Tenant]:
        """获取租户"""
        result = await self.session.execute(
            select(Tenant).where(Tenant.id == tenant_id)
        )
        return result.scalar_one_or_none()

    async def list_all(self) -> list[Tenant]:
        """列出所有租户"""
        result = await self.session.execute(select(Tenant))
        return list(result.scalars().all())


class ProjectService:
    """项目服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, input: CreateProjectInput) -> Project:
        """创建项目"""
        project = Project(
            id=str(uuid.uuid4()),
            tenant_id=input.tenant_id,
            name=input.name,
            description=input.description,
            icon=input.icon,
            color=input.color,
        )
        self.session.add(project)
        await self.session.commit()
        await self.session.refresh(project)
        return project

    async def get_by_id(self, project_id: str) -> Optional[Project]:
        """获取项目"""
        result = await self.session.execute(
            select(Project).where(Project.id == project_id)
        )
        return result.scalar_one_or_none()

    async def get_by_tenant(self, tenant_id: str) -> list[Project]:
        """获取租户的所有项目"""
        result = await self.session.execute(
            select(Project).where(
                and_(
                    Project.tenant_id == tenant_id,
                    Project.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def get_user_projects(self, user_id: str) -> list[Project]:
        """获取用户有权限访问的项目"""
        # 获取用户直接关联的项目
        result = await self.session.execute(
            select(Project)
            .join(ProjectMember, ProjectMember.project_id == Project.id)
            .where(
                and_(
                    ProjectMember.user_id == user_id,
                    ProjectMember.can_query == True,
                    Project.is_active == True
                )
            )
        )
        return list(result.scalars().all())


class UserService:
    """用户服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        input: CreateUserInput,
        tenant_id: str,
    ) -> User:
        """创建用户"""
        user = User(
            id=str(uuid.uuid4()),
            username=input.username,
            email=input.email,
            password_hash=self._hash_password(input.password),
            role=input.role,
            tenant_id=tenant_id,
        )
        self.session.add(user)

        # 自动添加为租户成员
        member = TenantMember(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user.id,
            role="member",
        )
        self.session.add(member)

        await self.session.commit()
        await self.session.refresh(user)
        return user

    async def get_by_username(self, username: str) -> Optional[User]:
        """按用户名获取用户"""
        result = await self.session.execute(
            select(User).where(User.username == username)
        )
        return result.scalar_one_or_none()

    async def verify_password(self, username: str, password: str) -> Optional[User]:
        """验证密码"""
        user = await self.get_by_username(username)
        if not user:
            return None

        if self._verify_password(password, user.password_hash):
            return user
        return None

    def _hash_password(self, password: str) -> str:
        """哈希密码（实际应使用 bcrypt）"""
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

    def _verify_password(self, password: str, hashed: str) -> bool:
        """验证密码"""
        import bcrypt
        return bcrypt.checkpw(password.encode(), hashed.encode())


class LLMConfigService:
    """LLM 配置服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, input: CreateLLMConfigInput) -> LLMConfig:
        """创建 LLM 配置"""
        config = LLMConfig(
            id=str(uuid.uuid4()),
            tenant_id=input.tenant_id,
            name=input.name,
            provider=input.provider,
            api_key_encrypted=SecretManager.encrypt(input.api_key),
            base_url=input.base_url,
            model=input.model,
            max_tokens=input.max_tokens,
            temperature=str(input.temperature),
            is_default=input.is_default,
        )
        self.session.add(config)

        # 如果是默认配置，取消其他默认
        if input.is_default:
            await self._clear_default(input.tenant_id)

        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def get_by_tenant(self, tenant_id: str) -> list[LLMConfig]:
        """获取租户的所有 LLM 配置"""
        result = await self.session.execute(
            select(LLMConfig)
            .where(
                and_(
                    LLMConfig.tenant_id == tenant_id,
                    LLMConfig.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def get_default(self, tenant_id: str) -> Optional[LLMConfig]:
        """获取默认 LLM 配置"""
        result = await self.session.execute(
            select(LLMConfig)
            .where(
                and_(
                    LLMConfig.tenant_id == tenant_id,
                    LLMConfig.is_default == True,
                    LLMConfig.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, config_id: str) -> Optional[LLMConfig]:
        """获取配置"""
        result = await self.session.execute(
            select(LLMConfig).where(LLMConfig.id == config_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        config_id: str,
        **updates,
    ) -> Optional[LLMConfig]:
        """更新配置"""
        config = await self.get_by_id(config_id)
        if not config:
            return None

        for key, value in updates.items():
            if hasattr(config, key):
                setattr(config, key, value)

        config.updated_at = datetime.utcnow()
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def _clear_default(self, tenant_id: str):
        """清除默认标记"""
        await self.session.execute(
            update(LLMConfig)
            .where(
                and_(
                    LLMConfig.tenant_id == tenant_id,
                    LLMConfig.is_default == True
                )
            )
            .values(is_default=False)
        )


class DatabaseConnectionService:
    """数据库连接服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(self, input: CreateDatabaseConnectionInput) -> DatabaseConnection:
        """创建数据库连接"""
        connection = DatabaseConnection(
            id=str(uuid.uuid4()),
            tenant_id=input.tenant_id,
            project_id=input.project_id,  # 所属项目
            name=input.name,
            db_type=input.db_type,
            host=input.host,
            port=input.port,
            database_name=input.database_name,
            username=input.username,
            password_encrypted=(
                SecretManager.encrypt(input.password)
                if input.password else None
            ),
            charset=input.charset,
            is_default=input.is_default,
        )
        self.session.add(connection)

        if input.is_default:
            await self._clear_default(input.tenant_id)

        await self.session.commit()
        await self.session.refresh(connection)
        return connection

    async def get_by_tenant(self, tenant_id: str) -> list[DatabaseConnection]:
        """获取租户的所有连接"""
        result = await self.session.execute(
            select(DatabaseConnection)
            .where(
                and_(
                    DatabaseConnection.tenant_id == tenant_id,
                    DatabaseConnection.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def get_by_project(self, project_id: str) -> list[DatabaseConnection]:
        """获取项目的所有连接"""
        result = await self.session.execute(
            select(DatabaseConnection)
            .where(
                and_(
                    DatabaseConnection.project_id == project_id,
                    DatabaseConnection.is_active == True
                )
            )
        )
        return list(result.scalars().all())

    async def get_default(self, tenant_id: str) -> Optional[DatabaseConnection]:
        """获取默认连接"""
        result = await self.session.execute(
            select(DatabaseConnection)
            .where(
                and_(
                    DatabaseConnection.tenant_id == tenant_id,
                    DatabaseConnection.is_default == True,
                    DatabaseConnection.is_active == True
                )
            )
        )
        return result.scalar_one_or_none()

    async def test_connection(self, connection_id: str) -> dict:
        """测试连接（使用 MultiDBConnectionFactory 进行真实连接测试）"""
        connection = await self.get_by_id(connection_id)
        if not connection:
            return {"success": False, "error": "连接不存在"}

        try:
            from micro_genbi.db.connection_factory import get_multi_db_factory

            factory = get_multi_db_factory()
            result = await factory.test_connection(connection_id)
            return result
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def get_by_id(self, connection_id: str) -> Optional[DatabaseConnection]:
        """获取连接"""
        result = await self.session.execute(
            select(DatabaseConnection)
            .where(DatabaseConnection.id == connection_id)
        )
        return result.scalar_one_or_none()


class APIKeyService:
    """API Key 服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        tenant_id: str,
        user_id: str,
        name: str,
        scope: str = "readonly",
        expires_in_days: Optional[int] = None,
    ) -> tuple[APIKey, str]:
        """
        创建 API Key

        Returns:
            (APIKey, raw_key): 返回创建的对象和明文 Key（仅此时可查看）
        """
        # 生成 Key
        raw_key = f"mgbi_sk_{secrets.token_urlsafe(32)}"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        key_prefix = raw_key[:10]

        from datetime import timedelta
        expires_at = None
        if expires_in_days:
            expires_at = datetime.utcnow() + timedelta(days=expires_in_days)

        api_key = APIKey(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            name=name,
            key_hash=key_hash,
            key_prefix=key_prefix,
            scope=scope,
            expires_at=expires_at,
        )
        self.session.add(api_key)
        await self.session.commit()
        await self.session.refresh(api_key)

        return api_key, raw_key

    async def verify(self, raw_key: str) -> Optional[APIKey]:
        """验证 API Key"""
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
        result = await self.session.execute(
            select(APIKey).where(
                and_(
                    APIKey.key_hash == key_hash,
                    APIKey.is_active == True,
                    or_(
                        APIKey.expires_at.is_(None),
                        APIKey.expires_at > datetime.utcnow()
                    )
                )
            )
        )
        api_key = result.scalar_one_or_none()

        if api_key:
            # 更新最后使用时间
            api_key.last_used_at = datetime.utcnow()

        return api_key

    async def revoke(self, api_key_id: str) -> bool:
        """撤销 API Key"""
        result = await self.session.execute(
            update(APIKey)
            .where(APIKey.id == api_key_id)
            .values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount > 0


class AuditService:
    """审计服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def log(
        self,
        event_type: str,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        ip_address: Optional[str] = None,
        resource: Optional[str] = None,
        action: Optional[str] = None,
        result: str = "success",
        error_message: Optional[str] = None,
        metadata: Optional[dict] = None,
    ):
        """记录审计日志"""
        log = AuditLog(
            id=str(uuid.uuid4()),
            tenant_id=tenant_id,
            user_id=user_id,
            ip_address=ip_address,
            event_type=event_type,
            resource=resource,
            action=action,
            result=result,
            error_message=error_message,
            metadata=metadata,
        )
        self.session.add(log)
        await self.session.commit()


class QueryHistoryService:
    """查询历史服务"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def create(
        self,
        user_id: str,
        tenant_id: str,
        natural_query: str,
        generated_sql: Optional[str] = None,
        tables_used: Optional[list] = None,
        row_count: Optional[int] = None,
        execution_time_ms: Optional[int] = None,
        status: str = QueryStatus.SUCCESS.value,
        error_message: Optional[str] = None,
        llm_config_id: Optional[str] = None,
        connection_id: Optional[str] = None,
        session_id: Optional[str] = None,
    ) -> QueryHistory:
        """创建查询历史"""
        history = QueryHistory(
            id=str(uuid.uuid4()),
            user_id=user_id,
            tenant_id=tenant_id,
            natural_query=natural_query,
            generated_sql=generated_sql,
            tables_used=tables_used,
            row_count=row_count,
            execution_time_ms=execution_time_ms,
            status=status,
            error_message=error_message,
            llm_config_id=llm_config_id,
            connection_id=connection_id,
            session_id=session_id,
        )
        self.session.add(history)
        await self.session.commit()
        await self.session.refresh(history)
        return history

    async def get_by_user(
        self,
        user_id: str,
        limit: int = 20,
        offset: int = 0,
    ) -> list[QueryHistory]:
        """获取用户的查询历史"""
        result = await self.session.execute(
            select(QueryHistory)
            .where(QueryHistory.user_id == user_id)
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all())

    async def list_all(
        self,
        tenant_id: str,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[QueryHistory], int]:
        """获取租户的所有查询历史"""
        # 总数
        count_result = await self.session.execute(
            select(QueryHistory.id)
            .where(QueryHistory.tenant_id == tenant_id)
        )
        total = len(count_result.scalars().all())

        # 分页数据
        result = await self.session.execute(
            select(QueryHistory)
            .where(QueryHistory.tenant_id == tenant_id)
            .order_by(QueryHistory.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def delete(self, history_id: str) -> bool:
        """删除历史记录"""
        result = await self.session.execute(
            delete(QueryHistory).where(QueryHistory.id == history_id)
        )
        await self.session.commit()
        return result.rowcount > 0


class AuditLogService:
    """审计日志服务（查询端）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_logs(
        self,
        tenant_id: Optional[str] = None,
        user_id: Optional[str] = None,
        event_type: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[AuditLog], int]:
        """查询审计日志"""
        conditions = []
        if tenant_id:
            conditions.append(AuditLog.tenant_id == tenant_id)
        if user_id:
            conditions.append(AuditLog.user_id == user_id)
        if event_type:
            conditions.append(AuditLog.event_type == event_type)

        where_clause = and_(*conditions) if conditions else True

        # 总数
        count_result = await self.session.execute(
            select(AuditLog.id).where(where_clause)
        )
        total = len(count_result.scalars().all())

        result = await self.session.execute(
            select(AuditLog)
            .where(where_clause)
            .order_by(AuditLog.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def get_stats(self, tenant_id: Optional[str] = None) -> dict:
        """获取审计统计"""
        from datetime import datetime, timedelta

        now = datetime.utcnow()
        day_ago = now - timedelta(days=1)

        base = select(AuditLog).where(AuditLog.tenant_id == tenant_id) if tenant_id else select(AuditLog)

        total_result = await self.session.execute(base)
        total_logs = len(total_result.scalars().all())

        # 失败/阻断/成功
        failed_result = await self.session.execute(
            select(AuditLog).where(and_(base.whereclause, AuditLog.result == "failed"))
        )
        blocked_result = await self.session.execute(
            select(AuditLog).where(and_(base.whereclause, AuditLog.result == "blocked"))
        )
        login_result = await self.session.execute(
            select(AuditLog).where(
                and_(base.whereclause, AuditLog.event_type.like("%login%"))
            )
        )
        last24_result = await self.session.execute(
            select(AuditLog).where(
                and_(base.whereclause, AuditLog.created_at >= day_ago)
            )
        )

        # 按类型统计
        type_result = await self.session.execute(
            select(AuditLog.event_type, func.count(AuditLog.id))
            .where(base.whereclause if base.whereclause is not None else True)
            .group_by(AuditLog.event_type)
            .limit(10)
        )

        return {
            "totalEvents": total_logs,
            "failedLogins": len(failed_result.scalars().all()),
            "blockedQueries": len(blocked_result.scalars().all()),
            "sqlInjections": 0,
            "last24h": {
                "logins": len(login_result.scalars().all()),
                "queries": len(last24_result.scalars().all()),
                "failures": len([
                    l for l in last24_result.scalars().all() if l.result == "failed"
                ]),
            },
        }


class UserManagementService:
    """用户管理服务（用于 admin 后台）"""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def list_users(
        self,
        tenant_id: Optional[str] = None,
        role: Optional[str] = None,
        status: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[User], int]:
        """列出用户"""
        conditions = []
        if tenant_id:
            conditions.append(User.tenant_id == tenant_id)
        if role:
            conditions.append(User.role == role)
        if status == "active":
            conditions.append(User.is_active == True)
        elif status == "suspended":
            conditions.append(User.is_active == False)

        where_clause = and_(*conditions) if conditions else True

        # 总数
        count_result = await self.session.execute(select(User.id).where(where_clause))
        total = len(count_result.scalars().all())

        result = await self.session.execute(
            select(User)
            .where(where_clause)
            .order_by(User.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(result.scalars().all()), total

    async def update_user(self, user_id: str, **updates) -> Optional[User]:
        """更新用户"""
        result = await self.session.execute(
            update(User).where(User.id == user_id).values(**updates)
        )
        await self.session.commit()
        if result.rowcount == 0:
            return None
        user_result = await self.session.execute(select(User).where(User.id == user_id))
        return user_result.scalar_one_or_none()

    async def delete_user(self, user_id: str) -> bool:
        """删除用户（软删除）"""
        result = await self.session.execute(
            update(User).where(User.id == user_id).values(is_active=False)
        )
        await self.session.commit()
        return result.rowcount > 0

    async def reset_password(self, user_id: str) -> str:
        """重置用户密码（生成随机密码）"""
        import secrets
        new_password = secrets.token_urlsafe(12)  # 生成 16 字符随机密码
        password_hash = self._hash_password(new_password)
        result = await self.session.execute(
            update(User).where(User.id == user_id).values(password_hash=password_hash)
        )
        await self.session.commit()
        if result.rowcount == 0:
            return None
        return new_password
