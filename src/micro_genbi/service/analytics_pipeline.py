"""AnalyticsPipeline - Complete analysis pipeline

Query → Analyze → Forecast → Visualize → Respond

This module provides a comprehensive analytics pipeline that combines:
- SQL query execution via AskService
- Parallel LLM-based analysis (interpretation + comparison)
- Time series forecasting with statistical methods
- ECharts visualization generation
"""

from __future__ import annotations

import asyncio
import re
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Optional

from micro_genbi import get_logger, track_duration
from micro_genbi.chart import ChartEngine
from micro_genbi.errors import GenBIError
from micro_genbi.llm.base import LLMClient, LLMResponse
from micro_genbi.prediction import StatisticsPredictor
from micro_genbi.service.result_interpreter import ResultInterpreter

if TYPE_CHECKING:
    from micro_genbi.service.ask_service import AskService

logger = get_logger(__name__)


# =============================================================================
# Data Classes
# =============================================================================

@dataclass
class QueryInfo:
    """Query execution result information"""
    sql: str
    row_count: int
    elapsed_ms: float
    data: list[dict[str, Any]]


@dataclass
class AnalysisInfo:
    """LLM analysis result information"""
    conclusion: str
    findings: list[str]
    confidence: float
    suggestions: list[str]


@dataclass
class ForecastInfo:
    """Time series forecast result information"""
    model: str
    values: list[dict[str, Any]]
    interpretation: str


@dataclass
class StepDetail:
    """Details of a single pipeline step execution"""
    step: str
    duration_ms: float
    status: str  # success/failed/skipped
    error: str = ""


@dataclass
class PipelineMetadata:
    """Pipeline execution metadata"""
    steps_taken: list[str]
    step_details: list[StepDetail]
    total_duration_ms: float


@dataclass
class PipelineResult:
    """Complete analytics pipeline result"""
    query: QueryInfo
    analysis: AnalysisInfo
    forecast: ForecastInfo
    chart: dict[str, Any]
    metadata: PipelineMetadata


# =============================================================================
# LLM Analysis Service
# =============================================================================

class LLMAnalysisService:
    """LLM-powered analysis service for parallel interpretation and comparison.

    Provides two main analysis capabilities:
    - Interpretation: Explain what the data means
    - Comparison: Compare values and identify patterns
    """

    SYSTEM_PROMPT_INTERPRET = """你是一个数据分析专家。请分析查询结果数据，回答用户的问题。
请用简洁的中文总结关键发现，避免重复信息。"""

    SYSTEM_PROMPT_COMPARE = """你是一个数据分析专家。请对比分析数据中的数值，找出：
1. 最高和最低的值
2. 显著的差异或变化
3. 值得注意的模式

请用简洁的中文列表输出关键对比发现。"""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def interpret(
        self,
        data: list[dict[str, Any]],
        question: str,
    ) -> dict[str, Any]:
        """Interpret the query results to answer the user's question.

        Args:
            data: Query result data
            question: Original user question

        Returns:
            Dict containing interpretation results
        """
        if not data:
            return {
                "conclusion": "查询结果为空",
                "confidence": 0.0,
            }

        data_summary = self._summarize_data(data)
        prompt = f"""用户问题: {question}

查询结果（共 {len(data)} 行）:
{data_summary}

请解释这些数据说明了什么？"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=self.SYSTEM_PROMPT_INTERPRET,
                max_tokens=500,
            )
            return {
                "conclusion": response.content.strip(),
                "confidence": 0.8,
            }
        except Exception as e:
            logger.warning(f"LLM interpretation failed: {e}")
            return {
                "conclusion": self._generate_fallback_conclusion(data),
                "confidence": 0.5,
            }

    async def compare(
        self,
        data: list[dict[str, Any]],
        question: str,
    ) -> dict[str, Any]:
        """Compare values in the query results.

        Args:
            data: Query result data
            question: Original user question

        Returns:
            Dict containing comparison findings
        """
        if not data or len(data) < 2:
            return {
                "findings": [],
                "confidence": 0.0,
            }

        prompt = f"""用户问题: {question}

查询结果（共 {len(data)} 行）:
{self._summarize_data(data)}

