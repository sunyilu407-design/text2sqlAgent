"""LLM 分析服务模块

提供基于 LLM 的深度数据分析功能，包括结果解读、对比分析、
异常检测、预测解读和 SQL 解释。
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Optional

from micro_genbi.llm.base import LLMClient

logger = logging.getLogger(__name__)


@dataclass
class AnalysisResult:
    """LLM 分析结果数据类"""

    type: str = ""  # 分析类型
    conclusion: str = ""  # 分析结论
    findings: list[str] = field(default_factory=list)  # 发现列表
    confidence: float = 0.0  # 置信度 0.0-1.0
    suggestions: list[str] = field(default_factory=list)  # 建议列表
    raw_response: str = ""  # 原始 LLM 输出
    error: str = ""  # 错误信息

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "type": self.type,
            "conclusion": self.conclusion,
            "findings": self.findings,
            "confidence": self.confidence,
            "suggestions": self.suggestions,
            "raw_response": self.raw_response,
            "error": self.error,
        }


# =============================================================================
# 分析提示词定义
# =============================================================================

_ANALYSIS_PROMPTS: dict[str, dict[str, str]] = {
    "interpret": {
        "system": "你是一个专业的数据分析师。你的任务是对查询结果进行深入分析，"
                  "提取关键洞察，用简洁的中文总结数据背后的业务含义。"
                  "始终返回结构化的 JSON 格式结果。",
        "user_template": "问题：{question}\n\n数据摘要：\n{data_summary}\n\n"
                        "请分析这些数据，提取关键发现，并给出可操作的建议。"
                        "返回 JSON 格式：{{\"conclusion\": \"...\", \"findings\": [\"...\"], "
                        "\"confidence\": 0.0-1.0, \"suggestions\": [\"...\"]}}",
    },
    "compare": {
        "system": "你是一个专业的数据分析师，擅长对比分析。你的任务是比较两个数据集的差异，"
                  "找出关键区别点，并用简洁的中文总结对比结论。"
                  "始终返回结构化的 JSON 格式结果。",
        "user_template": "对比分析任务：{question}\n\n"
                        "数据集1摘要：\n{data1_summary}\n\n"
                        "数据集2摘要：\n{data2_summary}\n\n"
                        "请对比分析这两个数据集，找出主要差异和共同点。"
                        "返回 JSON 格式：{{\"conclusion\": \"...\", \"findings\": [\"...\"], "
                        "\"confidence\": 0.0-1.0, \"suggestions\": [\"...\"]}}",
    },
    "anomaly": {
        "system": "你是一个专业的数据分析师，擅长异常检测和解释。"
                  "你的任务是识别数据中的异常点，并解释可能的原因。"
                  "始终返回结构化的 JSON 格式结果。",
        "user_template": "异常检测任务：{question}\n\n"
                        "数据摘要：\n{data_summary}\n\n"
                        "请识别数据中的异常值，并解释可能的业务原因。"
                        "返回 JSON 格式：{{\"conclusion\": \"...\", \"findings\": [\"...\"], "
                        "\"confidence\": 0.0-1.0, \"suggestions\": [\"...\"]}}",
    },
    "forecast_reasoning": {
        "system": "你是一个专业的数据分析师，擅长预测模型解读。"
                  "你的任务是解释预测结果，帮助用户理解决策依据。"
                  "始终返回结构化的 JSON 格式结果。",
        "user_template": "预测解读任务：{question}\n\n"
                        "预测数据摘要：\n{forecast_summary}\n\n"
                        "请解释预测结果，包括主要驱动因素和不确定性。"
                        "返回 JSON 格式：{{\"conclusion\": \"...\", \"findings\": [\"...\"], "
                        "\"confidence\": 0.0-1.0, \"suggestions\": [\"...\"]}}",
    },
    "sql_explain": {
        "system": "你是一个专业的 SQL 专家，擅长解释 SQL 查询逻辑。"
                  "你的任务是用通俗易懂的语言解释 SQL 语句的功能和数据处理逻辑。"
                  "始终返回结构化的 JSON 格式结果。",
        "user_template": "SQL 解释任务：{question}\n\n"
                        "SQL 语句：\n{sql}\n\n"
                        "请用通俗易懂的语言解释这个 SQL 查询的功能和处理逻辑。"
                        "返回 JSON 格式：{{\"conclusion\": \"...\", \"findings\": [\"...\"], "
                        "\"confidence\": 0.0-1.0, \"suggestions\": [\"...\"]}}",
    },
}


class LLMAnalysisService:
    """LLM 驱动的深度分析服务

    提供多种分析类型的 LLM 分析能力，包括：
    - interpret: 结果解读分析
    - compare: 两个数据集对比分析
    - anomaly: 异常检测与解释
    - forecast_reasoning: 预测结果解读
    - sql_explain: SQL 语句解释
    """

    def __init__(self, llm_client: Optional[LLMClient] = None) -> None:
        """初始化分析服务

        Args:
            llm_client: LLM 客户端实例。如果为 None，则无法执行 LLM 分析，
                       将在调用时返回错误。
        """
        self._llm_client = llm_client

    def _summarize_result(self, data: list[dict[str, Any]], max_tokens: int = 500) -> str:
        """压缩结果以避免 token 爆炸

        将查询结果压缩为摘要文本，限制总字符数。

        Args:
            data: 查询结果数据列表
            max_tokens: 最大字符数限制，默认 500

        Returns:
            压缩后的数据摘要字符串
        """
        if not data:
            return "（空数据）"

        # 计算数据基本信息
        row_count = len(data)
        columns = list(data[0].keys()) if data else []
        col_count = len(columns)

        # 构建摘要头部
        summary_parts = [f"共 {row_count} 行，{col_count} 列"]

        # 添加每列的统计信息
        column_summaries = []
        for col in columns[:10]:  # 最多处理 10 列避免过长
            values = [row.get(col) for row in data if row.get(col) is not None]

            if not values:
                column_summaries.append(f"{col}: 无数据")
                continue

            # 根据数据类型生成摘要
            if all(isinstance(v, (int, float)) for v in values):
                numeric_values = [float(v) for v in values]
                col_summary = (
                    f"{col}: 均值={sum(numeric_values)/len(numeric_values):.2f}, "
                    f"最小={min(numeric_values):.2f}, 最大={max(numeric_values):.2f}"
                )
            elif all(isinstance(v, str) for v in values):
                unique_count = len(set(values))
                top_values = list(set(values))[:5]
                col_summary = (
                    f"{col}: {unique_count} 个不同值，示例: {', '.join(str(v) for v in top_values[:3])}"
                )
            else:
                col_summary = f"{col}: {len(values)} 个值"

            column_summaries.append(col_summary)

        # 组合完整摘要
        full_summary = "; ".join(summary_parts + column_summaries)

        # 截断超过限制的部分
        if len(full_summary) > max_tokens:
            return full_summary[: max_tokens - 3] + "..."

        return full_summary

    def _build_prompt(
        self, analysis_type: str, question: str, data_summary: str, **kwargs: Any
    ) -> tuple[str, str]:
        """根据分析类型生成提示词

        Args:
            analysis_type: 分析类型
            question: 原始问题
            data_summary: 数据摘要
            **kwargs: 额外参数（如 compare 需要 data2_summary，sql_explain 需要 sql）

        Returns:
            (system_prompt, user_prompt) 元组
        """
        prompt_config = _ANALYSIS_PROMPTS.get(analysis_type)
        if not prompt_config:
            raise ValueError(f"不支持的分析类型: {analysis_type}")

        system_prompt = prompt_config["system"]
        user_template = prompt_config["user_template"]

        # 填充模板变量
        user_vars: dict[str, str] = {
            "question": question,
            "data_summary": data_summary,
        }

        # 添加类型特定的变量
        if analysis_type == "compare":
            user_vars["data1_summary"] = data_summary
            user_vars["data2_summary"] = kwargs.get("data2_summary", "（无数据）")
        elif analysis_type == "sql_explain":
            user_vars["sql"] = data_summary  # 在 sql_explain 场景下 data_summary 实际是 SQL
        elif analysis_type == "forecast_reasoning":
            user_vars["forecast_summary"] = data_summary

        user_prompt = user_template.format(**user_vars)

        return system_prompt, user_prompt

    def _parse_response(self, analysis_type: str, response: str) -> dict[str, Any]:
        """解析 LLM 响应

        从 LLM 返回的原始文本中提取结构化数据。

        Args:
            analysis_type: 分析类型
            response: LLM 原始响应文本

        Returns:
            解析后的结构化数据字典
        """
        result: dict[str, Any] = {
            "conclusion": "",
            "findings": [],
            "confidence": 0.5,
            "suggestions": [],
        }

        try:
            # 尝试提取 JSON 块
            json_str = self._extract_json(response)
            if json_str:
                parsed = json.loads(json_str)
                result["conclusion"] = str(parsed.get("conclusion", ""))
                result["findings"] = parsed.get("findings", [])
                result["confidence"] = float(parsed.get("confidence", 0.5))
                result["suggestions"] = parsed.get("suggestions", [])

                # 确保类型正确
                if not isinstance(result["findings"], list):
                    result["findings"] = [str(result["findings"])]
                if not isinstance(result["suggestions"], list):
                    result["suggestions"] = [str(result["suggestions"])]

                # 限制置信度范围
                result["confidence"] = max(0.0, min(1.0, result["confidence"]))
            else:
                # 如果无法解析 JSON，将整个响应作为结论
                result["conclusion"] = response.strip()
                result["confidence"] = 0.4
        except json.JSONDecodeError:
            # JSON 解析失败，尝试提取关键段落
            result["conclusion"] = response.strip()
            result["confidence"] = 0.3
        except Exception as e:
            logger.warning(f"解析 LLM 响应失败: {e}")
            result["conclusion"] = response.strip()
            result["confidence"] = 0.3

        return result

    def _extract_json(self, text: str) -> str | None:
        """从文本中提取 JSON 字符串

        支持从 markdown 代码块或纯文本中提取 JSON。

        Args:
            text: 原始文本

        Returns:
            提取的 JSON 字符串，如果未找到则返回 None
        """
        import re

        # 尝试从 ```json ... ``` 块中提取
        json_block_match = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
        if json_block_match:
            return json_block_match.group(1)

        # 尝试从纯 JSON 中提取（查找第一个 { 到最后一个 }）
        first_brace = text.find("{")
        last_brace = text.rfind("}")
        if first_brace != -1 and last_brace > first_brace:
            return text[first_brace : last_brace + 1]

        return None

    def analyze(
        self, data: list[dict[str, Any]], question: str, analysis_type: str
    ) -> dict[str, Any]:
        """执行 LLM 分析

        根据分析类型执行相应的 LLM 分析。

        Args:
            data: 查询结果数据列表
            question: 原始问题
            analysis_type: 分析类型 (interpret, compare, anomaly,
                          forecast_reasoning, sql_explain)

        Returns:
            分析结果字典，包含:
            - type: 分析类型
            - conclusion: 结论
            - findings: 发现列表
            - confidence: 置信度
            - suggestions: 建议列表
            - raw_response: 原始 LLM 输出
            - error: 错误信息（如果有）
        """
        # 验证分析类型
        if analysis_type not in _ANALYSIS_PROMPTS:
            return AnalysisResult(
                type=analysis_type,
                error=f"不支持的分析类型: {analysis_type}",
            ).to_dict()

        # 检查 LLM 客户端
        if self._llm_client is None:
            return AnalysisResult(
                type=analysis_type,
                error="LLM 客户端未初始化，请提供 llm_client 参数",
            ).to_dict()

        try:
            # 根据分析类型调用对应方法
            if analysis_type == "interpret":
                result = self.interpret(data, question)
            elif analysis_type == "anomaly":
                result = self.analyze_anomalies(data, question)
            else:
                # 其他类型使用通用分析
                result = self._generic_analyze(data, question, analysis_type)

            return result
        except Exception as e:
            logger.error(f"LLM 分析失败: {e}")
            return AnalysisResult(
                type=analysis_type,
                error=f"分析执行失败: {str(e)}",
            ).to_dict()

    def _generic_analyze(
        self, data: list[dict[str, Any]], question: str, analysis_type: str, **kwargs: Any
    ) -> dict[str, Any]:
        """通用 LLM 分析

        通用的 LLM 分析入口，用于 compare, forecast_reasoning, sql_explain 等类型。

        Args:
            data: 数据列表
            question: 问题
            analysis_type: 分析类型
            **kwargs: 额外参数

        Returns:
            分析结果字典
        """
        data_summary = self._summarize_result(data)

        # 根据类型准备数据摘要
        if analysis_type == "compare":
            data_summary = kwargs.get("data1_summary", data_summary)
            data2_summary = kwargs.get("data2_summary", "（无数据）")
            system_prompt, user_prompt = self._build_prompt(
                analysis_type, question, data_summary, data2_summary=data2_summary
            )
        else:
            system_prompt, user_prompt = self._build_prompt(
                analysis_type, question, data_summary
            )

        return self._call_llm_and_parse(analysis_type, system_prompt, user_prompt)

    def _call_llm_and_parse(
        self, analysis_type: str, system_prompt: str, user_prompt: str
    ) -> dict[str, Any]:
        """调用 LLM 并解析响应

        Args:
            analysis_type: 分析类型
            system_prompt: 系统提示词
            user_prompt: 用户提示词

        Returns:
            分析结果字典
        """
        try:
            import asyncio

            # 检查是否在异步上下文中
            try:
                loop = asyncio.get_running_loop()
                # 在异步上下文中，使用线程池执行
                import concurrent.futures

                def sync_call():
                    return asyncio.run(
                        self._llm_client.generate(system=system_prompt, prompt=user_prompt)
                    )

                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(sync_call)
                    llm_response = future.result(timeout=60)
            except RuntimeError:
                # 不在异步上下文中
                llm_response = asyncio.run(
                    self._llm_client.generate(system=system_prompt, prompt=user_prompt)
                )

            raw_response = llm_response.content
            parsed = self._parse_response(analysis_type, raw_response)

            return AnalysisResult(
                type=analysis_type,
                conclusion=parsed.get("conclusion", ""),
                findings=parsed.get("findings", []),
                confidence=parsed.get("confidence", 0.5),
                suggestions=parsed.get("suggestions", []),
                raw_response=raw_response,
            ).to_dict()

        except Exception as e:
            logger.error(f"LLM 调用失败: {e}")
            return AnalysisResult(
                type=analysis_type,
                error=f"LLM 调用失败: {str(e)}",
            ).to_dict()

    def interpret(self, data: list[dict[str, Any]], question: str) -> dict[str, Any]:
        """结果解读分析

        对查询结果进行深入解读，提取关键洞察。

        Args:
            data: 查询结果数据列表
            question: 原始问题

        Returns:
            分析结果字典
        """
        if not data:
            return AnalysisResult(
                type="interpret",
                conclusion="数据为空，无法进行解读分析",
                findings=["没有可分析的数据"],
                confidence=0.0,
                suggestions=["请提供有效的数据进行分析"],
            ).to_dict()

        data_summary = self._summarize_result(data)
        system_prompt, user_prompt = self._build_prompt(
            "interpret", question, data_summary
        )

        return self._call_llm_and_parse("interpret", system_prompt, user_prompt)

    def compare(
        self, data1: list[dict[str, Any]], data2: list[dict[str, Any]], question: str
    ) -> dict[str, Any]:
        """对比分析

        比较两个数据集的差异。

        Args:
            data1: 第一个数据集
            data2: 第二个数据集
            question: 对比问题

        Returns:
            分析结果字典
        """
        if not data1:
            return AnalysisResult(
                type="compare",
                error="数据集1为空，无法进行对比分析",
            ).to_dict()

        if not data2:
            return AnalysisResult(
                type="compare",
                error="数据集2为空，无法进行对比分析",
            ).to_dict()

        data1_summary = self._summarize_result(data1)
        data2_summary = self._summarize_result(data2)

        system_prompt, user_prompt = self._build_prompt(
            "compare",
            question,
            data1_summary,
            data1_summary=data1_summary,
            data2_summary=data2_summary,
        )

        return self._call_llm_and_parse("compare", system_prompt, user_prompt)

    def analyze_anomalies(self, data: list[dict[str, Any]], question: str) -> dict[str, Any]:
        """异常检测分析

        识别数据中的异常点并解释原因。

        Args:
            data: 查询结果数据列表
            question: 分析问题

        Returns:
            分析结果字典
        """
        if not data:
            return AnalysisResult(
                type="anomaly",
                conclusion="数据为空，无法进行异常检测",
                findings=["没有可分析的数据"],
                confidence=0.0,
                suggestions=["请提供有效的数据进行分析"],
            ).to_dict()

        data_summary = self._summarize_result(data)
        system_prompt, user_prompt = self._build_prompt(
            "anomaly", question, data_summary
        )

        return self._call_llm_and_parse("anomaly", system_prompt, user_prompt)

    def forecast_reasoning(
        self, forecast_data: list[dict[str, Any]], question: str
    ) -> dict[str, Any]:
        """预测结果解读

        解释预测模型的输出和决策依据。

        Args:
            forecast_data: 预测结果数据
            question: 解读问题

        Returns:
            分析结果字典
        """
        if not forecast_data:
            return AnalysisResult(
                type="forecast_reasoning",
                conclusion="预测数据为空，无法进行解读",
                findings=["没有可解读的预测数据"],
                confidence=0.0,
                suggestions=["请提供有效的预测结果进行分析"],
            ).to_dict()

        forecast_summary = self._summarize_result(forecast_data)
        system_prompt, user_prompt = self._build_prompt(
            "forecast_reasoning", question, forecast_summary
        )

        return self._call_llm_and_parse("forecast_reasoning", system_prompt, user_prompt)

    def explain_sql(self, sql: str, question: str) -> dict[str, Any]:
        """SQL 语句解释

        用通俗易懂的语言解释 SQL 查询逻辑。

        Args:
            sql: SQL 查询语句
            question: 解释问题

        Returns:
            分析结果字典
        """
        if not sql or not sql.strip():
            return AnalysisResult(
                type="sql_explain",
                conclusion="SQL 语句为空，无法进行解释",
                findings=["没有可解释的 SQL 语句"],
                confidence=0.0,
                suggestions=["请提供有效的 SQL 语句"],
            ).to_dict()

        system_prompt, user_prompt = self._build_prompt("sql_explain", question, sql)

        return self._call_llm_and_parse("sql_explain", system_prompt, user_prompt)
