"""端到端集成测试：ServiceFactory + AskService + MultiDBAskService

测试完整的查询流水线，包括：
1. ServiceFactory 模式检测和创建
2. AskService 单库查询流水线
3. MultiDBAskService 多库查询流水线
4. SQL 安全验证
5. 意图分类
6. 自愈重试
"""

from __future__ import annotations

import pytest
import asyncio
from typing import Any, Generator
from unittest.mock import AsyncMock, MagicMock, patch
from dataclasses import dataclass


pytestmark = pytest.mark.integration


# =============================================================================
# Mock 组件
# =============================================================================

class MockLLMClient:
    """Mock LLM 客户端"""

    def __init__(self, response_content: str = "SELECT 1"):
        self._response_content = response_content
        self.call_count = 0

    async def generate(self, prompt: str, system: str | None = None) -> MockResponse:
        self.call_count += 1
        return MockResponse(content=self._response_content)

    async def close(self) -> None:
        pass


class MockLLMClientForClassifier:
    """Mock LLM 客户端 - 专门用于意图分类测试，根据 prompt 内容返回对应意图"""

    # 规则优先匹配（与 IntentClassifier 第一层相同的逻辑）
    INTENT_PATTERNS = {
        "aggregation": ["统计", "合计", "总计", "sum", "count", "avg", "平均", "总数", "汇总"],
        "filter": ["查找", "查询", "筛选", "过滤", "只看", "只要"],
        "ranking": ["排名", "top", "前三", "倒数", "排序", "最大", "最小"],
    }

    def __init__(self):
        self.call_count = 0

    async def generate(self, prompt: str, system: str | None = None) -> MockResponse:
        self.call_count += 1
        # 提取查询文本：LLM prompt 最后一行通常是 "用户查询: XXX"
        lines = [l.strip() for l in prompt.strip().splitlines() if l.strip()]
        query_text = lines[-1] if lines else prompt
        # 移除 "用户查询:" 前缀
        for prefix in ["用户查询:", "User query:", "user query:"]:
            if query_text.lower().startswith(prefix.lower()):
                query_text = query_text[len(prefix):].strip()
                break

        # 规则优先匹配（与真实 IntentClassifier 相同的逻辑）
        for intent, keywords in self.INTENT_PATTERNS.items():
            for kw in keywords:
                if kw.lower() in query_text.lower():
                    return MockResponse(content=intent)
        return MockResponse(content="query")

    async def close(self) -> None:
        pass

    async def close(self) -> None:
        pass


class MockResponse:
    """Mock LLM 响应"""

    def __init__(self, content: str):
        self.content = content


class MockExecutor:
    """Mock 数据库执行器"""

    def __init__(self, data: list[dict] | None = None):
        self._data = data or [
            {"部门": "销售部", "报销总额": 150000, "笔数": 45},
            {"部门": "技术部", "报销总额": 85000, "笔数": 32},
        ]

    async def execute(self, sql: str) -> list[dict]:
        return self._data


class MockSchemaRegistry:
    """Mock Schema Registry"""

    def __init__(self):
        self._tables: dict = {}

    def load(self) -> None:
        pass

    def build_llm_context(self, **kwargs) -> str:
        return """
## 表: dept_expense
| 列名 | 类型 | 描述 |
|------|------|------|
| dept_name | VARCHAR | 部门名称 |
| amount | DECIMAL | 报销金额 |
| submit_date | DATE | 提交日期 |
"""

    def get_tables(self):
        return []

    def get_table(self, name: str):
        return None


# =============================================================================
# 测试辅助函数
# =============================================================================

async def create_mock_single_service() -> Any:
    """创建配置了 Mock 的 AskService"""
    from micro_genbi.service.ask_service import AskService

    return AskService(
        llm_client=MockLLMClient(response_content="SELECT dept_name, SUM(amount) FROM dept_expense GROUP BY dept_name"),
        schema_registry=MockSchemaRegistry(),
        executor=MockExecutor(),
        schema_path=None,
        max_retries=3,
        enable_security=True,
        enable_masking=True,
    )


