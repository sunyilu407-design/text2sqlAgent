"""意图分类模块

三层意图分类器：
1. 规则匹配（低成本，覆盖 ~70% 请求）
2. LLM 分类（高置信度，覆盖 ~30%）
3. 兜底 TEXT_TO_SQL（保守假设）
"""

from __future__ import annotations

from typing import Optional

from micro_genbi.models import IntentType, IntentClassification
from micro_genbi.llm.base import LLMClient


class IntentClassifier:
    """
    意图分类器

    采用三层分类策略：
    1. 规则匹配（低成本）
    2. LLM 分类（高置信度）
    """

    # 意图关键词映射（按优先级排序：更具体的模式在前）
    INTENT_PATTERNS = {
        IntentType.AGGREGATION: [
            "统计", "合计", "总计", "sum", "count", "avg", "平均",
            "总数", "count", "汇总", "聚合", "总金额", "总额",
        ],
        IntentType.TREND: [
            "趋势", "走势", "变化趋势", "历史", "最近", "环比",
            "同比", "period", "trend", "over time",
        ],
        IntentType.COMPARISON: [
            "对比", "比较", "差异", "多了", "少了", "增减",
            "增长", "下降", "compare", "versus", "vs",
        ],
        IntentType.FILTER: [
            "查找", "查询", "筛选", "过滤", "只看", "只要", "查",
            "filter", "where", "find", "查销售",
        ],
        IntentType.RANKING: [
            "排名", "top", "前三", "倒数", "排序", "最大", "最小",
            "rank", "highest", "lowest", "order by", "前10",
        ],
    }

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def classify(self, query: str) -> IntentClassification:
        """
        分类用户查询的意图

        Args:
            query: 用户查询

        Returns:
            IntentClassification: 分类结果
        """
        # 第一层：规则匹配
        for intent, keywords in self.INTENT_PATTERNS.items():
            for keyword in keywords:
                if keyword.lower() in query.lower():
                    return IntentClassification(
                        intent=intent,
                        confidence=0.85,
                        reasoning=f"关键词匹配: {keyword}",
                    )

        # 第二层：LLM 分类
        prompt = f"""请分析以下用户查询的意图类型，只回答一个词（query/aggregation/comparison/trend/filter/ranking）。

用户查询: {query}

只回答意图类型，不要解释。"""

        try:
            response = await self.llm_client.generate(prompt)
            intent_str = response.content.strip().lower()

            # 映射到 IntentType
            intent_map = {
                "query": IntentType.QUERY,
                "aggregation": IntentType.AGGREGATION,
                "comparison": IntentType.COMPARISON,
                "trend": IntentType.TREND,
                "filter": IntentType.FILTER,
                "ranking": IntentType.RANKING,
            }

            intent = intent_map.get(intent_str, IntentType.UNKNOWN)

            return IntentClassification(
                intent=intent,
                confidence=0.75,
                reasoning="LLM 分类",
            )

        except Exception:
            # 第三层：兜底
            return IntentClassification(
                intent=IntentType.QUERY,
                confidence=0.5,
                reasoning="默认分类（LLM 失败）",
            )
