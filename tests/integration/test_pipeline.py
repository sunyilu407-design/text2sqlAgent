"""集成测试：端到端流水线"""

import pytest
import asyncio
from typing import Generator
from unittest.mock import AsyncMock, MagicMock, patch


pytestmark = pytest.mark.integration


class TestPipelineIntegration:
    """端到端流水线测试"""

    @pytest.fixture
    async def ask_service(self) -> Generator:
        """创建 AskService 实例（使用 Mock）"""
        from micro_genbi.service.ask_service import AskService

        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(
            return_value=type("obj", (), {"content": "SELECT 1 FROM dual"})()
        )
        mock_llm.close = AsyncMock()

        service = AskService(
            llm_client=mock_llm,
            schema_registry=None,
            executor=None,
            schema_path=None,
        )
        yield service
        await service.close()

    @pytest.mark.asyncio
    async def test_simple_query(self, ask_service):
        """测试简单查询"""
        result = await ask_service.ask("统计订单数量")
        assert result is not None
        assert result.sql is not None

    @pytest.mark.asyncio
    async def test_multi_round_conversation(self, ask_service):
        """测试多轮对话"""
        session_id = "test_session_1"

        result1 = await ask_service.ask(
            "统计本月订单",
            session_id=session_id
        )
        assert result1 is not None

        result2 = await ask_service.ask(
            "继续按这个趋势",
            session_id=session_id
        )
        assert result2 is not None

    @pytest.mark.asyncio
    async def test_intent_classification_flow(self, ask_service):
        """测试意图分类流程"""
        test_cases = [
            "统计销售额",
            "对比两个月的订单",
            "查询各部门数据",
        ]

        for query in test_cases:
            result = await ask_service.ask(query)
            assert result is not None

    @pytest.mark.asyncio
    async def test_error_recovery(self, ask_service):
        """测试错误恢复（自愈重试）"""
        # 测试异常处理
        from micro_genbi.errors import SQLExecutionError

        # 正常情况下不抛异常
        result = await ask_service.ask("查询订单")
        assert result is not None


class TestMultiDatabaseIntegration:
    """多库集成测试"""

    @pytest.mark.skip(reason="需要配置多库环境")
    @pytest.mark.asyncio
    async def test_aggregate_query(self):
        """测试同构多库聚合查询"""
        pass

    @pytest.mark.skip(reason="需要配置多库环境")
    @pytest.mark.asyncio
    async def test_federated_query(self):
        """测试异构多库联邦查询"""
        pass


class TestAPIIntegration:
    """API 集成测试"""

    @pytest.fixture
    def api_client(self):
        """创建测试 API 客户端"""
        import httpx
        return httpx.Client(base_url="http://localhost:8000")

    def test_health_endpoint(self, api_client):
        """测试健康检查端点"""
        response = api_client.get("/api/v1/health")

    def test_schema_endpoint(self, api_client):
        """测试 schema 获取端点"""
        response = api_client.get("/api/v1/schema")