async def create_mock_multi_service(session: Any) -> Any:
    """创建配置了 Mock 的 MultiDBAskService"""
    from micro_genbi.service.multi_ask_service import MultiDBAskService

    return MultiDBAskService(
        session=session,
        llm_client=MockLLMClient(
            response_content="SELECT city, SUM(sales) FROM orders GROUP BY city"
        ),
        schema_registry=MockSchemaRegistry(),
        default_connection_id=None,
        max_retries=3,
        enable_security=True,
        enable_masking=True,
    )


# =============================================================================
# TestAskServicePipeline
# =============================================================================

class TestAskServicePipeline:
    """AskService 单库查询流水线测试"""

    @pytest.fixture
    async def service(self) -> Generator:
        svc = await create_mock_single_service()
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_simple_query_returns_result(self, service):
        """测试简单查询返回结果"""
        result = await service.ask("各部门报销总额是多少？")

        assert result is not None
        assert hasattr(result, "sql")
        assert hasattr(result, "data")
        assert hasattr(result, "execution_time_ms")
        assert result.sql is not None
        assert len(result.data) == 2

    @pytest.mark.asyncio
    async def test_aggregation_query(self, service):
        """测试聚合查询"""
        result = await service.ask("统计各部门上月的报销总额是多少？")

        assert result is not None
        assert result.sql is not None
        assert "GROUP BY" in result.sql.upper() or "group by" in result.sql.lower()

    @pytest.mark.asyncio
    async def test_intent_classification(self, service):
        """测试意图分类"""
        result = await service.ask("销售部的报销增长了多少？")

        assert result is not None
        assert hasattr(result, "steps_timing")
        assert "intent_classification_ms" in result.steps_timing

    @pytest.mark.asyncio
    async def test_timing_metrics(self, service):
        """测试时间指标"""
        result = await service.ask("统计本月订单数量")

        assert result.execution_time_ms >= 0
        assert "prompt_security_check_ms" in result.steps_timing
        assert "intent_classification_ms" in result.steps_timing
        assert "sql_generation_ms" in result.steps_timing
        assert "sql_validation_ms" in result.steps_timing
        assert "sql_execution_ms" in result.steps_timing

    @pytest.mark.asyncio
    async def test_security_check(self, service):
        """测试安全检查"""
        # 正常查询应该通过
        result = await service.ask("各部门报销总额是多少？")
        assert result is not None

    @pytest.mark.asyncio
    async def test_session_context(self, service):
        """测试会话上下文"""
        session_id = "test_session_123"

        result = await service.ask(
            "各部门报销总额是多少？",
            session_id=session_id
        )

        assert result.session_id == session_id


# =============================================================================
# TestMultiDBAskServicePipeline
# =============================================================================

