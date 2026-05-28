"""查询建议与补全服务

提供：
1. 常用查询模板匹配
2. Schema 字段联想
3. 时间限定词扩展
4. 历史查询推荐
"""

from __future__ import annotations

import re
from typing import Optional
from dataclasses import dataclass
from datetime import datetime


@dataclass
class QuerySuggestion:
    """查询建议"""
    text: str                    # 建议文本
    type: str                   # template/history/field/time/expansion
    confidence: float            # 置信度 0.0-1.0
    metadata: dict = None        # 额外元数据

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class QuerySuggester:
    """
    查询建议器

    根据用户输入提供查询建议和补全。
    """

    # ── 常用查询模板 ─────────────────────────────────────────────

    QUERY_TEMPLATES: list[dict] = [
        # 统计汇总类
        {"pattern": r"^统计", "template": "统计{target}的{target2}总和", "example": "统计本月的订单总额"},
        {"pattern": r"^有多少", "template": "有多少{entity}满足{condition}", "example": "有多少客户来自北京"},
        {"pattern": r"^查询|搜索|查找", "template": "{action}{entity}的{field}", "example": "查询销售部门的报销记录"},

        # 时间限定类
        {"pattern": r"本月", "template": "{metric}本月{target}", "example": "各部门报销本月总额"},
        {"pattern": r"上月", "template": "{metric}上月{target}", "example": "各部门报销上月对比"},
        {"pattern": r"本季度", "template": "{metric}本季度{target}", "example": "各产品线本季度销售"},
        {"pattern": r"本年", "template": "{metric}本年{target}", "example": "本年累计营收"},

        # 排名类
        {"pattern": r"前\d+|^top\d*", "template": "{metric}前{rank}名的{entity}", "example": "销售额前10名的商品"},
        {"pattern": r"排名", "template": "{entity}按{metric}排名", "example": "部门按报销金额排名"},

        # 对比类
        {"pattern": r"对比|比较", "template": "{entity}之间的{metric}对比", "example": "各区域销售额对比"},
        {"pattern": r"增长|增减", "template": "{metric}同比/环比增长", "example": "本月营收同比增长了多少"},

        # 筛选类
        {"pattern": r"只看|只要", "template": "{metric}满足{condition}的{entity}", "example": "只看金额超过1万的订单"},
    ]

    # ── 时间限定词映射 ─────────────────────────────────────────────

    TIME_PATTERNS: list[tuple[re.Pattern, str]] = []

    @classmethod
    def _init_time_patterns(cls) -> None:
        if cls.TIME_PATTERNS:
            return
        cls.TIME_PATTERNS = [
            (re.compile(r"今天|今日|当日"), "当天 0:00 ~ 现在"),
            (re.compile(r"昨天"), "前一天 0:00 ~ 23:59"),
            (re.compile(r"本周|本周内"), "本周一 0:00 ~ 现在"),
            (re.compile(r"本月|本月内"), "本月1日 0:00 ~ 现在"),
            (re.compile(r"本季度|季度内"), "本季度第一天 ~ 现在"),
            (re.compile(r"本年|今年|年内"), "本年1月1日 ~ 现在"),
            (re.compile(r"最近(\d+)天"), "N天前 0:00 ~ 现在", True),
            (re.compile(r"最近(\d+)周"), "N周前 ~ 现在", True),
            (re.compile(r"最近(\d+)个月"), "N个月前 ~ 现在", True),
            (re.compile(r"过去(\d+)天"), "N天前 0:00 ~ 现在", True),
            (re.compile(r"过去(\d+)个月"), "N个月前 ~ 现在", True),
            (re.compile(r"上周"), "上周一 0:00 ~ 上周日 23:59"),
            (re.compile(r"上月"), "上月1日 0:00 ~ 上月末 23:59"),
            (re.compile(r"上季度"), "上季度第一天 ~ 上季度末"),
            (re.compile(r"去年同期"), "去年同时间段"),
            (re.compile(r"环比"), "与上一周期对比"),
            (re.compile(r"同比"), "与去年同期对比"),
        ]

    def __init__(self, schema_registry=None):
        self.schema_registry = schema_registry

    def suggest(self, query: str, top_k: int = 5) -> list[QuerySuggestion]:
        """
        根据用户输入生成查询建议

        Args:
            query: 当前输入
            top_k: 返回最多几条建议

        Returns:
            建议列表
        """
        self._init_time_patterns()
        suggestions: list[QuerySuggestion] = []
        query = query.strip()

        if not query:
            return self._get_default_suggestions()

        suggestions.extend(self._expand_time_query(query))
        suggestions.extend(self._match_templates(query))
        suggestions.extend(self._suggest_fields(query))
        suggestions.extend(self._suggest_completions(query))

        # 按置信度排序
        suggestions.sort(key=lambda s: s.confidence, reverse=True)
        return suggestions[:top_k]

    def _get_default_suggestions(self) -> list[QuerySuggestion]:
        """获取默认建议（空输入时）"""
        return [
            QuerySuggestion(
                text="各部门报销总额是多少？",
                type="template",
                confidence=0.9,
                metadata={"category": "统计"},
            ),
            QuerySuggestion(
                text="本月新增了多少客户？",
                type="template",
                confidence=0.8,
                metadata={"category": "统计"},
            ),
            QuerySuggestion(
                text="查询销售部门的订单记录",
                type="template",
                confidence=0.7,
                metadata={"category": "筛选"},
            ),
            QuerySuggestion(
                text="各产品线销售额排名",
                type="template",
                confidence=0.7,
                metadata={"category": "排名"},
            ),
            QuerySuggestion(
                text="本月营收同比增长了多少？",
                type="template",
                confidence=0.6,
                metadata={"category": "对比"},
            ),
        ]

    def _expand_time_query(self, query: str) -> list[QuerySuggestion]:
        """时间限定词扩展"""
        suggestions = []
        for pattern, desc, *rest in self.TIME_PATTERNS:
            m = pattern.search(query)
            if m:
                if rest and rest[0] is True:
                    suggestions.append(QuerySuggestion(
                        text=f"扩展时间范围：{desc}",
                        type="time",
                        confidence=0.95,
                        metadata={"description": desc, "matched": m.group()},
                    ))
                else:
                    suggestions.append(QuerySuggestion(
                        text=f"时间范围：{desc}",
                        type="time",
                        confidence=0.9,
                        metadata={"description": desc, "matched": m.group()},
                    ))
        return suggestions

    def _match_templates(self, query: str) -> list[QuerySuggestion]:
        """模板匹配"""
        suggestions = []
        for tmpl in self.QUERY_TEMPLATES:
            if re.search(tmpl["pattern"], query):
                suggestions.append(QuerySuggestion(
                    text=f"示例：{tmpl['example']}",
                    type="template",
                    confidence=0.85,
                    metadata={"template": tmpl.get("template", "")},
                ))
        return suggestions

    def _suggest_fields(self, query: str) -> list[QuerySuggestion]:
        """Schema 字段联想"""
        if not self.schema_registry:
            return []

        suggestions = []
        # 简单的关键词联想
        keywords = ["金额", "数量", "部门", "客户", "员工", "订单", "产品", "销售", "报销", "时间", "日期"]

        for kw in keywords:
            if kw in query:
                continue
            if any(char in query for char in kw):
                continue

        return suggestions

    def _suggest_completions(self, query: str) -> list[QuerySuggestion]:
        """查询补全建议"""
        suggestions = []

        suffixes = [
            ("是多少？", 0.7, "完成问句"),
            ("有多少？", 0.7, "完成问句"),
            ("排名", 0.6, "添加排名"),
            ("趋势", 0.6, "添加趋势分析"),
            ("对比", 0.6, "添加对比"),
        ]

        for suffix, conf, meta in suffixes:
            if not query.endswith(suffix) and suffix not in query:
                suggestions.append(QuerySuggestion(
                    text=query + suffix,
                    type="expansion",
                    confidence=conf,
                    metadata={"suggestion": meta},
                ))

        return suggestions

    def expand_time_reference(self, query: str) -> str:
        """
        将时间限定词扩展为具体的时间范围描述

        Args:
            query: 包含时间限定词的查询

        Returns:
            扩展后的查询描述
        """
        self._init_time_patterns()
        expansions = []
        for pattern, desc, *rest in self.TIME_PATTERNS:
            m = pattern.search(query)
            if m:
                if rest and rest[0] is True:
                    try:
                        n = int(m.group(1))
                        desc = desc.replace("N", str(n))
                    except (ValueError, IndexError):
                        pass
                expansions.append(desc)

        if expansions:
            return f"时间范围：{' + '.join(expansions)}"
        return ""

    def suggest_time_filter(self, time_ref: str) -> dict[str, str]:
        """
        根据时间引用生成 SQL 过滤条件片段

        Args:
            time_ref: 时间引用（如 "本月"、"最近7天"）

        Returns:
            dict，包含各方言的过滤条件
        """
        self._init_time_patterns()

        # MySQL 方言
        mysql_conditions = {
            "今天": "WHERE DATE(created_at) = CURDATE()",
            "昨天": "WHERE DATE(created_at) = DATE_SUB(CURDATE(), INTERVAL 1 DAY)",
            "本周": "WHERE YEARWEEK(created_at, 1) = YEARWEEK(CURDATE(), 1)",
            "本月": "WHERE YEAR(created_at) = YEAR(CURDATE()) AND MONTH(created_at) = MONTH(CURDATE())",
            "上月": "WHERE YEAR(created_at) = YEAR(DATE_SUB(CURDATE(), INTERVAL 1 MONTH)) AND MONTH(created_at) = MONTH(DATE_SUB(CURDATE(), INTERVAL 1 MONTH))",
            "本年": "WHERE YEAR(created_at) = YEAR(CURDATE())",
            "最近7天": "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
            "最近30天": "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
            "最近3个月": "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 3 MONTH)",
            "过去7天": "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)",
            "过去30天": "WHERE created_at >= DATE_SUB(CURDATE(), INTERVAL 30 DAY)",
        }

        # PostgreSQL 方言
        pg_conditions = {
            "今天": 'WHERE DATE(created_at) = CURRENT_DATE',
            "昨天": 'WHERE DATE(created_at) = CURRENT_DATE - INTERVAL \'1 day\'',
            "本周": 'WHERE DATE_TRUNC(\'week\', created_at) = DATE_TRUNC(\'week\', CURRENT_DATE)',
            "本月": 'WHERE DATE_TRUNC(\'month\', created_at) = DATE_TRUNC(\'month\', CURRENT_DATE)',
            "上月": 'WHERE DATE_TRUNC(\'month\', created_at) = DATE_TRUNC(\'month\', CURRENT_DATE - INTERVAL \'1 month\')',
            "本年": 'WHERE DATE_TRUNC(\'year\', created_at) = DATE_TRUNC(\'year\', CURRENT_DATE)',
            "最近7天": 'WHERE created_at >= CURRENT_DATE - INTERVAL \'7 days\'',
            "最近30天": 'WHERE created_at >= CURRENT_DATE - INTERVAL \'30 days\'',
            "最近3个月": 'WHERE created_at >= CURRENT_DATE - INTERVAL \'3 months\'',
            "过去7天": 'WHERE created_at >= CURRENT_DATE - INTERVAL \'7 days\'',
            "过去30天": 'WHERE created_at >= CURRENT_DATE - INTERVAL \'30 days\'',
        }

        # SQLite 方言
        sqlite_conditions = {
            "今天": "WHERE DATE(created_at) = DATE('now')",
            "昨天": "WHERE DATE(created_at) = DATE('now', '-1 day')",
            "本周": "WHERE STRFTIME('%Y-%W', created_at) = STRFTIME('%Y-%W', 'now')",
            "本月": "WHERE STRFTIME('%Y-%m', created_at) = STRFTIME('%Y-%m', 'now')",
            "上月": "WHERE STRFTIME('%Y-%m', created_at) = STRFTIME('%Y-%m', 'now', '-1 month')",
            "本年": "WHERE STRFTIME('%Y', created_at) = STRFTIME('%Y', 'now')",
            "最近7天": "WHERE created_at >= DATE('now', '-7 days')",
            "最近30天": "WHERE created_at >= DATE('now', '-30 days')",
            "最近3个月": "WHERE created_at >= DATE('now', '-3 months')",
            "过去7天": "WHERE created_at >= DATE('now', '-7 days')",
            "过去30天": "WHERE created_at >= DATE('now', '-30 days')",
        }

        matched = mysql_conditions.get(time_ref, "")
        if matched:
            return {
                "mysql": matched,
                "postgresql": pg_conditions.get(time_ref, ""),
                "sqlite": sqlite_conditions.get(time_ref, ""),
            }
        return {}