请对比分析这些数据，找出关键差异和模式。"""

        try:
            response = await self.llm_client.generate(
                prompt=prompt,
                system=self.SYSTEM_PROMPT_COMPARE,
                max_tokens=500,
            )
            findings = [
                f.strip()
                for f in response.content.split("\n")
                if f.strip() and not f.strip().startswith("#")
            ]
            return {
                "findings": findings,
                "confidence": 0.8,
            }
        except Exception as e:
            logger.warning(f"LLM comparison failed: {e}")
            return {
                "findings": self._generate_fallback_findings(data),
                "confidence": 0.5,
            }

    def _summarize_data(self, data: list[dict[str, Any]], max_rows: int = 10) -> str:
        """Generate a compact text summary of the data."""
        if not data:
            return "无数据"

        summary_parts = []
        sample_size = min(len(data), max_rows)

        for i, row in enumerate(data[:sample_size]):
            row_str = ", ".join(
                f"{k}={v}" for k, v in row.items() if v is not None
            )
            summary_parts.append(f"  [{i + 1}] {row_str}")

        if len(data) > sample_size:
            summary_parts.append(f"  ... (共 {len(data)} 行)")

        return "\n".join(summary_parts)

    def _generate_fallback_conclusion(self, data: list[dict[str, Any]]) -> str:
        """Generate a basic conclusion without LLM."""
        if not data:
            return "查询结果为空"

        row_count = len(data)
        cols = list(data[0].keys())

        numeric_cols = [
            c for c in cols
            if any(isinstance(row.get(c), (int, float)) for row in data)
        ]

        if numeric_cols:
            col = numeric_cols[0]
            values = [float(row.get(col, 0)) for row in data if row.get(col) is not None]
            if values:
                avg = sum(values) / len(values)
                return f"查询返回 {row_count} 行数据，'{col}' 列平均值为 {avg:.2f}"

        return f"查询返回 {row_count} 行数据，包含 {len(cols)} 个字段"

    def _generate_fallback_findings(self, data: list[dict[str, Any]]) -> list[str]:
        """Generate basic findings without LLM."""
        findings = []

        if not data or len(data) < 2:
            return findings

        cols = list(data[0].keys())
        numeric_cols = [
            c for c in cols
            if any(isinstance(row.get(c), (int, float)) for row in data)
        ]

        for col in numeric_cols[:3]:
            values = [float(row.get(col, 0)) for row in data if row.get(col) is not None]
            if len(values) >= 2:
                max_val = max(values)
                min_val = min(values)
                findings.append(
                    f"'{col}' 列：最大值 {max_val:.2f}，最小值 {min_val:.2f}，"
                    f"差值 {max_val - min_val:.2f}"
                )

        return findings


# =============================================================================
# Prediction Service
# =============================================================================

class PredictionService:
    """Time series forecasting service using statistical methods.

    Wraps the StatisticsPredictor for pipeline integration.
    """

    def __init__(self):
        self.predictor = StatisticsPredictor()

    def forecast(
        self,
        data: list[dict[str, Any]],
        time_col: str,
        value_col: str,
        periods: int = 3,
    ) -> ForecastInfo:
        """Generate time series forecast.

        Args:
            data: Historical time series data
            time_col: Name of the time/date column
            value_col: Name of the value column to forecast
            periods: Number of future periods to predict

        Returns:
            ForecastInfo with predicted values and interpretation
        """
        try:
            result = self.predictor.forecast(
                data=data,
                time_col=time_col,
                value_col=value_col,
                periods=periods,
            )

            values = [
                {
                    "date": fp.date,
                    "value": fp.value,
                    "lower_bound": fp.lower_bound,
                    "upper_bound": fp.upper_bound,
                }
                for fp in result.forecast_values
            ]

            return ForecastInfo(
                model="StatisticsPredictor (Exponential Smoothing)",
                values=values,
                interpretation=result.interpretation,
            )
        except Exception as e:
            logger.warning(f"Forecasting failed: {e}")
            return ForecastInfo(
                model="StatisticsPredictor",
                values=[],
                interpretation=f"预测失败: {str(e)}",
            )

    def detect_time_columns(self, data: list[dict[str, Any]]) -> tuple[str | None, str | None]:
        """Detect appropriate time and value columns for forecasting.

        Args:
            data: Query result data

        Returns:
            Tuple of (time_col, value_col) or (None, None)
        """
        if not data:
            return None, None

        cols = list(data[0].keys())

        # Find date-like column
        date_patterns = [
            r"\d{4}-\d{2}-\d{2}",
            r"\d{4}/\d{2}/\d{2}",
            r"^\d{4}-\d{2}$",
            r"年", r"月", r"日",
        ]

        time_col = None
        for col in cols:
            sample = data[0].get(col)
            if sample and isinstance(sample, str):
                for pattern in date_patterns:
                    if re.search(pattern, str(sample)):
                        time_col = col
                        break
            if time_col:
                break

        # Find numeric column for value
        value_col = None
        for col in cols:
            if col == time_col:
                continue
            if any(isinstance(row.get(col), (int, float)) for row in data):
                value_col = col
                break

        return time_col, value_col


# =============================================================================
# Analytics Pipeline
# =============================================================================

class AnalyticsPipeline:
    """Complete analytics pipeline: query → analyze → forecast → visualize → respond

    Orchestrates the full workflow:
    1. Execute query via AskService
    2. Run parallel LLM analysis (interpretation + comparison)
    3. Generate time series forecast if needed
    4. Create ECharts visualization
    5. Assemble final response

    Example:
        pipeline = AnalyticsPipeline(ask_service=service)
        result = await pipeline.run(
            question="本月销售趋势如何？",
            enable_forecast=True,
            enable_analysis=True,
            enable_chart=True,
        )
    """

    # Keywords that suggest forecasting intent
    FORECAST_KEYWORDS = [
        "预测", "forecast", "预测", "未来", "下个月", "下季度", "趋势",
        "预计", "预期", "展望", "增长预测", "销售额预测", "forecast",
        "下一年", "预测值", "预计增长", "预测销售",
    ]

    def __init__(
        self,
        ask_service: AskService,
        llm_analysis: Optional[LLMAnalysisService] = None,
        prediction_service: Optional[PredictionService] = None,
    ):
        """Initialize the analytics pipeline.

        Args:
            ask_service: AskService instance for SQL query execution
            llm_analysis: Optional LLMAnalysisService for enhanced analysis.
                        If None, uses ResultInterpreter for rule-based analysis.
            prediction_service: Optional PredictionService for time series
                              forecasting. If None, creates default instance.
        """
        self.ask_service = ask_service
        self.llm_analysis = llm_analysis
        self.prediction_service = prediction_service or PredictionService()
        self.result_interpreter = ResultInterpreter()
        self.chart_engine = ChartEngine()

    async def run(
        self,
        question: str,
        enable_forecast: bool = False,
        enable_analysis: bool = True,
        enable_chart: bool = True,
    ) -> PipelineResult:
        """Execute the complete analytics pipeline.

        Args:
            question: Natural language question
            enable_forecast: Enable time series forecasting
            enable_analysis: Enable LLM analysis
            enable_chart: Enable chart generation

        Returns:
            PipelineResult containing all results and metadata
        """
        start_time = time.time()
        step_details: list[StepDetail] = []
        steps_taken: list[str] = []

        query_info: Optional[QueryInfo] = None
        analysis_info: Optional[AnalysisInfo] = None
        forecast_info: Optional[ForecastInfo] = None
        chart_options: dict[str, Any] = {}

        # ========== Step 1: Execute Query ==========
        step_name = "query_execution"
        steps_taken.append(step_name)

        with track_duration(step_name) as timer:
            try:
                response = await self.ask_service.ask(question)
                query_info = QueryInfo(
                    sql=response.sql,
                    row_count=response.row_count,
                    elapsed_ms=float(response.execution_time_ms),
                    data=response.data or [],
                )
                step_details.append(StepDetail(
                    step=step_name,
                    duration_ms=int(timer.elapsed * 1000),
                    status="success",
                ))
            except Exception as e:
                logger.error(f"Query execution failed: {e}")
                step_details.append(StepDetail(
                    step=step_name,
                    duration_ms=int(timer.elapsed * 1000),
                    status="failed",
                    error=str(e),
                ))
                # Return partial result with error info
                return self._build_error_result(
                    question=str(e),
                    steps_taken=steps_taken,
                    step_details=step_details,
                    total_duration_ms=int((time.time() - start_time) * 1000),
                )

        # ========== Step 2: Parallel Analysis ==========
        if enable_analysis:
            step_name = "llm_analysis"
            steps_taken.append(step_name)

            with track_duration(step_name) as timer:
                try:
                    analysis_info = await self._run_parallel_analysis(
                        query_info.data,
                        question,
                    )
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="success",
                    ))
                except Exception as e:
                    logger.warning(f"Analysis failed: {e}")
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="failed",
                        error=str(e),
                    ))
                    # Use fallback analysis
                    analysis_info = self._create_fallback_analysis(query_info.data, question)
        else:
            steps_taken.append("analysis_skipped")
            step_details.append(StepDetail(
                step="analysis_skipped",
                duration_ms=0,
                status="skipped",
            ))
            analysis_info = AnalysisInfo(
                conclusion="分析已禁用",
                findings=[],
                confidence=0.0,
                suggestions=[],
            )

        # ========== Step 3: Forecasting ==========
        if enable_forecast and self._detect_intent_for_forecast(question):
            step_name = "forecasting"
            steps_taken.append(step_name)

            with track_duration(step_name) as timer:
                try:
                    forecast_info = await self._run_forecast(query_info.data)
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="success",
                    ))
                except Exception as e:
                    logger.warning(f"Forecasting failed: {e}")
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="failed",
                        error=str(e),
                    ))
                    forecast_info = ForecastInfo(
                        model="StatisticsPredictor",
                        values=[],
                        interpretation=f"预测失败: {str(e)}",
                    )
        else:
            steps_taken.append("forecast_skipped")
            step_details.append(StepDetail(
                step="forecast_skipped",
                duration_ms=0,
                status="skipped",
            ))
            forecast_info = ForecastInfo(
                model="",
                values=[],
                interpretation="未启用预测或无时间序列数据",
            )

        # ========== Step 4: Chart Generation ==========
        if enable_chart:
            step_name = "chart_generation"
            steps_taken.append(step_name)

            with track_duration(step_name) as timer:
                try:
                    chart_options = self.chart_engine.generate(
                        data=query_info.data,
                        intent=question,
                    ) or {}
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="success",
                    ))
                except Exception as e:
                    logger.warning(f"Chart generation failed: {e}")
                    step_details.append(StepDetail(
                        step=step_name,
                        duration_ms=int(timer.elapsed * 1000),
                        status="failed",
                        error=str(e),
                    ))
                    chart_options = {}
        else:
            steps_taken.append("chart_skipped")
            step_details.append(StepDetail(
                step="chart_skipped",
                duration_ms=0,
                status="skipped",
            ))
            chart_options = {}

        # ========== Assemble Result ==========
        total_duration_ms = int((time.time() - start_time) * 1000)

        return PipelineResult(
            query=query_info,
            analysis=analysis_info,
            forecast=forecast_info,
            chart=chart_options,
            metadata=PipelineMetadata(
                steps_taken=steps_taken,
                step_details=step_details,
                total_duration_ms=total_duration_ms,
            ),
        )

    def _detect_intent_for_forecast(self, question: str) -> bool:
        """Detect if the question asks about future/prediction.

        Args:
            question: User's natural language question

        Returns:
            True if forecasting is suggested by the question
        """
        question_lower = question.lower()

        for keyword in self.FORECAST_KEYWORDS:
            if keyword.lower() in question_lower:
                return True

        return False

    async def _run_parallel_analysis(
        self,
        data: list[dict[str, Any]],
        question: str,
    ) -> AnalysisInfo:
        """Run interpretation and comparison in parallel.

        Args:
            data: Query result data
            question: Original user question

        Returns:
            AnalysisInfo with combined results
        """
        if self.llm_analysis is None:
            # Use rule-based interpreter as fallback
            return self._create_fallback_analysis(data, question)

        # Run both analyses concurrently
        interpret_task = self.llm_analysis.interpret(data, question)
        compare_task = self.llm_analysis.compare(data, question)

        interpret_result, compare_result = await asyncio.gather(
            interpret_task,
            compare_task,
            return_exceptions=True,
        )

        # Handle potential errors
        if isinstance(interpret_result, Exception):
            logger.warning(f"Interpretation failed: {interpret_result}")
            interpret_result = {
                "conclusion": "解释生成失败",
                "confidence": 0.0,
            }

        if isinstance(compare_result, Exception):
            logger.warning(f"Comparison failed: {compare_result}")
            compare_result = {
                "findings": [],
                "confidence": 0.0,
            }

        # Combine results
        findings = compare_result.get("findings", [])
        if not findings and data:
            # Add rule-based findings as backup
            rule_findings = self._extract_rule_based_findings(data)
            findings.extend(rule_findings)

        suggestions = self._generate_suggestions(data, question)

        return AnalysisInfo(
            conclusion=interpret_result.get("conclusion", ""),
            findings=findings,
            confidence=(
                interpret_result.get("confidence", 0.0)
                + compare_result.get("confidence", 0.0)
            ) / 2,
            suggestions=suggestions,
        )

    def _run_forecast(self, data: list[dict[str, Any]]) -> ForecastInfo:
        """Run time series forecasting on the data.

        Args:
            data: Query result data

        Returns:
            ForecastInfo with predicted values
        """
        time_col, value_col = self.prediction_service.detect_time_columns(data)

        if time_col is None or value_col is None:
            return ForecastInfo(
                model="StatisticsPredictor",
                values=[],
                interpretation="未检测到时间序列列，无法进行预测",
            )

        return self.prediction_service.forecast(
            data=data,
            time_col=time_col,
            value_col=value_col,
            periods=3,
        )

    def _create_fallback_analysis(
        self,
        data: list[dict[str, Any]],
        question: str,
    ) -> AnalysisInfo:
        """Create analysis using rule-based interpreter.

        Args:
            data: Query result data
            question: Original user question

        Returns:
            AnalysisInfo with rule-based analysis
        """
        interpretation = self.result_interpreter.interpret(
            data=data,
            question=question,
            intent_type="analysis",
        )

        suggestions = interpretation.get("suggestions", [])
        if not suggestions:
            suggestions = self._generate_suggestions(data, question)

        return AnalysisInfo(
            conclusion=interpretation.get("summary", ""),
            findings=interpretation.get("key_findings", []),
            confidence=0.6,
            suggestions=suggestions,
        )

    def _extract_rule_based_findings(self, data: list[dict[str, Any]]) -> list[str]:
        """Extract basic findings using rules.

        Args:
            data: Query result data

        Returns:
            List of finding strings
        """
        findings = []

        if not data or len(data) < 2:
            return findings

        cols = list(data[0].keys())
        numeric_cols = [
            c for c in cols
            if any(isinstance(row.get(c), (int, float)) for row in data)
        ]

        for col in numeric_cols[:3]:
            values = [float(row.get(col, 0)) for row in data if row.get(col) is not None]
            if len(values) >= 2:
                max_val = max(values)
                min_val = min(values)
                max_idx = values.index(max_val)
                min_idx = values.index(min_val)

                findings.append(
                    f"'{col}' 列最大值 {max_val:.2f}（第 {max_idx + 1} 行），"
                    f"最小值 {min_val:.2f}（第 {min_idx + 1} 行）"
                )

        return findings

    def _generate_suggestions(self, data: list[dict[str, Any]], question: str) -> list[str]:
        """Generate actionable suggestions based on data.

        Args:
            data: Query result data
            question: Original user question

        Returns:
            List of suggestion strings
        """
        suggestions = []

        row_count = len(data)

        if row_count == 0:
            suggestions.append("请检查查询条件或确认数据源中存在相关数据")
        elif row_count > 100:
            suggestions.append("数据量较大，可考虑添加时间范围或分类筛选条件")
        elif row_count < 10 and row_count > 0:
            suggestions.append("数据量较少，可考虑扩大查询范围")

        # Forecasting suggestion
        if self._detect_intent_for_forecast(question):
            suggestions.append("可启用预测功能查看未来趋势")

        # Chart suggestion
        if row_count > 1:
            suggestions.append("建议查看图表可视化以更好地理解数据模式")

        return suggestions

    def _build_error_result(
        self,
        question: str,
        steps_taken: list[str],
        step_details: list[StepDetail],
        total_duration_ms: int,
    ) -> PipelineResult:
        """Build a partial result when query execution fails.

        Args:
            question: Original question (for context)
            steps_taken: Steps that were attempted
            step_details: Details of each step
            total_duration_ms: Total execution time

        Returns:
            PipelineResult with error state
        """
        return PipelineResult(
            query=QueryInfo(
                sql="",
                row_count=0,
                elapsed_ms=0.0,
                data=[],
            ),
            analysis=AnalysisInfo(
                conclusion=f"查询失败: {steps_taken[-1] if steps_taken else 'unknown'}",
                findings=[],
                confidence=0.0,
                suggestions=["请检查数据库连接和查询语句"],
            ),
            forecast=ForecastInfo(
                model="",
                values=[],
                interpretation="未执行预测",
            ),
            chart={},
            metadata=PipelineMetadata(
                steps_taken=steps_taken,
                step_details=step_details,
                total_duration_ms=total_duration_ms,
            ),
        )

    async def close(self) -> None:
        """Close the pipeline and release resources."""
        if self.ask_service:
            await self.ask_service.close()
