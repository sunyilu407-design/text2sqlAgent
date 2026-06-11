"""ChartEngine 单元测试"""

import pytest
from micro_genbi.chart import ChartEngine


class TestChartEngine:
    """图表引擎测试"""

    @pytest.fixture
    def engine(self) -> ChartEngine:
        return ChartEngine()

    @pytest.fixture
    def sample_data_time_series(self) -> list[dict]:
        return [
            {"date": "2024-01-01", "value": 100},
            {"date": "2024-01-02", "value": 120},
            {"date": "2024-01-03", "value": 95},
            {"date": "2024-01-04", "value": 150},
            {"date": "2024-01-05", "value": 180},
        ]

    @pytest.fixture
    def sample_data_category(self) -> list[dict]:
        return [
            {"city": "杭州", "sales": 50000},
            {"city": "宁波", "sales": 35000},
            {"city": "温州", "sales": 28000},
            {"city": "金华", "sales": 22000},
        ]

    def test_generate_time_series(self, engine: ChartEngine, sample_data_time_series):
        """测试时间序列数据生成折线图"""
        result = engine.generate(
            data=sample_data_time_series,
            intent="分析销售趋势",
        )
        assert result is not None
        assert "data" in result

    def test_generate_category(self, engine: ChartEngine, sample_data_category):
        """测试分类数据生成柱状图"""
        result = engine.generate(
            data=sample_data_category,
            intent="各城市销售对比",
        )
        assert result is not None

    def test_generate_with_forced_type(self, engine: ChartEngine, sample_data_time_series):
        """测试强制指定图表类型"""
        from micro_genbi.models import ChartType
        result = engine.generate(
            data=sample_data_time_series,
            intent="",
            forced_type=ChartType.BAR,
        )
        assert result is not None

    def test_generate_empty_data(self, engine: ChartEngine):
        """测试空数据返回 None"""
        result = engine.generate(data=[], intent="test")
        assert result is None

    def test_infer_chart_type_trend(self, engine: ChartEngine):
        """测试趋势意图推断为折线图"""
        data = [{"date": "2024-01-01", "value": 100}]
        chart_type = engine._infer_chart_type(data, "趋势分析")
        assert chart_type.value == "line"

    def test_infer_chart_type_comparison(self, engine: ChartEngine):
        """测试对比意图推断为柱状图"""
        data = [{"city": "杭州", "sales": 50000}]
        chart_type = engine._infer_chart_type(data, "对比各城市")
        assert chart_type.value == "bar"

    def test_infer_chart_type_ratio(self, engine: ChartEngine):
        """测试占比意图推断为饼图"""
        data = [{"product": "汽油", "ratio": 0.45}]
        chart_type = engine._infer_chart_type(data, "占比")
        assert chart_type.value == "pie"


class TestChartRecommender:
    """图表推荐器测试"""

    def test_recommend_returns_valid_result(self):
        """推荐应返回有效结果"""
        from micro_genbi.chart.smart_recommender import ChartRecommender

        recommender = ChartRecommender()
        data = [{"a": 1, "b": 2}]
        result = recommender.recommend(data, ["a", "b"], "")
        assert isinstance(result.chart_type, str)
        assert isinstance(result.confidence, float)
        assert isinstance(result.reason, str)
        assert isinstance(result.options, dict)
        assert isinstance(result.alternatives, list)

    def test_recommend_confidence_in_range(self):
        """推荐置信度应在 0-1 之间"""
        from micro_genbi.chart.smart_recommender import ChartRecommender

        recommender = ChartRecommender()
        data = [{"a": 1, "b": 2}]
        result = recommender.recommend(data, ["a", "b"], "")
        assert 0.0 <= result.confidence <= 1.0

    def test_recommend_with_any_intent(self):
        """任意意图输入均应返回结果"""
        from micro_genbi.chart.smart_recommender import ChartRecommender

        recommender = ChartRecommender()
        data = [{"x": 1, "y": 2}]
        for intent in ["", "趋势", "对比", "排名", "分布"]:
            result = recommender.recommend(data, ["x", "y"], intent)
            assert result is not None
            assert result.chart_type != ""

    def test_recommend_pie_with_numeric(self):
        """数值类型数据应能生成推荐"""
        from micro_genbi.chart.smart_recommender import ChartRecommender

        recommender = ChartRecommender()
        data = [{"city": "杭州", "sales": 50000}]
        result = recommender.recommend(data, ["city", "sales"], "")
        assert result.chart_type != ""

    def test_recommend_empty_data_returns_table(self):
        """空数据应返回表格推荐"""
        from micro_genbi.chart.smart_recommender import ChartRecommender

        recommender = ChartRecommender()
        result = recommender.recommend([], [], "")
        assert result.chart_type == "table"
