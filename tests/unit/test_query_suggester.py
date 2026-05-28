"""查询建议器单元测试"""

import pytest
from unittest.mock import MagicMock
from micro_genbi.intent.query_suggester import (
    QuerySuggester,
    QuerySuggestion,
)


# ── Tests: QuerySuggestion ──────────────────────────────────────────────────

class TestQuerySuggestion:
    """查询建议测试"""

    def test_creation(self):
        """测试创建"""
        suggestion = QuerySuggestion(
            text="本月销售额是多少？",
            type="template",
            confidence=0.85,
            metadata={"category": "统计"},
        )
        assert suggestion.text == "本月销售额是多少？"
        assert suggestion.type == "template"
        assert suggestion.confidence == 0.85
        assert suggestion.metadata["category"] == "统计"

    def test_defaults(self):
        """测试默认值"""
        suggestion = QuerySuggestion(
            text="test",
            type="template",
            confidence=0.5,
        )
        assert suggestion.metadata == {}


# ── Tests: QuerySuggester.suggest ───────────────────────────────────────────

class TestQuerySuggesterSuggest:
    """查询建议测试"""

    def setup_method(self):
        """Setup"""
        self.suggester = QuerySuggester()

    def test_suggest_empty_query_returns_defaults(self):
        """测试空查询返回默认建议"""
        suggestions = self.suggester.suggest("")
        assert len(suggestions) > 0
        assert all(isinstance(s, QuerySuggestion) for s in suggestions)

    def test_suggest_returns_list(self):
        """测试返回列表"""
        suggestions = self.suggester.suggest("本月销售")
        assert isinstance(suggestions, list)

    def test_suggest_respects_top_k(self):
        """测试 top_k 参数"""
        suggestions = self.suggester.suggest("本月销售", top_k=3)
        assert len(suggestions) <= 3

    def test_suggest_sorted_by_confidence(self):
        """测试按置信度排序"""
        suggestions = self.suggester.suggest("本月销售", top_k=10)
        if len(suggestions) >= 2:
            # 验证排序（高置信度在前）
            for i in range(len(suggestions) - 1):
                assert suggestions[i].confidence >= suggestions[i + 1].confidence


# ── Tests: Time Query Expansion ─────────────────────────────────────────────

class TestTimeQueryExpansion:
    """时间查询扩展测试"""

    def setup_method(self):
        self.suggester = QuerySuggester()

    def test_expand_today(self):
        """测试今天"""
        suggestions = self.suggester.suggest("今天的订单")
        time_suggestions = [s for s in suggestions if s.type == "time"]
        assert len(time_suggestions) > 0
        assert any("今天" in s.metadata.get("matched", "") for s in time_suggestions)

    def test_expand_this_month(self):
        """测试本月"""
        suggestions = self.suggester.suggest("本月销售额")
        time_suggestions = [s for s in suggestions if s.type == "time"]
        assert len(time_suggestions) > 0

    def test_expand_this_week(self):
        """测试本周"""
        suggestions = self.suggester.suggest("本周新增客户")
        time_suggestions = [s for s in suggestions if s.type == "time"]
        assert len(time_suggestions) > 0

    def test_expand_recent_days(self):
        """测试最近N天"""
        suggestions = self.suggester.suggest("最近7天的订单")
        time_suggestions = [s for s in suggestions if s.type == "time"]
        assert len(time_suggestions) > 0

    def test_expand_last_month(self):
        """测试上月"""
        suggestions = self.suggester.suggest("上月销售额")
        time_suggestions = [s for s in suggestions if s.type == "time"]
        assert len(time_suggestions) > 0


# ── Tests: Template Matching ─────────────────────────────────────────────────

class TestTemplateMatching:
    """模板匹配测试"""

    def setup_method(self):
        self.suggester = QuerySuggester()

    def test_match_stat_template(self):
        """测试统计模板"""
        suggestions = self.suggester.suggest("统计本月销售额")
        template_suggestions = [s for s in suggestions if s.type == "template"]
        assert len(template_suggestions) > 0

    def test_match_count_template(self):
        """测试数量模板"""
        suggestions = self.suggester.suggest("有多少客户")
        template_suggestions = [s for s in suggestions if s.type == "template"]
        assert len(template_suggestions) > 0

    def test_match_query_template(self):
        """测试查询模板"""
        suggestions = self.suggester.suggest("查询订单")
        template_suggestions = [s for s in suggestions if s.type == "template"]
        assert len(template_suggestions) > 0

    def test_match_ranking_template(self):
        """测试排名模板"""
        suggestions = self.suggester.suggest("前10名商品")
        template_suggestions = [s for s in suggestions if s.type == "template"]
        assert len(template_suggestions) > 0

    def test_match_comparison_template(self):
        """测试对比模板"""
        suggestions = self.suggester.suggest("各部门对比")
        template_suggestions = [s for s in suggestions if s.type == "template"]
        assert len(template_suggestions) > 0


# ── Tests: Query Completion ───────────────────────────────────────────────────

class TestQueryCompletion:
    """查询补全测试"""

    def setup_method(self):
        self.suggester = QuerySuggester()

    def test_suggest_completion(self):
        """测试补全建议"""
        suggestions = self.suggester.suggest("本月销售额")
        expansion_suggestions = [s for s in suggestions if s.type == "expansion"]
        # 应该建议添加后缀
        assert len(expansion_suggestions) > 0

    def test_completion_adds_suffix(self):
        """测试补全添加后缀"""
        suggestions = self.suggester.suggest("本月销售额")
        expansion_suggestions = [s for s in suggestions if s.type == "expansion"]
        # 建议应该包含原始查询
        assert any("本月销售额" in s.text for s in expansion_suggestions)


