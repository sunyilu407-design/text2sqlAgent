"""结果解释器模块

提供 SQL 查询结果的自然语言解释功能，包括统计摘要、关键发现提取、异常检测和建议生成。
纯规则实现，不依赖 LLM。
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ResultInterpretation:
    """SQL 查询结果解释的数据类"""

    summary: str = ""  # 一句话总结
    row_count: int = 0  # 数据行数
    column_count: int = 0  # 列数
    stats: dict[str, dict[str, float | int | None]] = field(default_factory=dict)  # 统计信息
    key_findings: list[str] = field(default_factory=list)  # 关键发现
    suggestions: list[str] = field(default_factory=list)  # 建议行动
    insights: list[str] = field(default_factory=list)  # 深入洞察

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "summary": self.summary,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "stats": self.stats,
            "key_findings": self.key_findings,
            "suggestions": self.suggestions,
            "insights": self.insights,
        }


class ResultInterpreter:
    """SQL 查询结果解释器

    分析 SQL 查询结果，生成自然语言解释，包括：
    - 数据统计摘要
    - 关键发现提取
    - 异常检测
    - 可操作建议
    """

    def __init__(self) -> None:
        """初始化解释器"""
        self._numeric_threshold_std: float = 3.0  # 异常检测标准差倍数
        self._null_ratio_threshold: float = 0.3  # 空值比例警告阈值

    def interpret(
        self, data: list[dict[str, Any]], question: str, intent_type: str
    ) -> dict[str, Any]:
        """解释 SQL 查询结果

        Args:
            data: 查询结果数据列表，每项为列名到值的字典
            question: 原始问题
            intent_type: 意图类型 (e.g., "query", "analysis", "comparison")

        Returns:
            包含解释结果的字典，包含以下键：
            - summary: 一句话总结
            - row_count: 数据行数
            - column_count: 列数
            - stats: 统计信息
            - key_findings: 关键发现列表
            - suggestions: 建议行动列表
            - insights: 深入洞察列表
        """
        if not data:
            return self._empty_result()

        columns = list(data[0].keys()) if data else []

        stats = self._summarize_data(data, columns)
        key_findings = self._extract_key_findings(data, columns)
        anomalies = self._detect_anomalies(data, columns, stats)
        suggestions = self._generate_suggestions(data, intent_type)
        insights = self._generate_insights(data, columns, stats, key_findings, anomalies)

        summary = self._generate_summary(
            data=data,
            question=question,
            stats=stats,
            key_findings=key_findings,
        )

        result = ResultInterpretation(
            summary=summary,
            row_count=len(data),
            column_count=len(columns),
            stats=stats,
            key_findings=key_findings + anomalies,
            suggestions=suggestions,
            insights=insights,
        )

        return result.to_dict()

    def _empty_result(self) -> dict[str, Any]:
        """生成空数据的结果"""
        result = ResultInterpretation(
            summary="查询结果为空，请检查查询条件或数据源。",
            row_count=0,
            column_count=0,
            stats={},
            key_findings=["没有找到符合条件的数据"],
            suggestions=["请尝试扩大查询范围", "检查筛选条件是否过于严格"],
            insights=["建议确认数据源中是否存在相关记录"],
        )
        return result.to_dict()

    def _summarize_data(
        self, data: list[dict[str, Any]], columns: list[str]
    ) -> dict[str, dict[str, float | int | None]]:
        """计算数值列的统计信息

        Args:
            data: 查询结果数据
            columns: 列名列表

        Returns:
            统计信息字典，键为列名，值为统计指标字典
        """
        stats: dict[str, dict[str, float | int | None]] = {}

        for col in columns:
            values = []
            for row in data:
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)):
                    values.append(float(val))

            if not values:
                stats[col] = {
                    "count": 0,
                    "sum": None,
                    "avg": None,
                    "min": None,
                    "max": None,
                    "median": None,
                }
                continue

            stats[col] = {
                "count": len(values),
                "sum": round(sum(values), 2),
                "avg": round(sum(values) / len(values), 2),
                "min": round(min(values), 2),
                "max": round(max(values), 2),
                "median": round(self._median(values), 2),
            }

        return stats

    def _median(self, values: list[float]) -> float:
        """计算中位数"""
        if not values:
            return 0.0
        sorted_vals = sorted(values)
        n = len(sorted_vals)
        mid = n // 2
        if n % 2 == 0:
            return (sorted_vals[mid - 1] + sorted_vals[mid]) / 2
        return sorted_vals[mid]

    def _std_dev(self, values: list[float]) -> float:
        """计算标准差"""
        if len(values) < 2:
            return 0.0
        avg = sum(values) / len(values)
        variance = sum((v - avg) ** 2 for v in values) / len(values)
        return math.sqrt(variance)

    def _extract_key_findings(
        self, data: list[dict[str, Any]], columns: list[str]
    ) -> list[str]:
        """提取关键发现

        识别顶部/底部值、趋势和模式。

        Args:
            data: 查询结果数据
            columns: 列名列表

        Returns:
            关键发现列表
        """
        findings: list[str] = []

        for col in columns:
            numeric_values: list[tuple[int, float]] = []
            for i, row in enumerate(data):
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)):
                    numeric_values.append((i, float(val)))

            if not numeric_values:
                continue

            values_only = [v for _, v in numeric_values]

            # 找出最大值和最小值
            max_idx, max_val = max(numeric_values, key=lambda x: x[1])
            min_idx, min_val = min(numeric_values, key=lambda x: x[1])

            # 顶部值（Top 3）
            if len(numeric_values) >= 3:
                sorted_desc = sorted(numeric_values, key=lambda x: x[1], reverse=True)
                top_values = [v for _, v in sorted_desc[:3]]
                findings.append(
                    f"「{col}」列最高值为 {max_val}，前三名为 {top_values}"
                )

            # 底部值（Bottom 3）
            if len(numeric_values) >= 3:
                sorted_asc = sorted(numeric_values, key=lambda x: x[1])[:3]
                bottom_values = [v for _, v in sorted_asc]
                findings.append(
                    f"「{col}」列最低值为 {min_val}，后三名为 {bottom_values}"
                )

            # 范围跨度
            value_range = max_val - min_val
            findings.append(
                f"「{col}」列数值跨度为 {round(value_range, 2)}，从 {min_val} 到 {max_val}"
            )

            # 检测单调趋势（适用于有序数据）
            if len(values_only) >= 3:
                trend = self._detect_trend(values_only)
                if trend:
                    findings.append(f"「{col}」列呈现{trend}")

        return findings

    def _detect_trend(self, values: list[float]) -> str | None:
        """检测数值序列的趋势

        Args:
            values: 数值列表

        Returns:
            趋势描述，如果无明显趋势则返回 None
        """
        if len(values) < 3:
            return None

        increases = sum(1 for i in range(1, len(values)) if values[i] > values[i - 1])
        decreases = sum(1 for i in range(1, len(values)) if values[i] < values[i - 1])
        total = len(values) - 1

        increase_ratio = increases / total if total > 0 else 0
        decrease_ratio = decreases / total if total > 0 else 0

        if increase_ratio > 0.8:
            return "持续上升趋势"
        elif decrease_ratio > 0.8:
            return "持续下降趋势"
        elif increase_ratio > 0.6:
            return "总体上升趋势"
        elif decrease_ratio > 0.6:
            return "总体下降趋势"
        elif self._is_seasonal(values):
            return "存在周期性波动"
        else:
            return "波动较小，数值稳定"

    def _is_seasonal(self, values: list[float]) -> bool:
        """简单检测是否存在周期性波动"""
        if len(values) < 6:
            return False

        # 计算相邻差值的符号变化
        diffs = [values[i] - values[i - 1] for i in range(1, len(values))]
        sign_changes = sum(
            1 for i in range(1, len(diffs)) if diffs[i] * diffs[i - 1] < 0
        )

        # 如果符号变化频繁，可能存在周期性
        return sign_changes >= len(diffs) * 0.4

    def _detect_anomalies(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        stats: dict[str, dict[str, float | int | None]],
    ) -> list[str]:
        """检测数据异常

        识别超过 3 倍标准差的异常值和空值比例异常。

        Args:
            data: 查询结果数据
            columns: 列名列表
            stats: 预计算的统计信息

        Returns:
            异常描述列表
        """
        anomalies: list[str] = []

        for col in columns:
            values = []
            for row in data:
                val = row.get(col)
                if val is not None and isinstance(val, (int, float)):
                    values.append(float(val))

            if len(values) < 3:
                continue

            col_stats = stats.get(col, {})
            avg = col_stats.get("avg")
            std = self._std_dev(values)

            if avg is None or std == 0:
                continue

            threshold = self._numeric_threshold_std * std

            # 检测高于均值过多或过少的值
            high_anomalies = [v for v in values if v > avg + threshold]
            low_anomalies = [v for v in values if v < avg - threshold]

            if high_anomalies:
                anomalies.append(
                    f"「{col}」列存在 {len(high_anomalies)} 个异常高值，最大达 {max(high_anomalies)}"
                )

            if low_anomalies:
                anomalies.append(
                    f"「{col}」列存在 {len(low_anomalies)} 个异常低值，最小为 {min(low_anomalies)}"
                )

        # 检测空值比例
        for col in columns:
            total = len(data)
            null_count = sum(1 for row in data if row.get(col) is None)
            null_ratio = null_count / total if total > 0 else 0

            if null_ratio > self._null_ratio_threshold:
                anomalies.append(
                    f"「{col}」列空值比例较高 ({round(null_ratio * 100, 1)}%)，建议检查数据完整性"
                )

        return anomalies

    def _generate_suggestions(self, data: list[dict[str, Any]], intent_type: str) -> list[str]:
        """生成可操作建议

        根据数据和意图类型生成建议。

        Args:
            data: 查询结果数据
            intent_type: 意图类型

        Returns:
            建议列表
        """
        suggestions: list[str] = []
        row_count = len(data)

        # 基于行数的建议
        if row_count == 0:
            suggestions.append("请检查查询条件或确认数据源中存在相关数据")
        elif row_count > 10000:
            suggestions.append("数据量较大，建议添加时间范围或分类筛选条件")
        elif row_count < 10 and row_count > 0:
            suggestions.append("数据量较少，可考虑扩大查询范围以获得更全面的分析")

        # 基于意图类型的建议
        if intent_type == "query":
            suggestions.append("可进一步添加排序、分组条件深入分析")
        elif intent_type == "analysis":
            suggestions.append("建议结合时间维度分析数据变化趋势")
            suggestions.append("可对比不同分类维度的数据差异")
        elif intent_type == "comparison":
            suggestions.append("可添加更多对比维度进行交叉分析")
            suggestions.append("建议关注差异较大的维度进行重点分析")

        return suggestions

    def _generate_insights(
        self,
        data: list[dict[str, Any]],
        columns: list[str],
        stats: dict[str, dict[str, float | int | None]],
        key_findings: list[str],
        anomalies: list[str],
    ) -> list[str]:
        """生成深入洞察

        基于分析结果生成更深层次的洞察。

        Args:
            data: 查询结果数据
            columns: 列名列表
            stats: 统计信息
            key_findings: 关键发现
            anomalies: 异常信息

        Returns:
            洞察列表
        """
        insights: list[str] = []

        if not data:
            return insights

        # 基于数值分布的洞察
        numeric_cols = [
            col
            for col in columns
            if any(isinstance(row.get(col), (int, float)) for row in data)
        ]

        if numeric_cols:
            # 计算变异系数（CV）了解数据离散程度
            cv_values = []
            for col in numeric_cols:
                col_stats = stats.get(col, {})
                avg = col_stats.get("avg")
                if avg and avg != 0:
                    std = self._std_dev(
                        [float(row[col]) for row in data if isinstance(row.get(col), (int, float))]
                    )
                    cv = std / abs(avg)
                    cv_values.append((col, round(cv, 3)))

            if cv_values:
                # 按变异系数排序
                cv_values.sort(key=lambda x: x[1], reverse=True)
                highest_cv_col, highest_cv = cv_values[0]
                lowest_cv_col, lowest_cv = cv_values[-1]

                insights.append(
                    f"「{highest_cv_col}」列变异系数最高 ({highest_cv})，数据离散程度较大"
                )
                insights.append(
                    f"「{lowest_cv_col}」列变异系数最低 ({lowest_cv})，数据分布相对集中"
                )

        # 基于关键发现的洞察
        if "上升趋势" in str(key_findings):
            insights.append("数据显示持续增长趋势，可能存在季节性因素或长期增长动力")
        if "下降趋势" in str(key_findings):
            insights.append("数据显示下降趋势，建议关注相关影响因素的变化")

        # 基于异常的洞察
        if anomalies:
            insights.append("检测到部分数据存在异常波动，可能需要进一步调查原因")
            insights.append("建议结合业务背景判断异常数据的合理性")

        # 数据量洞察
        if len(data) > 100:
            insights.append("数据样本量充足，统计结果具有较高可信度")
        elif len(data) > 10:
            insights.append("数据样本量适中，建议关注统计结果的稳定性")

        return insights

    def _generate_summary(
        self,
        data: list[dict[str, Any]],
        question: str,
        stats: dict[str, dict[str, float | int | None]],
        key_findings: list[str],
    ) -> str:
        """生成一句话总结

        Args:
            data: 查询结果数据
            question: 原始问题
            stats: 统计信息
            key_findings: 关键发现

        Returns:
            一句话总结文本
        """
        row_count = len(data)

        if row_count == 0:
            return "查询结果为空，未找到符合条件的数据记录。"

        # 获取最重要的数值列（变异系数最低，即最稳定的列）
        numeric_stats = {
            col: s
            for col, s in stats.items()
            if s.get("count", 0) > 0 and s.get("avg") is not None
        }

        if numeric_stats:
            # 找到变异系数最低的列作为主要指标
            best_col = None
            best_cv = float("inf")

            for col, col_stats in numeric_stats.items():
                avg = col_stats.get("avg", 0)
                if avg and avg != 0:
                    values = [
                        float(row.get(col, 0))
                        for row in data
                        if isinstance(row.get(col), (int, float))
                    ]
                    std = self._std_dev(values)
                    cv = std / abs(avg)
                    if cv < best_cv:
                        best_cv = cv
                        best_col = col

            if best_col and best_col in stats:
                col_stats = stats[best_col]
                avg = col_stats.get("avg")
                total = col_stats.get("sum")

                if avg is not None:
                    summary = f"查询返回 {row_count} 条数据，「{best_col}」列平均值为 {avg}"
                    if total is not None:
                        summary += f"，总和为 {total}"
                    return summary

        return f"查询返回 {row_count} 条数据，包含 {len(data[0]) if data else 0} 个字段。"

    def _format_stats(
        self, numeric_stats: dict[str, dict[str, float | int | None]]
    ) -> str:
        """将统计信息格式化为可读的中文文本

        Args:
            numeric_stats: 数值列的统计信息

        Returns:
            格式化的统计文本
        """
        if not numeric_stats:
            return "无数值统计数据"

        lines = []
        for col, stats in numeric_stats.items():
            if stats.get("count", 0) == 0:
                continue

            line = f"「{col}」："
            line += f"共 {stats.get('count', 0)} 条记录"

            if stats.get("sum") is not None:
                line += f"，总和 {stats['sum']}"
            if stats.get("avg") is not None:
                line += f"，均值 {stats['avg']}"
            if stats.get("min") is not None:
                line += f"，最小值 {stats['min']}"
            if stats.get("max") is not None:
                line += f"，最大值 {stats['max']}"

            lines.append(line)

        return "\n".join(lines) if lines else "无有效统计数据"
