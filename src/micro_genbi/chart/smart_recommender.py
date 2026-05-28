"""图表智能推荐模块

根据查询结果和意图类型，智能推荐最合适的 ECharts 图表类型。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional


class ColumnType(Enum):
    """列类型枚举"""
    TIME = "time"           # 时间/日期类型
    CATEGORY = "category"   # 分类/字符串类型
    NUMERIC = "numeric"     # 数值类型
    RATIO = "ratio"         # 比率/占比类型（0-1 或带 % 符号）
    UNKNOWN = "unknown"     # 未知类型


class ChartTypeRecommendation(Enum):
    """推荐的图表类型"""
    LINE = "line"
    BAR = "bar"
    BAR_DESC = "bar_desc"   # 降序排列的条形图
    PIE = "pie"
    SCATTER = "scatter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    TABLE = "table"


@dataclass
class ChartRecommendation:
    """图表推荐结果"""
    chart_type: str       # line/bar/pie/scatter/gauge/table
    confidence: float     # 0.0-1.0
    reason: str           # 为什么推荐这个图表
    options: dict         # ECharts options JSON
    suggested_configs: dict  # {color: [...], legend: bool, ...}
    alternatives: list[str]  # 备选图表类型


@dataclass
class ColumnTypeInfo:
    """列类型分析结果"""
    name: str
    column_type: ColumnType
    sample_values: list[Any] = field(default_factory=list)
    numeric_stats: dict[str, float] | None = None


# ECharts 配色方案
DEFAULT_COLORS = [
    "#5470c6", "#91cc75", "#fac858", "#ee6666",
    "#73c0de", "#3ba272", "#fc8452", "#9a60b4",
    "#ea7ccc", "#a45eea", "#ff7840", "#33bfc8",
]

# 中文月份名称映射
MONTH_NAMES = ["1月", "2月", "3月", "4月", "5月", "6月",
               "7月", "8月", "9月", "10月", "11月", "12月"]


class ChartRecommender:
    """
    图表智能推荐器

    根据查询结果的数据特征和意图类型，自动推荐最合适的图表类型。
    支持多种图表类型的自动推断和 ECharts 配置生成。
    """

    # 意图类型到图表类型的映射
    INTENT_CHART_MAP = {
        "trend": ChartTypeRecommendation.LINE,
        "趋势": ChartTypeRecommendation.LINE,
        "走势": ChartTypeRecommendation.LINE,
        "历史": ChartTypeRecommendation.LINE,
        "变化": ChartTypeRecommendation.LINE,
        "comparison": ChartTypeRecommendation.BAR,
        "对比": ChartTypeRecommendation.BAR,
        "比较": ChartTypeRecommendation.BAR,
        "差异": ChartTypeRecommendation.BAR,
        "ranking": ChartTypeRecommendation.BAR_DESC,
        "排名": ChartTypeRecommendation.BAR_DESC,
        "top": ChartTypeRecommendation.BAR_DESC,
        "排序": ChartTypeRecommendation.BAR_DESC,
        "aggregation": ChartTypeRecommendation.PIE,
        "聚合": ChartTypeRecommendation.PIE,
        "统计": ChartTypeRecommendation.PIE,
        "占比": ChartTypeRecommendation.PIE,
        "比例": ChartTypeRecommendation.PIE,
        "distribution": ChartTypeRecommendation.SCATTER,
        "分布": ChartTypeRecommendation.SCATTER,
        "散点": ChartTypeRecommendation.SCATTER,
        "filter": ChartTypeRecommendation.TABLE,
        "查询": ChartTypeRecommendation.TABLE,
        "筛选": ChartTypeRecommendation.TABLE,
        "query": ChartTypeRecommendation.TABLE,
    }

    # 时间日期模式
    DATE_PATTERNS = [
        r"^\d{4}-\d{2}-\d{2}$",        # 2024-01-01
        r"^\d{4}/\d{2}/\d{2}$",        # 2024/01/01
        r"^\d{4}-\d{2}$",               # 2024-01
        r"^\d{4}年\d{1,2}月$",          # 2024年1月
        r"^\d{4}年第\d{1,2}季度$",      # 2024年第1季度
        r"^\d{4}年\d{1,2}月\d{1,2}日$", # 2024年1月1日
        r"^\d{4}$",                      # 2024
        r"^\d{1,2}月$",                 # 1月
        r"^\d{1,2}日$",                 # 1日
    ]

    def __init__(self, locale: str = "zh_CN"):
        """
        初始化图表推荐器

        Args:
            locale: 区域设置，影响中文显示
        """
        self.locale = locale

    def recommend(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        intent_type: str,
    ) -> ChartRecommendation:
        """
        推荐最合适的图表类型

        Args:
            data: 查询结果数据
            columns: 列名列表
            intent_type: 意图类型

        Returns:
            ChartRecommendation: 图表推荐结果
        """
        # 处理边界情况
        if not data:
            return self._empty_recommendation("数据为空")

        if len(data) == 1:
            return self._single_row_recommendation(data[0], columns)

        # 分析数据结构
        column_types = self._analyze_result_structure(data, columns)

        # 根据意图推断图表
        chart_by_intent = self._infer_chart_by_intent(intent_type, column_types)

        # 根据数据特征推断图表
        chart_by_data = self._infer_chart_by_data(columns, column_types)

        # 综合判断：意图优先，但数据特征可以调整
        if chart_by_intent and chart_by_data:
            # 如果数据特征显示应该用 table，优先采用
            if chart_by_data.chart_type in (ChartTypeRecommendation.TABLE,):
                final_chart = chart_by_data
            else:
                final_chart = chart_by_intent
        elif chart_by_intent:
            final_chart = chart_by_intent
        else:
            final_chart = chart_by_data

        # 检查类别数量，过多时建议使用表格
        category_count = self._count_categories(data, columns, column_types)
        if category_count > 20:
            return self._many_categories_recommendation(data, columns)

        # 构建 ECharts 配置
        options = self._build_chart_options(
            final_chart.chart_type.value if isinstance(final_chart, ChartTypeRecommendation) else final_chart,
            data,
            columns,
            column_types,
        )

        # 生成推荐原因
        reason = self._generate_reason(final_chart, column_types, intent_type)

        # 生成备选图表
        alternatives = self._get_alternatives(final_chart, column_types)

        return ChartRecommendation(
            chart_type=final_chart.chart_type.value if isinstance(final_chart, ChartTypeRecommendation) else final_chart,
            confidence=0.85,
            reason=reason,
            options=options,
            suggested_configs=self._get_suggested_configs(final_chart),
            alternatives=alternatives,
        )

    def _analyze_result_structure(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
    ) -> list[ColumnTypeInfo]:
        """
        分析结果数据结构，检测各列类型

        Args:
            data: 查询结果数据
            columns: 列名列表

        Returns:
            各列的类型分析结果列表
        """
        if not data or not columns:
            return []

        result = []

        for col in columns:
            col_info = self._analyze_column(data, col)
            result.append(col_info)

        return result

    def _analyze_column(self, data: list[dict[str, Any]], col: str) -> ColumnTypeInfo:
        """
        分析单个列的类型

        Args:
            data: 数据列表
            col: 列名

        Returns:
            列类型分析结果
        """
        values = [row.get(col) for row in data if row.get(col) is not None]
        sample_values = values[:5] if len(values) > 5 else values

        if not values:
            return ColumnTypeInfo(
                name=col,
                column_type=ColumnType.UNKNOWN,
                sample_values=[],
            )

        # 检测数值类型
        numeric_values = []
        for v in values:
            if self._is_numeric(v):
                numeric_values.append(float(v) if not isinstance(v, bool) else 0)

        # 检测时间类型
        is_time = all(self._is_time_like(v) for v in values[:min(5, len(values))])

        # 检测比率类型（0-1 之间或带 %）
        is_ratio = False
        if len(numeric_values) == len(values) and len(numeric_values) > 0:
            all_in_range = all(0 <= v <= 1 for v in numeric_values)
            any_has_percent = any("%" in str(v) for v in values[:5])
            is_ratio = all_in_range or any_has_percent

        # 检测分类类型（字符串且唯一值较少）
        unique_count = len(set(str(v) for v in values))
        is_category = unique_count <= len(values) * 0.5 and not is_time and not numeric_values

        if is_time:
            column_type = ColumnType.TIME
        elif is_ratio:
            column_type = ColumnType.RATIO
        elif len(numeric_values) > len(values) * 0.8:
            column_type = ColumnType.NUMERIC
        elif is_category or unique_count <= 15:
            column_type = ColumnType.CATEGORY
        else:
            column_type = ColumnType.CATEGORY

        # 计算数值统计
        numeric_stats = None
        if numeric_values:
            numeric_stats = {
                "min": min(numeric_values),
                "max": max(numeric_values),
                "avg": sum(numeric_values) / len(numeric_values),
                "sum": sum(numeric_values),
            }

        return ColumnTypeInfo(
            name=col,
            column_type=column_type,
            sample_values=sample_values,
            numeric_stats=numeric_stats,
        )

    def _is_numeric(self, value: Any) -> bool:
        """判断是否为数值"""
        if value is None:
            return False
        if isinstance(value, (int, float)):
            return not isinstance(value, bool)
        if isinstance(value, str):
            # 移除千分位逗号和百分号
            cleaned = value.replace(",", "").replace("%", "").strip()
            try:
                float(cleaned)
                return True
            except (ValueError, TypeError):
                return False
        return False

    def _is_time_like(self, value: Any) -> bool:
        """判断是否像时间日期"""
        if value is None:
            return False
        if isinstance(value, (datetime,)):
            return True
        if not isinstance(value, str):
            return False

        for pattern in self.DATE_PATTERNS:
            if re.match(pattern, value):
                return True

        # 尝试解析为日期
        try:
            datetime.fromisoformat(value.replace("/", "-"))
            return True
        except (ValueError, AttributeError):
            pass

        return False

    def _infer_chart_by_intent(
        self,
        intent_type: str,
        column_types: list[ColumnTypeInfo],
    ) -> ChartTypeRecommendation | None:
        """
        根据意图类型推断图表

        Args:
            intent_type: 意图类型字符串
            column_types: 列类型分析结果

        Returns:
            推荐的图表类型
        """
        intent_lower = intent_type.lower().strip()

        # 直接映射
        if intent_lower in self.INTENT_CHART_MAP:
            chart = self.INTENT_CHART_MAP[intent_lower]
            # 检查数据是否支持该图表类型
            if self._is_chart_supported(chart, column_types):
                return chart

        # 关键词模糊匹配
        for intent_key, chart in self.INTENT_CHART_MAP.items():
            if intent_key in intent_lower or intent_lower in intent_key:
                if self._is_chart_supported(chart, column_types):
                    return chart

        return None

    def _is_chart_supported(
        self,
        chart: ChartTypeRecommendation,
        column_types: list[ColumnTypeInfo],
    ) -> bool:
        """检查数据是否支持指定的图表类型"""
        numeric_cols = [c for c in column_types if c.column_type == ColumnType.NUMERIC]
        time_cols = [c for c in column_types if c.column_type == ColumnType.TIME]
        category_cols = [c for c in column_types if c.column_type == ColumnType.CATEGORY]

        if chart == ChartTypeRecommendation.LINE:
            return bool(time_cols) and bool(numeric_cols)
        elif chart == ChartTypeRecommendation.PIE:
            return bool(numeric_cols)
        elif chart == ChartTypeRecommendation.SCATTER:
            return len(numeric_cols) >= 2
        elif chart in (ChartTypeRecommendation.BAR, ChartTypeRecommendation.BAR_DESC):
            return bool(numeric_cols)
        elif chart == ChartTypeRecommendation.TABLE:
            return True

        return True

    def _infer_chart_by_data(
        self,
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> ChartTypeRecommendation:
        """
        根据数据特征推断图表类型

        Args:
            columns: 列名列表
            column_types: 列类型分析结果

        Returns:
            推断的图表类型
        """
        if not column_types:
            return ChartTypeRecommendation.TABLE

        time_cols = [c for c in column_types if c.column_type == ColumnType.TIME]
        numeric_cols = [c for c in column_types if c.column_type == ColumnType.NUMERIC]
        category_cols = [c for c in column_types if c.column_type == ColumnType.CATEGORY]
        ratio_cols = [c for c in column_types if c.column_type == ColumnType.RATIO]

        # 时间序列 + 数值 → 折线图
        if time_cols and numeric_cols:
            return ChartTypeRecommendation.LINE

        # 比率类型 → 饼图
        if ratio_cols and not numeric_cols:
            return ChartTypeRecommendation.PIE

        # 单一数值列 + 类别列 → 柱状图或饼图
        if len(numeric_cols) == 1 and category_cols:
            return ChartTypeRecommendation.BAR

        # 多列数值 → 散点图或柱状图
        if len(numeric_cols) >= 2 and len(category_cols) == 0:
            return ChartTypeRecommendation.SCATTER

        # 多列数值 + 类别 → 分组柱状图
        if len(numeric_cols) > 1 and category_cols:
            return ChartTypeRecommendation.BAR

        # 默认返回表格
        return ChartTypeRecommendation.TABLE

    def _count_categories(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> int:
        """统计类别数量"""
        category_cols = [c for c in column_types if c.column_type == ColumnType.CATEGORY]

        if not category_cols:
            return len(data)

        # 使用第一个类别列统计
        first_category = category_cols[0]
        categories = set()
        for row in data:
            val = row.get(first_category.name)
            if val is not None:
                categories.add(str(val))

        return len(categories)

    def _empty_recommendation(self, reason: str) -> ChartRecommendation:
        """空数据推荐"""
        return ChartRecommendation(
            chart_type="table",
            confidence=0.0,
            reason=f"无法生成图表：{reason}",
            options={"type": "table", "data": [], "columns": []},
            suggested_configs={"legend": False},
            alternatives=[],
        )

    def _single_row_recommendation(
        self,
        row: dict[str, Any],
        columns: list[str],
    ) -> ChartRecommendation:
        """单行数据推荐"""
        numeric_cols = [c for c in columns if self._is_numeric(row.get(c))]
        numeric_stats = None

        if numeric_cols:
            values = [float(row.get(c)) for c in numeric_cols if self._is_numeric(row.get(c))]
            numeric_stats = {
                "min": min(values),
                "max": max(values),
                "avg": sum(values) / len(values),
                "sum": sum(values),
            }

        # 单行数据通常显示为仪表盘或统计卡片
        if numeric_stats:
            options = self._build_gauge_options(numeric_stats, numeric_cols[0] if numeric_cols else "值")
            return ChartRecommendation(
                chart_type="gauge",
                confidence=0.6,
                reason="单行数据建议使用仪表盘展示关键指标",
                options=options,
                suggested_configs={"show_value": True},
                alternatives=["table", "bar"],
            )

        return ChartRecommendation(
            chart_type="table",
            confidence=0.5,
            reason="单行数据建议使用表格展示",
            options={"type": "table", "data": [row], "columns": columns},
            suggested_configs={"sortable": False},
            alternatives=["bar"],
        )

    def _many_categories_recommendation(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
    ) -> ChartRecommendation:
        """类别过多的推荐"""
        return ChartRecommendation(
            chart_type="table",
            confidence=0.9,
            reason="类别数量超过20个，建议使用表格以便查看详细数据",
            options={"type": "table", "data": data, "columns": columns},
            suggested_configs={"sortable": True, "pageSize": 10},
            alternatives=["bar"],
        )

    def _generate_reason(
        self,
        chart: ChartTypeRecommendation,
        column_types: list[ColumnTypeInfo],
        intent_type: str,
    ) -> str:
        """生成推荐原因"""
        time_cols = [c for c in column_types if c.column_type == ColumnType.TIME]
        numeric_cols = [c for c in column_types if c.column_type == ColumnType.NUMERIC]
        category_cols = [c for c in column_types if c.column_type == ColumnType.CATEGORY]

        reasons = {
            ChartTypeRecommendation.LINE: f"检测到时间维度（{time_cols[0].name if time_cols else 'N/A'}）与数值维度，适合展示趋势变化",
            ChartTypeRecommendation.BAR: f"发现{len(category_cols)}个类别和{len(numeric_cols)}个数值指标，适合对比分析",
            ChartTypeRecommendation.BAR_DESC: f"用户关注排名，使用降序柱状图便于直观比较",
            ChartTypeRecommendation.PIE: f"检测到占比类数据，适合展示各部分占比关系",
            ChartTypeRecommendation.SCATTER: f"存在多个数值维度，适合探索变量间的相关性",
            ChartTypeRecommendation.TABLE: "数据特征适合使用表格展示详细信息",
        }

        base_reason = reasons.get(chart, "根据数据特征推荐")

        if intent_type and intent_type not in ("unknown", ""):
            return f"{base_reason}（意图：{intent_type}）"

        return base_reason

    def _get_alternatives(
        self,
        chart: ChartTypeRecommendation,
        column_types: list[ColumnTypeInfo],
    ) -> list[str]:
        """获取备选图表类型"""
        alternatives_map = {
            ChartTypeRecommendation.LINE: ["bar", "area"],
            ChartTypeRecommendation.BAR: ["line", "pie"],
            ChartTypeRecommendation.BAR_DESC: ["bar", "table"],
            ChartTypeRecommendation.PIE: ["bar", "ring"],
            ChartTypeRecommendation.SCATTER: ["line", "bar"],
            ChartTypeRecommendation.TABLE: [],
        }

        return alternatives_map.get(chart, [])

    def _get_suggested_configs(
        self,
        chart: ChartTypeRecommendation,
    ) -> dict[str, Any]:
        """获取建议的配置"""
        configs_map = {
            ChartTypeRecommendation.LINE: {
                "color": DEFAULT_COLORS,
                "legend": True,
                "tooltip": {"trigger": "axis"},
                "dataZoom": True,
                "smooth": True,
            },
            ChartTypeRecommendation.BAR: {
                "color": DEFAULT_COLORS,
                "legend": True,
                "tooltip": {"trigger": "axis"},
                "barWidth": "60%",
            },
            ChartTypeRecommendation.BAR_DESC: {
                "color": DEFAULT_COLORS[:6],  # 减少颜色数量更清晰
                "legend": False,
                "tooltip": {"trigger": "axis"},
                "sort": "descending",
            },
            ChartTypeRecommendation.PIE: {
                "color": DEFAULT_COLORS,
                "legend": True,
                "tooltip": {"trigger": "item"},
                "label": {"show": True, "formatter": "{b}: {c} ({d}%)"},
                "roseType": False,
            },
            ChartTypeRecommendation.SCATTER: {
                "color": DEFAULT_COLORS[:4],
                "legend": True,
                "tooltip": {"trigger": "item"},
                "scatterSymbolSize": 10,
            },
            ChartTypeRecommendation.TABLE: {
                "sortable": True,
                "filterable": True,
                "pageSize": 10,
                "stripe": True,
            },
        }

        return configs_map.get(chart, {"legend": True})

    def _build_chart_options(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> dict[str, Any]:
        """
        构建 ECharts 图表配置

        Args:
            chart_type: 图表类型
            data: 数据
            columns: 列名
            column_types: 列类型信息

        Returns:
            ECharts 配置字典
        """
        if chart_type == "table":
            return self._build_table_options(data, columns)

        if chart_type == "gauge":
            return self._build_gauge_options({}, columns[0] if columns else "值")

        if chart_type == "pie":
            return self._build_pie_options(data, columns, column_types)

        if chart_type == "scatter":
            return self._build_scatter_options(data, columns, column_types)

        # 默认为柱状图或折线图
        return self._build_bar_line_options(chart_type, data, columns, column_types)

    def _build_table_options(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
    ) -> dict[str, Any]:
        """构建表格配置"""
        return {
            "type": "table",
            "data": data,
            "columns": columns,
            "options": {
                "pagination": {"pageSize": 10},
                "stripe": True,
                "border": True,
                "header": {"style": {"background": "#f5f7fa", "fontWeight": "bold"}},
                "cell": {"align": "left"},
                "locale": "zh_CN",
            },
        }

    def _build_gauge_options(
        self,
        numeric_stats: dict[str, float],
        metric_name: str,
    ) -> dict[str, Any]:
        """构建仪表盘配置"""
        value = numeric_stats.get("avg", numeric_stats.get("max", 0)) if numeric_stats else 0
        max_val = numeric_stats.get("max", 100) if numeric_stats else 100

        return {
            "type": "gauge",
            "data": [{"value": value, "name": metric_name}],
            "options": {
                "series": [{
                    "type": "gauge",
                    "startAngle": 180,
                    "endAngle": 0,
                    "min": 0,
                    "max": max_val,
                    "splitNumber": 5,
                    "itemStyle": {"color": "#5470c6"},
                    "progress": {"show": True, "width": 18},
                    "pointer": {"show": True, "length": "60%", "width": 6},
                    "axisLine": {"lineStyle": {"width": 18}},
                    "axisTick": {"show": True, "distance": -20, "splitNumber": 5},
                    "splitLine": {"distance": -24, "length": 14},
                    "axisLabel": {"distance": -12, "color": "#999", "fontSize": 12},
                    "anchor": {"show": True, "size": 10, "itemStyle": {"borderWidth": 3}},
                    "detail": {
                        "valueAnimation": True,
                        "formatter": "{value}",
                        "color": "auto",
                        "fontSize": 24,
                        "offsetCenter": [0, "40%"],
                    },
                    "data": [{"value": value, "name": metric_name}],
                }],
                "color": DEFAULT_COLORS,
            },
        }

    def _build_pie_options(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> dict[str, Any]:
        """构建饼图配置"""
        category_cols = [c for c in column_types if c.column_type == ColumnType.CATEGORY]
        numeric_cols = [c for c in column_types if c.column_type in (ColumnType.NUMERIC, ColumnType.RATIO)]

        name_col = category_cols[0].name if category_cols else columns[0]
        value_col = numeric_cols[0].name if numeric_cols else columns[-1]

        pie_data = [
            {"name": str(row.get(name_col, "")), "value": self._parse_numeric(row.get(value_col))}
            for row in data
        ]

        return {
            "type": "pie",
            "data": pie_data,
            "options": {
                "title": {
                    "text": "",
                    "left": "center",
                    "top": 10,
                },
                "tooltip": {
                    "trigger": "item",
                    "formatter": "{b}: {c} ({d}%)",
                },
                "legend": {
                    "orient": "vertical",
                    "left": "left",
                    "top": "center",
                    "data": [item["name"] for item in pie_data],
                },
                "series": [{
                    "type": "pie",
                    "radius": ["40%", "70%"],
                    "center": ["50%", "55%"],
                    "avoidLabelOverlap": True,
                    "itemStyle": {
                        "borderRadius": 4,
                        "borderColor": "#fff",
                        "borderWidth": 2,
                    },
                    "label": {
                        "show": True,
                        "formatter": "{b}: {c}\n{d}%",
                        "position": "outside",
                    },
                    "emphasis": {
                        "itemStyle": {
                            "shadowBlur": 10,
                            "shadowOffsetX": 0,
                            "shadowColor": "rgba(0, 0, 0, 0.5)",
                        },
                        "label": {"show": True, "fontSize": 14, "fontWeight": "bold"},
                    },
                    "labelLine": {"show": True},
                    "data": pie_data,
                }],
                "color": DEFAULT_COLORS,
            },
        }

    def _build_scatter_options(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> dict[str, Any]:
        """构建散点图配置"""
        numeric_cols = [c for c in column_types if c.column_type == ColumnType.NUMERIC]

        if len(numeric_cols) < 2:
            # 不足两个数值列，使用柱状图
            return self._build_bar_line_options("bar", data, columns, column_types)

        x_col = numeric_cols[0].name
        y_col = numeric_cols[1].name
        size_col = numeric_cols[2].name if len(numeric_cols) > 2 else None

        scatter_data = []
        for row in data:
            x_val = self._parse_numeric(row.get(x_col))
            y_val = self._parse_numeric(row.get(y_col))
            if x_val is not None and y_val is not None:
                item = [x_val, y_val]
                if size_col:
                    item.append(self._parse_numeric(row.get(size_col)))
                scatter_data.append(item)

        series_config = {
            "type": "scatter",
            "symbolSize": 10,
            "data": scatter_data,
        }

        if size_col:
            series_config["symbolSize"] = lambda x: max(8, min(30, x[2] / 10))
            series_config["label"] = {
                "show": False,
                "formatter": lambda params: f"{params.data[0]}, {params.data[1]}",
                "position": "top",
            }

        return {
            "type": "scatter",
            "data": scatter_data,
            "options": {
                "title": {"text": "", "left": "center"},
                "tooltip": {
                    "trigger": "item",
                    "formatter": lambda params: f"{x_col}: {params.data[0]}<br/>{y_col}: {params.data[1]}",
                },
                "xAxis": {
                    "type": "value",
                    "name": x_col,
                    "scale": True,
                    "axisLabel": {"formatter": "{value}"},
                },
                "yAxis": {
                    "type": "value",
                    "name": y_col,
                    "scale": True,
                    "axisLabel": {"formatter": "{value}"},
                },
                "series": [series_config],
                "grid": {"left": "10%", "right": "10%", "bottom": "15%", "top": "60px"},
                "color": DEFAULT_COLORS[:4],
            },
        }

    def _build_bar_line_options(
        self,
        chart_type: str,
        data: list[dict[str, Any]],
        columns: list[str],
        column_types: list[ColumnTypeInfo],
    ) -> dict[str, Any]:
        """构建柱状图/折线图配置"""
        category_cols = [c for c in column_types if c.column_type in (ColumnType.CATEGORY, ColumnType.TIME)]
        numeric_cols = [c for c in column_types if c.column_type in (ColumnType.NUMERIC, ColumnType.RATIO)]

        x_col = category_cols[0].name if category_cols else columns[0]
        y_cols = [c.name for c in numeric_cols] if numeric_cols else [columns[-1] if len(columns) > 1 else columns[0]]

        # 准备 x 轴数据
        x_data = [self._format_category(row.get(x_col)) for row in data]

        # 准备系列数据
        series = []
        for i, y_col in enumerate(y_cols):
            series_data = [self._parse_numeric(row.get(y_col)) for row in data]
            series.append({
                "name": self._format_label(y_col),
                "type": "line" if chart_type == "line" else "bar",
                "data": series_data,
                "smooth": True if chart_type == "line" else False,
                "itemStyle": {"color": DEFAULT_COLORS[i % len(DEFAULT_COLORS)]},
                "emphasis": {
                    "itemStyle": {"shadowBlur": 10, "shadowColor": "rgba(0, 0, 0, 0.3)"}
                },
            })

        is_time_series = any(c.column_type == ColumnType.TIME for c in column_types)

        return {
            "type": chart_type,
            "data": [{"x": x_data, "series": series}],
            "options": {
                "title": {"text": "", "left": "center"},
                "tooltip": {
                    "trigger": "axis",
                    "axisPointer": {"type": "cross"} if chart_type == "line" else {"type": "shadow"},
                    "formatter": None,
                },
                "legend": {
                    "data": [s["name"] for s in series],
                    "top": 30,
                    "type": "scroll" if len(series) > 3 else "plain",
                },
                "grid": {
                    "left": "10%",
                    "right": "10%",
                    "bottom": "20%" if is_time_series else "15%",
                    "top": "60px" if len(series) > 1 else "50px",
                    "containLabel": True,
                },
                "xAxis": {
                    "type": "category",
                    "data": x_data,
                    "name": self._format_label(x_col),
                    "axisLabel": {
                        "rotate": 45 if len(x_data) > 8 else 0,
                        "interval": 0 if len(x_data) <= 10 else "auto",
                    },
                    "axisTick": {"alignWithLabel": True},
                },
                "yAxis": {
                    "type": "value",
                    "name": ", ".join([self._format_label(c) for c in y_cols]),
                    "axisLabel": {"formatter": self._format_number},
                },
                "series": series,
                "color": DEFAULT_COLORS,
                "animation": True,
                "animationDuration": 800,
                "animationEasing": "cubicOut",
            },
        }

    def _parse_numeric(self, value: Any) -> float | None:
        """解析数值为浮点数"""
        if value is None:
            return None
        if isinstance(value, (int, float)):
            return float(value) if not isinstance(value, bool) else None
        if isinstance(value, str):
            cleaned = value.replace(",", "").replace("%", "").strip()
            try:
                return float(cleaned)
            except (ValueError, TypeError):
                return None
        return None

    def _format_category(self, value: Any) -> str:
        """格式化类别标签"""
        if value is None:
            return ""
        if isinstance(value, datetime):
            return value.strftime("%Y-%m-%d")
        return str(value)

    def _format_label(self, label: str) -> str:
        """格式化标签（中文友好）"""
        if not label:
            return ""
        # 下划线转中文
        label = label.replace("_", " ")
        # 首字母大写
        return label

    def _format_number(self, value: float) -> str:
        """格式化数字显示"""
        if abs(value) >= 1_000_000:
            return f"{value / 1_000_000:.1f}M"
        if abs(value) >= 1_000:
            return f"{value / 1_000:.1f}K"
        if abs(value) < 1 and value != 0:
            return f"{value:.2%}"
        return f"{value:.0f}"


# 导出模块主类
__all__ = ["ChartRecommender", "ChartRecommendation", "ColumnTypeInfo", "ColumnType"]