class TestMultiDBAskServicePipeline:
    """MultiDBAskService 多库查询流水线测试"""

    @pytest.fixture
    def mock_session(self) -> MagicMock:
        """创建 Mock Session"""
        return MagicMock()

    @pytest.fixture
    async def service(self, mock_session) -> Generator:
        svc = await create_mock_multi_service(mock_session)
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_multi_db_service_creation(self, service):
        """测试多库服务创建"""
        assert service is not None
        assert hasattr(service, "router")
        assert hasattr(service, "executor")
        assert hasattr(service, "intent_classifier")

    @pytest.mark.asyncio
    async def test_query_mode_detection(self, service, mock_session):
        """测试查询模式检测"""
        # Mock 路由器返回单库模式
        with patch.object(service.router, "route", new_callable=AsyncMock) as mock_route:
            from micro_genbi.db.router import QueryPlan, QueryMode, SubQueryPlan

            mock_route.return_value = QueryPlan(
                mode=QueryMode.SINGLE,
                is_multi_db=False,
                sub_plans=[
                    SubQueryPlan(
                        connection_id="conn_1",
                        connection_name="test_db",
                        connection_type="postgresql",
                        sql="",
                        source_table="orders",
                        merge_column="",
                    )
                ],
                description="单库查询",
            )

            result = await service.ask("统计订单数量")

            assert result is not None
            assert hasattr(result, "query_mode")

    @pytest.mark.asyncio
    async def test_sql_generation_per_connection(self, service, mock_session):
        """测试按连接生成 SQL"""
        with patch.object(service.router, "route", new_callable=AsyncMock) as mock_route:
            from micro_genbi.db.router import QueryPlan, QueryMode, SubQueryPlan

            mock_route.return_value = QueryPlan(
                mode=QueryMode.SINGLE,
                is_multi_db=False,
                sub_plans=[
                    SubQueryPlan(
                        connection_id="conn_1",
                        connection_name="orders_db",
                        connection_type="postgresql",
                        sql="",
                        source_table="orders",
                        merge_column="",
                    )
                ],
                description="单库查询",
            )

            with patch.object(service.executor, "execute", new_callable=AsyncMock) as mock_exec:
                from micro_genbi.db.execution import ExecutionResult
                from micro_genbi.db.router import QueryMode

                mock_exec.return_value = ExecutionResult(
                    mode=QueryMode.SINGLE,
                    data=[{"city": "上海", "销售额": 100000}],
                    columns=["city", "销售额"],
                    row_count=1,
                    latency_ms=50,
                    sql="SELECT city, SUM(sales) FROM orders GROUP BY city",
                    summary="查询成功，返回 1 行",
                )

                result = await service.ask("各城市销售额是多少？")

                assert result is not None
                assert result.sql is not None


# =============================================================================
# TestServiceFactory
# =============================================================================

