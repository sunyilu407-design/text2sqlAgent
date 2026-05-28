"""图表生成模块

基于 ECharts 的图表生成引擎，支持规则推断和 LLM 增强。
"""

from __future__ import annotations

from typing import Any, Optional

from micro_genbi.models import ChartType

from micro_genbi.chart.smart_recommender import (
    ChartRecommender,
    ChartRecommendation,
    ColumnTypeInfo,
    ColumnType,
)


class ChartEngine:
    """
    图表生成引擎

    根据数据特征和查询意图，自动选择最合适的图表类型。

    Attributes:
        recommender: ChartRecommender 实例，用于智能推荐图表类型
    """

    def __init__(self):
        self.recommender = ChartRecommender()

    def generate(
        self,
        data: list[dict[str, Any]],
        intent: Optional[str] = None,
        forced_type: Optional[ChartType] = None,
    ) -> Optional[dict[str, Any]]:
        """
        生成图表配置

        Args:
            data: 查询结果数据
            intent: 意图类型（用于图表选择）
            forced_type: 强制图表类型

        Returns:
            ECharts 图表配置字典，或 None（无法生成图表时）
        """
        if not data or len(data) == 0:
            return None

        chart_type = forced_type or self._infer_chart_type(data, intent)
        if chart_type == ChartType.TABLE:
            return self._build_table_config(data)

        return self._build_chart_options(data, chart_type)

    def _infer_chart_type(
        self,
        data: list[dict[str, Any]],
        intent: Optional[str] = None,
    ) -> ChartType:
        """根据数据特征推断图表类型"""
        if not data:
            return ChartType.TABLE

        # 基于意图推断
        intent_lower = (intent or "").lower()
        if intent_lower in ("trend", "趋势", "走势"):
            return ChartType.LINE
        if intent_lower in ("comparison", "对比", "比较"):
            return ChartType.BAR
        if intent_lower in ("ranking", "排名", "top"):
            return ChartType.BAR
        if intent_lower in ("aggregation", "占比", "比例", "pie"):
            return ChartType.PIE

        # 基于数据特征推断
        columns = list(data[0].keys())
        numeric_cols = [
            c for c in columns
            if self._is_numeric(data[0].get(c))
        ]
        date_cols = [
            c for c in columns
            if self._is_date_like(data[0].get(c))
        ]

        # 时间序列 + 数值 → line
        if date_cols and numeric_cols:
            return ChartType.LINE

        # 分类 + 数值 → bar
        if numeric_cols and len(columns) >= 2:
            return ChartType.BAR

        # 百分比/占比场景 → pie
        if len(numeric_cols) == 1 and len(data) <= 10:
            return ChartType.PIE

        return ChartType.TABLE

    def _is_numeric(self, value: Any) -> bool:
        """判断是否为数值类型"""
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return True
        if isinstance(value, str):
            try:
                float(value)
                return True
            except (ValueError, TypeError):
                return False
        return False

    def _is_date_like(self, value: Any) -> bool:
        """判断是否像日期"""
        if value is None:
            return False
        if isinstance(value, str):
            return len(value) in (7, 10) and ("-" in value or "/" in value)
        return False

    def _build_table_config(
        self,
        data: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """构建表格配置"""
        if not data:
            return {"type": "table", "data": []}

        columns = list(data[0].keys())
        return {
            "type": "table",
            "data": data,
            "columns": columns,
        }

    def _build_chart_options(
        self,
        data: list[dict[str, Any]],
        chart_type: ChartType,
    ) -> dict[str, Any]:
        """构建 ECharts 图表配置"""
        if not data:
            return {"type": chart_type.value, "data": [], "options": {}}

        columns = list(data[0].keys())
        numeric_cols = [c for c in columns if self._is_numeric(data[0].get(c))]
        date_cols = [c for c in columns if self._is_date_like(data[0].get(c))]
        dim_cols = [c for c in columns if c not in numeric_cols and c not in date_cols]

        x_col = (date_cols or dim_cols or columns)[0]
        y_cols = numeric_cols if numeric_cols else [c for c in columns if c != x_col]

        series = []
        for y_col in y_cols:
            series_data = [
                {"value": row.get(y_col), "name": row.get(x_col, "")}
                for row in data
            ]

            if chart_type == ChartType.PIE:
                series.append({
                    "name": y_col,
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "data": series_data,
                    "label": {"show": True, "formatter": "{b}: {c} ({d}%)"},
                })
            else:
                series.append({
                    "name": y_col,
                    "type": chart_type.value,
                    "data": [row.get(y_col) for row in data],
                })

        options = {
            "title": {"text": "", "left": "center"},
            "tooltip": {"trigger": "axis"} if chart_type != ChartType.PIE else {"trigger": "item"},
            "legend": {
                "data": [s["name"] for s in series] if len(series) > 1 else None,
                "top": 30,
            },
            "xAxis": {
                "type": "category" if chart_type != ChartType.PIE else None,
                "data": [row.get(x_col) for row in data] if chart_type != ChartType.PIE else None,
                "name": x_col,
            },
            "yAxis": {
                "type": "value",
                "name": ", ".join(y_cols) if y_cols else "",
            },
            "series": series,
            "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "60px"},
            "color": [
                "#5470c6", "#91cc75", "#fac858", "#ee6666",
                "#73c0de", "#3ba272", "#fc8452", "#9a60b4",
            ],
        }

        # 饼图不需要 xAxis/yAxis
        if chart_type == ChartType.PIE:
            options.pop("xAxis", None)
            options.pop("yAxis", None)

        return {
            "type": chart_type.value,
            "data": data,
            "options": options,
        }

    def recommend_smart(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        intent_type: str,
    ) -> ChartRecommendation:
        """
        使用智能推荐器推荐图表

        Args:
            data: 查询结果数据
            columns: 列名列表
            intent_type: 意图类型

        Returns:
            ChartRecommendation: 图表推荐结果
        """
        return self.recommender.recommend(data, columns, intent_type)
