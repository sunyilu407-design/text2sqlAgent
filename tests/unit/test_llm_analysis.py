"""LLM Analysis Service 单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from micro_genbi.service.llm_analysis import (
    LLMAnalysisService,
    AnalysisType,
)


class TestLLMAnalysisService:
    """LLM 分析服务测试"""

    @pytest.fixture
    def mock_llm(self):
        mock = AsyncMock()
        mock.generate = AsyncMock(return_value=MagicMock(
            content='{"conclusion": "分析结论", "findings": ["发现1", "发现2"], "confidence": 0.85, "suggestions": ["建议1"]}'
        ))
        return mock

    @pytest.fixture
    def service(self, mock_llm):
        return LLMAnalysisService(llm_client=mock_llm)

    @pytest.fixture
    def sample_query_result(self):
        return {
            "data": [
                {"city": "杭州", "sales": 50000, "orders": 120},
                {"city": "宁波", "sales": 35000, "orders": 85},
                {"city": "温州", "sales": 28000, "orders": 65},
            ],
            "columns": ["city", "sales", "orders"],
            "row_count": 3,
            "sql": "SELECT city, SUM(sales) FROM orders GROUP BY city",
        }

    @pytest.mark.asyncio
    async def test_interpret_analysis(self, service, sample_query_result):
        """测试结果解读分析"""
        result = await service.analyze(
            query_result=sample_query_result,
            analysis_type=AnalysisType.INTERPRET,
        )
        assert result.type == "interpret"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_compare_analysis(self, service, sample_query_result):
        """测试对比分析"""
        result = await service.analyze(
            query_result=sample_query_result,
            analysis_type=AnalysisType.COMPARE,
        )
        assert result.type == "compare"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_sql_explain(self, service, sample_query_result):
        """测试 SQL 解读"""
        result = await service.analyze(
            query_result=sample_query_result,
            analysis_type=AnalysisType.SQL_EXPLAIN,
        )
        assert result.type == "sql_explain"
        assert result.confidence > 0

    @pytest.mark.asyncio
    async def test_forecast_reasoning(self, service, sample_query_result):
        """测试预测推理"""
        result = await service.analyze(
            query_result=sample_query_result,
            analysis_type=AnalysisType.FORECAST_REASONING,
        )
        assert result.type == "forecast_reasoning"

    @pytest.mark.asyncio
    async def test_parallel_analysis(self, service, sample_query_result):
        """测试并行多类型分析"""
        results = await service.analyze_parallel(
            query_result=sample_query_result,
            analysis_types=[AnalysisType.INTERPRET, AnalysisType.COMPARE],
        )
        assert len(results) == 2
        assert any(r.type == "interpret" for r in results)
        assert any(r.type == "compare" for r in results)

    @pytest.mark.asyncio
    async def test_llm_failure_returns_error_result(self, service, sample_query_result):
        """LLM 调用失败应返回错误结果而非抛出异常"""
        service._llm.generate = AsyncMock(side_effect=Exception("LLM unavailable"))
        result = await service.analyze(
            query_result=sample_query_result,
            analysis_type=AnalysisType.INTERPRET,
        )
        assert result.error != ""
        assert result.confidence == 0.0

    def test_analysis_types_enum(self):
        """测试分析类型枚举值"""
        assert AnalysisType.INTERPRET.value == "interpret"
        assert AnalysisType.COMPARE.value == "compare"
        assert AnalysisType.ANOMALY.value == "anomaly"
        assert AnalysisType.FORECAST_REASONING.value == "forecast_reasoning"
        assert AnalysisType.SQL_EXPLAIN.value == "sql_explain"

    def test_result_to_dict(self):
        """测试结果序列化"""
        from micro_genbi.service.llm_analysis import AnalysisResult
        result = AnalysisResult(
            type="interpret",
            conclusion="测试结论",
            findings=["发现1"],
            confidence=0.9,
            suggestions=["建议1"],
        )
        d = result.to_dict()
        assert d["type"] == "interpret"
        assert d["conclusion"] == "测试结论"
        assert d["confidence"] == 0.9
        assert "to_openai_messages" in dir(result)
        assert "to_anthropic_messages" in dir(result)

    def test_result_to_openai_messages(self):
        """测试转换为 OpenAI 消息格式"""
        from micro_genbi.service.llm_analysis import AnalysisResult
        result = AnalysisResult(
            type="interpret",
            conclusion="测试",
            findings=["发现"],
            confidence=0.8,
            suggestions=["建议"],
        )
        messages = result.to_openai_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert "测试" in messages[0]["content"]

    def test_result_to_anthropic_messages(self):
        """测试转换为 Anthropic 消息格式"""
        from micro_genbi.service.llm_analysis import AnalysisResult
        result = AnalysisResult(
            type="compare",
            conclusion="对比结论",
            findings=["发现"],
            confidence=0.85,
            suggestions=["建议"],
        )
        messages = result.to_anthropic_messages()
        assert len(messages) == 1
        assert messages[0]["role"] == "assistant"
        assert messages[0]["type"] == "text"