# ── Tests: Field Suggestion ──────────────────────────────────────────────────

class TestFieldSuggestion:
    """字段建议测试"""

    def test_suggest_fields_with_registry(self):
        """测试带 Schema Registry 的字段建议"""
        mock_registry = MagicMock()
        suggester = QuerySuggester(schema_registry=mock_registry)
        suggestions = suggester.suggest("查询订单")
        # 字段建议可能为空，但不报错
        assert isinstance(suggestions, list)

    def test_suggest_fields_without_registry(self):
        """测试不带 Schema Registry"""
        suggester = QuerySuggester(schema_registry=None)
        suggestions = suggester.suggest("查询订单")
        # 字段建议应该为空
        field_suggestions = [s for s in suggestions if s.type == "field"]
        assert len(field_suggestions) == 0


# ── Tests: expand_time_reference ─────────────────────────────────────────────

class TestExpandTimeReference:
    """时间引用扩展测试"""

    def setup_method(self):
        self.suggester = QuerySuggester()

    def test_expand_today(self):
        """测试扩展今天"""
        result = self.suggester.expand_time_reference("今天的订单")
        assert "今天" in result or "当天" in result

    def test_expand_this_month(self):
        """测试扩展本月"""
        result = self.suggester.expand_time_reference("本月的销售额")
        assert "本月" in result

    def test_expand_recent_days(self):
        """测试扩展最近N天"""
        result = self.suggester.expand_time_reference("最近7天的订单")
        assert "7" in result or "7天" in result

    def test_expand_no_match(self):
        """测试无时间引用"""
        result = self.suggester.expand_time_reference("查询所有订单")
        assert result == ""

    def test_expand_multiple(self):
        """测试多个时间引用"""
        result = self.suggester.expand_time_reference("本月和上月对比")
        assert len(result) > 0


# ── Tests: suggest_time_filter ───────────────────────────────────────────────

class TestSuggestTimeFilter:
    """时间过滤建议测试"""

    def setup_method(self):
        self.suggester = QuerySuggester()

    def test_suggest_time_filter_today(self):
        """测试今天的过滤"""
        result = self.suggester.suggest_time_filter("今天")
        assert "mysql" in result
        assert "postgresql" in result
        assert "sqlite" in result
        assert "CURDATE" in result["mysql"] or "CURRENT_DATE" in result["mysql"]

    def test_suggest_time_filter_this_month(self):
        """测试本月的过滤"""
        result = self.suggester.suggest_time_filter("本月")
        assert "mysql" in result
        assert "WHERE" in result["mysql"]

    def test_suggest_time_filter_this_year(self):
        """测试本年的过滤"""
        result = self.suggester.suggest_time_filter("本年")
        assert "mysql" in result
        assert "YEAR" in result["mysql"]

    def test_suggest_time_filter_recent_days(self):
        """测试最近N天的过滤"""
        result = self.suggester.suggest_time_filter("最近7天")
        assert "mysql" in result
        assert "7" in result["mysql"]

    def test_suggest_time_filter_unknown(self):
        """测试未知时间引用"""
        result = self.suggester.suggest_time_filter("未知时间")
        assert result == {}

    def test_suggest_time_filter_postgresql_dialect(self):
        """测试 PostgreSQL 方言"""
        result = self.suggester.suggest_time_filter("今天")
        pg = result.get("postgresql", "")
        assert "CURRENT_DATE" in pg

    def test_suggest_time_filter_sqlite_dialect(self):
        """测试 SQLite 方言"""
        result = self.suggester.suggest_time_filter("今天")
        sqlite = result.get("sqlite", "")
        assert "DATE" in sqlite


# ── Tests: Default Suggestions ───────────────────────────────────────────────

class TestDefaultSuggestions:
    """默认建议测试"""

    def test_get_default_suggestions(self):
        """测试获取默认建议"""
        suggester = QuerySuggester()
        suggestions = suggester._get_default_suggestions()
        assert len(suggestions) == 5
        assert all(s.type == "template" for s in suggestions)

    def test_default_suggestions_have_confidence(self):
        """测试默认建议有置信度"""
        suggester = QuerySuggester()
        suggestions = suggester._get_default_suggestions()
        for s in suggestions:
            assert 0 <= s.confidence <= 1

    def test_default_suggestions_categories(self):
        """测试默认建议分类"""
        suggester = QuerySuggester()
        suggestions = suggester._get_default_suggestions()
        categories = [s.metadata.get("category") for s in suggestions]
        assert None not in categories


# ── Tests: TIME_PATTERNS initialization ─────────────────────────────────────

class TestTimePatternsInit:
    """时间模式初始化测试"""

    def test_time_patterns_lazy_init(self):
        """测试延迟初始化"""
        # TIME_PATTERNS 是类变量，多个测试共享
        # 所以只验证初始化后有内容，不验证初始为空
        suggester = QuerySuggester()
        suggester._init_time_patterns()
        assert len(suggester.TIME_PATTERNS) > 0

    def test_time_patterns_idempotent(self):
        """测试多次初始化是幂等的"""
        suggester = QuerySuggester()
        suggester._init_time_patterns()
        first_len = len(suggester.TIME_PATTERNS)
        suggester._init_time_patterns()
        second_len = len(suggester.TIME_PATTERNS)
        assert first_len == second_len
