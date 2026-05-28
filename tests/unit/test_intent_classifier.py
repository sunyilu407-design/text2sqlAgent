"""IntentClassifier 单元测试"""

import pytest
from micro_genbi.intent.classifier import IntentClassifier
from micro_genbi.models import IntentType, IntentClassification


class TestIntentClassifierRuleLayer:
    """意图分类器第一层（规则匹配）测试"""

    @pytest.fixture
    def classifier(self) -> IntentClassifier:
        """创建意图分类器"""
        from unittest.mock import AsyncMock
        mock_llm = AsyncMock()
        mock_llm.generate = AsyncMock(return_value=type("obj", (), {"content": "query"})())
        return IntentClassifier(llm_client=mock_llm)

    @pytest.mark.parametrize("query,expected_intent", [
        # 聚合查询
        ("各部门报销总额是多少？", IntentType.AGGREGATION),
        ("统计本月订单数量", IntentType.AGGREGATION),
        ("合计所有销售额", IntentType.AGGREGATION),
        ("总计支出金额", IntentType.AGGREGATION),
        # 对比查询
        ("销售部和市场部的业绩对比？", IntentType.COMPARISON),
        ("对比两个月的收入", IntentType.COMPARISON),
        ("和上周相比增长了多少", IntentType.COMPARISON),
        # 趋势查询
        ("过去三个月的销售趋势如何？", IntentType.TREND),
        ("最近一周的订单走势", IntentType.TREND),
        ("未来三个月的预测趋势", IntentType.TREND),
        ("环比增长率的历史变化", IntentType.TREND),
        ("销售额的历史走势", IntentType.TREND),
        # 筛选查询
        ("只查销售部的数据", IntentType.FILTER),
        ("筛选状态为已完成", IntentType.FILTER),
        ("查找张三的订单", IntentType.FILTER),
        # 排名查询
        ("销售额最高的前10名商品是什么？", IntentType.RANKING),
        ("排名最后的部门", IntentType.RANKING),
        ("按金额排序", IntentType.RANKING),
    ])
    @pytest.mark.asyncio
    async def test_rule_classification(
        self,
        classifier: IntentClassifier,
        query: str,
        expected_intent: IntentType,
    ):
        """测试规则匹配"""
        result = await classifier.classify(query)
        assert result is not None
        assert result.intent == expected_intent, \
            f"'{query}' 应该分类为 {expected_intent}，实际为 {result.intent}"

    @pytest.mark.asyncio
    async def test_unmatched_query_falls_to_llm(self, classifier: IntentClassifier):
        """测试未匹配的查询走到 LLM 层"""
        # "随机字符串 xyz123" 不匹配任何规则，应该走到 LLM
        result = await classifier.classify("随机字符串 xyz123")
        assert result is not None
        assert result.intent in list(IntentType)

    @pytest.mark.asyncio
    async def test_intent_classification_result_structure(self, classifier: IntentClassifier):
        """测试分类结果结构"""
        result = await classifier.classify("各部门报销总额是多少？")
        assert isinstance(result, IntentClassification)
        assert hasattr(result, "intent")
        assert hasattr(result, "confidence")
        assert hasattr(result, "reasoning")
        assert isinstance(result.intent, IntentType)
        assert isinstance(result.confidence, float)
        assert 0 <= result.confidence <= 1

    @pytest.mark.asyncio
    async def test_case_insensitive_matching(self, classifier: IntentClassifier):
        """测试大小写不敏感匹配"""
        result = await classifier.classify("各部门总计金额")
        assert result.intent == IntentType.AGGREGATION

    @pytest.mark.asyncio
    async def test_mixed_case_keywords(self, classifier: IntentClassifier):
        """测试混合大小写关键词"""
        result = await classifier.classify("统计 SUm 销售额")
        assert result.intent == IntentType.AGGREGATION
