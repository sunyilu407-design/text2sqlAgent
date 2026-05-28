"""ServiceFactory - 统一服务创建入口

提供 AskService 和 MultiDBAskService 的统一创建接口，支持：
1. 自动模式检测（单库/多库）
2. 依赖注入（支持测试 Mock）
3. 配置化创建
4. 资源管理（统一生命周期）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Optional, Any

from micro_genbi import get_logger

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from micro_genbi.llm.base import LLMClient
    from micro_genbi.semantic.schema_registry import SchemaRegistry
    from micro_genbi.db.engine import DatabaseExecutor
    from micro_genbi.service.ask_service import AskService
    from micro_genbi.service.multi_ask_service import MultiDBAskService

logger = get_logger(__name__)


class ServiceMode(str, Enum):
    """服务模式"""
    AUTO = "auto"      # 自动检测
    SINGLE = "single"  # 单库模式
    MULTI = "multi"   # 多库模式


@dataclass
class ServiceConfig:
    """服务配置"""
    mode: ServiceMode = ServiceMode.AUTO
    default_connection_id: Optional[str] = None
    max_retries: int = 3
    enable_security: bool = True
    enable_masking: bool = True
    schema_path: Optional[str] = None


@dataclass
class ServiceDependencies:
    """服务依赖（用于测试注入）"""
    llm_client: Optional[Any] = None
    schema_registry: Optional[Any] = None
    executor: Optional[Any] = None
    session: Optional[Any] = None


class ServiceFactory:
    """
    统一服务工厂

    用法示例：

    ```python
    # 基础用法（自动检测模式）
    factory = ServiceFactory()
    service = await factory.create()

    # 单库模式
    service = await factory.create(mode=ServiceMode.SINGLE)

    # 多库模式（需要 session）
    from sqlalchemy.ext.asyncio import AsyncSession
    service = await factory.create(
        mode=ServiceMode.MULTI,
        session=db_session,
    )

    # 使用 Mock 依赖（测试场景）
    service = await factory.create(
        mock_llm=mock_llm_client,
        mock_executor=mock_executor,
    )

    # 执行查询
    result = await service.ask("各部门上月的报销总额是多少？")

    # 关闭服务
    await factory.close()
    ```
    """

    def __init__(self, config: Optional[ServiceConfig] = None):
        self.config = config or ServiceConfig()
        self._llm_client: Optional[Any] = None
        self._schema_registry: Optional[Any] = None
        self._executor: Optional[Any] = None
        self._session: Optional[Any] = None
        self._service: Optional[Any] = None
        self._initialized: bool = False

    async def create(
        self,
        mode: Optional[ServiceMode] = None,
        session: Optional[Any] = None,
        mock_llm: Optional[Any] = None,
        mock_schema_registry: Optional[Any] = None,
        mock_executor: Optional[Any] = None,
        default_connection_id: Optional[str] = None,
        **kwargs,
    ) -> Any:
        """
        创建查询服务

        Args:
            mode: 服务模式（None=自动检测）
            session: FastAPI AsyncSession（多库模式必需）
            mock_llm: Mock LLM 客户端（测试用）
            mock_schema_registry: Mock SchemaRegistry（测试用）
            mock_executor: Mock 执行器（测试用）
            default_connection_id: 默认数据源 ID
            **kwargs: 传递给服务的其他参数

        Returns:
            AskService 或 MultiDBAskService 实例
        """
        # 确定模式
        effective_mode = mode or self.config.mode

        # 导入类（延迟加载避免循环导入）
        if effective_mode == ServiceMode.SINGLE:
            return await self._create_single_service(
                session=session,
                mock_llm=mock_llm,
                mock_schema_registry=mock_schema_registry,
                mock_executor=mock_executor,
                default_connection_id=default_connection_id,
                **kwargs,
            )
        elif effective_mode == ServiceMode.MULTI:
            if session is None:
                raise ValueError(
                    "MultiDBAskService 需要传入 session 参数，请从 FastAPI 注入"
                )
            return await self._create_multi_service(
                session=session,
                mock_llm=mock_llm,
                mock_schema_registry=mock_schema_registry,
                default_connection_id=default_connection_id,
                **kwargs,
            )
        else:
            # AUTO 模式：根据 session 是否传入决定
            if session is not None:
                return await self._create_multi_service(
                    session=session,
                    mock_llm=mock_llm,
                    mock_schema_registry=mock_schema_registry,
                    default_connection_id=default_connection_id,
                    **kwargs,
                )
            else:
                return await self._create_single_service(
                    session=session,
                    mock_llm=mock_llm,
                    mock_schema_registry=mock_schema_registry,
                    mock_executor=mock_executor,
                    default_connection_id=default_connection_id,
                    **kwargs,
                )

    async def _create_single_service(
        self,
        session: Optional[Any],
        mock_llm: Optional[Any],
        mock_schema_registry: Optional[Any],
        mock_executor: Optional[Any],
        default_connection_id: Optional[str],
        **kwargs,
    ) -> Any:
        """创建单库服务"""
        from micro_genbi.service.ask_service import AskService
        from micro_genbi.llm.base import create_llm_client

        logger.info("创建 AskService（单库模式）")

        # 使用 Mock 或创建真实依赖
        llm_client = mock_llm or self._llm_client
        if llm_client is None:
            llm_client = create_llm_client()

        schema_registry = mock_schema_registry or self._schema_registry
        if schema_registry is None:
            from micro_genbi.semantic.schema_registry import SchemaRegistry
            schema_registry = SchemaRegistry(
                schema_path=self.config.schema_path
            )
            schema_registry.load()

        executor = mock_executor or self._executor

        service = AskService(
            llm_client=llm_client,
            schema_registry=schema_registry,
            executor=executor,
            schema_path=self.config.schema_path,
            max_retries=self.config.max_retries,
            enable_security=self.config.enable_security,
            enable_masking=self.config.enable_masking,
        )

        self._service = service
        self._llm_client = llm_client
        self._schema_registry = schema_registry
        self._executor = executor
        self._initialized = True

        return service

    async def _create_multi_service(
        self,
        session: Any,
        mock_llm: Optional[Any],
        mock_schema_registry: Optional[Any],
        default_connection_id: Optional[str],
        **kwargs,
    ) -> Any:
        """创建多库服务"""
        from micro_genbi.service.multi_ask_service import MultiDBAskService
        from micro_genbi.llm.base import create_llm_client

        logger.info("创建 MultiDBAskService（多库模式）")

        # 使用 Mock 或创建真实依赖
        llm_client = mock_llm or self._llm_client
        if llm_client is None:
            llm_client = create_llm_client()

        schema_registry = mock_schema_registry or self._schema_registry
        if schema_registry is None:
            from micro_genbi.semantic.schema_registry import SchemaRegistry
            schema_registry = SchemaRegistry()
            schema_registry.load()

        conn_id = default_connection_id or self.config.default_connection_id

        service = MultiDBAskService(
            session=session,
            llm_client=llm_client,
            schema_registry=schema_registry,
            default_connection_id=conn_id,
            max_retries=self.config.max_retries,
            enable_security=self.config.enable_security,
            enable_masking=self.config.enable_masking,
        )

        self._service = service
        self._llm_client = llm_client
        self._schema_registry = schema_registry
        self._session = session
        self._initialized = True

        return service

    async def close(self) -> None:
        """关闭服务并释放资源"""
        if self._service is not None:
            await self._service.close()
            self._service = None
        self._initialized = False
        logger.info("ServiceFactory 资源已释放")

    @property
    def service_mode(self) -> str:
        """获取当前服务模式"""
        if self._service is None:
            return "not_initialized"
        from micro_genbi.service.ask_service import AskService
        if isinstance(self._service, AskService):
            return "single"
        return "multi"

    @property
    def is_initialized(self) -> bool:
        """是否已初始化"""
        return self._initialized


# =============================================================================
# 全局工厂实例（用于 FastAPI 依赖注入）
# =============================================================================

_factory_instance: Optional[ServiceFactory] = None


def get_service_factory() -> ServiceFactory:
    """获取全局工厂实例"""
    global _factory_instance
    if _factory_instance is None:
        _factory_instance = ServiceFactory()
    return _factory_instance


def reset_service_factory() -> None:
    """重置全局工厂实例"""
    global _factory_instance
    _factory_instance = None


# =============================================================================
# 便捷函数
# =============================================================================

async def create_ask_service(
    session: Optional[Any] = None,
    mode: ServiceMode = ServiceMode.AUTO,
    **kwargs,
) -> Any:
    """
    便捷函数：创建查询服务

    Args:
        session: FastAPI AsyncSession（多库模式必需）
        mode: 服务模式
        **kwargs: 其他参数

    Returns:
        AskService 或 MultiDBAskService 实例
    """
    factory = ServiceFactory()
    service = await factory.create(mode=mode, session=session, **kwargs)
    # 注意：调用方负责调用 await factory.close()
    return service


__all__ = [
    "ServiceFactory",
    "ServiceMode",
    "ServiceConfig",
    "ServiceDependencies",
    "create_ask_service",
    "get_service_factory",
    "reset_service_factory",
]