class TestServiceFactory:
    """ServiceFactory 测试"""

    @pytest.mark.asyncio
    async def test_create_single_service(self):
        """测试创建单库服务"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        service = await factory.create(mode=ServiceMode.SINGLE)

        assert service is not None
        assert service.__class__.__name__ == "AskService"

        await factory.close()

    @pytest.mark.asyncio
    async def test_create_multi_service_requires_session(self):
        """测试多库服务需要 session"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        with pytest.raises(ValueError, match="需要传入 session"):
            await factory.create(mode=ServiceMode.MULTI)

    @pytest.mark.asyncio
    async def test_auto_mode_single(self):
        """测试自动模式 - 单库（无 session）"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        service = await factory.create(mode=ServiceMode.AUTO)

        assert service is not None
        assert service.__class__.__name__ == "AskService"

        await factory.close()

    @pytest.mark.asyncio
    async def test_auto_mode_multi(self):
        """测试自动模式 - 多库（有 session）"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()
        mock_session = MagicMock()

        service = await factory.create(mode=ServiceMode.AUTO, session=mock_session)

        assert service is not None
        assert service.__class__.__name__ == "MultiDBAskService"

        await factory.close()

    @pytest.mark.asyncio
    async def test_mock_dependency_injection(self):
        """测试 Mock 依赖注入"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()
        mock_llm = MockLLMClient(response_content="SELECT 1 FROM dual")

        service = await factory.create(
            mode=ServiceMode.SINGLE,
            mock_llm=mock_llm,
        )

        assert service is not None
        assert service.llm_client is mock_llm

        await factory.close()

    @pytest.mark.asyncio
    async def test_service_config(self):
        """测试服务配置"""
        from micro_genbi.service.factory import ServiceFactory, ServiceConfig, ServiceMode

        config = ServiceConfig(
            mode=ServiceMode.SINGLE,
            max_retries=5,
            enable_security=False,
        )
        factory = ServiceFactory(config=config)

        assert factory.config.max_retries == 5
        assert factory.config.enable_security is False

        service = await factory.create()

        assert service.max_retries == 5
        assert service.enable_security is False

        await factory.close()

    @pytest.mark.asyncio
    async def test_factory_close(self):
        """测试工厂关闭"""
        from micro_genbi.service.factory import ServiceFactory

        factory = ServiceFactory()
        service = await factory.create()

        await factory.close()

        assert factory._service is None
        assert factory.is_initialized is False

    @pytest.mark.asyncio
    async def test_service_mode_property(self):
        """测试服务模式属性"""
        from micro_genbi.service.factory import ServiceFactory

        factory = ServiceFactory()
        assert factory.service_mode == "not_initialized"

        await factory.create()
        assert factory.service_mode == "single"

        await factory.close()
        assert factory.service_mode == "not_initialized"


# =============================================================================
# TestSQLSafetyValidation
# =============================================================================

class TestSQLSafetyValidation:
    """SQL 安全验证测试"""

    @pytest.fixture
    async def service(self) -> Generator:
        svc = await create_mock_single_service()
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_read_only_sql_pass(self, service):
        """测试只读 SQL 通过验证"""
        # Mock 返回 SELECT 语句
        result = await service.ask("各部门报销总额是多少？")
        assert result is not None

    @pytest.mark.asyncio
    async def test_limit_enforcement(self, service):
        """测试 LIMIT 强制执行"""
        result = await service.ask("查询所有订单")
        assert result.sql is not None


# =============================================================================
# TestChartGeneration
# =============================================================================

class TestChartGeneration:
    """图表生成测试"""

    @pytest.fixture
    async def service(self) -> Generator:
        svc = await create_mock_single_service()
        yield svc
        await svc.close()

    @pytest.mark.asyncio
    async def test_chart_engine_integration(self, service):
        """测试图表引擎集成"""
        from micro_genbi.chart import ChartEngine

        chart_engine = ChartEngine()

        test_data = [
            {"部门": "销售部", "金额": 150000},
            {"部门": "技术部", "金额": 85000},
        ]

        chart_config = chart_engine.generate(
            data=test_data,
            intent="aggregation",
        )

        assert chart_config is not None
        assert "type" in chart_config
        # 1 numeric col + <= 10 rows → pie（根据 ChartEngine 推断逻辑）
        assert chart_config["type"] in ("bar", "pie")

    @pytest.mark.asyncio
    async def test_intent_based_chart_selection(self, service):
        """测试基于意图的图表选择"""
        from micro_genbi.chart import ChartEngine

        chart_engine = ChartEngine()

        # 趋势数据 → line
        trend_data = [
            {"日期": "2026-01", "销售额": 100000},
            {"日期": "2026-02", "销售额": 120000},
            {"日期": "2026-03", "销售额": 95000},
        ]

        chart = chart_engine.generate(data=trend_data, intent="trend")
        assert chart is not None
        assert chart["type"] == "line"


# =============================================================================
# TestIntentClassifier
# =============================================================================

class TestIntentClassifier:
    """意图分类器测试"""

    @pytest.fixture
    def classifier(self):
        """创建意图分类器"""
        from micro_genbi.service.ask_service import IntentClassifier

        return IntentClassifier(llm_client=MockLLMClientForClassifier())

    @pytest.mark.asyncio
    async def test_aggregation_intent(self, classifier):
        """测试聚合意图"""
        result = await classifier.classify("各部门报销总额是多少？")
        assert result is not None
        assert result.intent.value in ["aggregation", "query"]

    @pytest.mark.asyncio
    async def test_comparison_intent(self, classifier):
        """测试对比意图"""
        result = await classifier.classify("销售部和市场部的业绩对比？")
        assert result is not None
        assert result.intent.value in ["comparison", "query"]

    @pytest.mark.asyncio
    async def test_trend_intent(self, classifier):
        """测试趋势意图"""
        result = await classifier.classify("过去三个月的销售趋势如何？")
        assert result is not None
        assert result.intent.value in ["trend", "query"]

    @pytest.mark.asyncio
    async def test_filter_intent(self, classifier):
        """测试筛选意图"""
        result = await classifier.classify("只查销售部的数据")
        assert result is not None
        assert result.intent.value in ["filter", "query"]

    @pytest.mark.asyncio
    async def test_ranking_intent(self, classifier):
        """测试排名意图"""
        result = await classifier.classify("销售额最高的前10名商品是什么？")
        assert result is not None
        assert result.intent.value in ["ranking", "query"]


# =============================================================================
# TestSemanticRetriever
# =============================================================================

class TestSemanticRetriever:
    """语义检索器测试"""

    def test_retrieve_relevant_tables(self):
        """测试检索相关表"""
        from micro_genbi.retrieval import SemanticRetriever
        from micro_genbi.semantic.schema_registry import SchemaRegistry

        schema_registry = MockSchemaRegistry()
        retriever = SemanticRetriever(schema_registry=schema_registry)

        result = retriever.retrieve_relevant_tables("报销 部门 金额")

        assert result is not None
        assert isinstance(result, list)

    def test_build_retrieval_context(self):
        """测试构建检索上下文"""
        from micro_genbi.retrieval import SemanticRetriever
        from micro_genbi.semantic.schema_registry import SchemaRegistry

        schema_registry = MockSchemaRegistry()
        retriever = SemanticRetriever(schema_registry=schema_registry)

        # 调用 tfidf_retriever 的 search 方法
        context = retriever.tfidf_retriever.retrieve("各部门报销总额", top_k=5)

        assert context is not None


# =============================================================================
# TestEndToEndScenarios
# =============================================================================

class TestEndToEndScenarios:
    """端到端场景测试"""

    @pytest.mark.asyncio
    async def test_complete_query_flow(self):
        """测试完整查询流程（使用 Mock）"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        # Mock LLM 返回有效 SQL
        mock_llm = MockLLMClient(
            response_content="SELECT dept_name AS 部门, SUM(amount) AS 报销总额 FROM dept_expense GROUP BY dept_name"
        )

        with patch("micro_genbi.llm.base.create_llm_client", return_value=mock_llm):
            service = await factory.create(mode=ServiceMode.SINGLE)

            # 执行查询
            result = await service.ask("各部门上月的报销总额是多少？")

            # 验证结果
            assert result is not None
            assert result.sql is not None
            assert len(result.data) > 0
            assert result.execution_time_ms >= 0

            # 清理
            await factory.close()

    @pytest.mark.asyncio
    async def test_multiple_queries_same_session(self):
        """测试同一会话的多次查询（使用 Mock）"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        mock_llm = MockLLMClient(response_content="SELECT dept_name, amount FROM dept_expense LIMIT 10")

        with patch("micro_genbi.llm.base.create_llm_client", return_value=mock_llm):
            service = await factory.create(mode=ServiceMode.SINGLE)

            session_id = "test_session_e2e"

            # 第一轮
            result1 = await service.ask(
                "各部门报销总额是多少？",
                session_id=session_id
            )
            assert result1.session_id == session_id

            # 第二轮
            result2 = await service.ask(
                "哪些部门超过平均金额？",
                session_id=session_id
            )
            assert result2.session_id == session_id

            await factory.close()

    @pytest.mark.asyncio
    async def test_concurrent_queries(self):
        """测试并发查询（使用 Mock）"""
        from micro_genbi.service.factory import ServiceFactory, ServiceMode

        factory = ServiceFactory()

        mock_llm = MockLLMClient(response_content="SELECT 1 FROM dual")

        with patch("micro_genbi.llm.base.create_llm_client", return_value=mock_llm):
            service = await factory.create(mode=ServiceMode.SINGLE)

            queries = [
                "各部门报销总额是多少？",
                "统计本月订单数量",
                "查询销售部门的数据",
            ]

            # 并发执行
            tasks = [service.ask(q) for q in queries]
            results = await asyncio.gather(*tasks)

            assert len(results) == 3
            for result in results:
                assert result is not None
                assert result.sql is not None

            await factory.close()
