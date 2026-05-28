"""SQL 自愈重试模块

自动检测并修复 SQL 执行错误。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional, Any
from enum import Enum

from micro_genbi import get_logger
from micro_genbi.errors import SQLExecutionError, SQLValidationError, GenBIReRetry
from micro_genbi.llm.base import LLMClient

logger = get_logger(__name__)


class ErrorType(str, Enum):
    """错误类型"""
    SYNTAX_ERROR = "syntax_error"           # 语法错误
    TABLE_NOT_FOUND = "table_not_found"     # 表不存在
    COLUMN_NOT_FOUND = "column_not_found"   # 列不存在
    TYPE_MISMATCH = "type_mismatch"        # 类型不匹配
    UNKNOWN_ERROR = "unknown_error"        # 未知错误


@dataclass
class ErrorAnalysis:
    """错误分析结果"""
    error_type: ErrorType
    error_message: str
    suggested_fix: Optional[str] = None
    needs_schema_update: bool = False
    confidence: float = 0.0


@dataclass
class CorrectionContext:
    """修正上下文"""
    original_query: str  # 用户原始查询
    original_sql: str     # 生成的 SQL
    error: ErrorAnalysis  # 错误分析
    schema_context: str   # Schema 上下文
    retry_count: int = 0
    corrections_history: list[str] = field(default_factory=list)


class SelfCorrector:
    """
    SQL 自愈器

    分析 SQL 执行错误并尝试自动修复。
    """

    # 错误模式匹配
    ERROR_PATTERNS = [
        # PostgreSQL
        (r'表\s*"?(\w+)"?\s*不存在', ErrorType.TABLE_NOT_FOUND, 0.95),
        (r'relation\s+"(\w+)"\s+does not exist', ErrorType.TABLE_NOT_FOUND, 0.95),
        (r'column\s+"(\w+)"\s+does not exist', ErrorType.COLUMN_NOT_FOUND, 0.95),
        (r'column\s+"?(\w+)"?\s+没有找到', ErrorType.COLUMN_NOT_FOUND, 0.95),
        (r'syntax error at or near\s+"(\w+)"', ErrorType.SYNTAX_ERROR, 0.9),
        (r'语法错误', ErrorType.SYNTAX_ERROR, 0.9),

        # MySQL
        (r'Table\s+`?(\w+)`?\s+doesn\'t exist', ErrorType.TABLE_NOT_FOUND, 0.95),
        (r'Unknown column\s+`?(\w+)`?\s+in', ErrorType.COLUMN_NOT_FOUND, 0.95),

        # 通用
        (r'(SELECT|INSERT|UPDATE|DELETE).*syntax', ErrorType.SYNTAX_ERROR, 0.85),
        (r'类型不匹配|type mismatch', ErrorType.TYPE_MISMATCH, 0.9),
    ]

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_corrections: int = 3,
    ):
        self.llm_client = llm_client
        self.max_corrections = max_corrections

    def analyze_error(self, error: Exception, sql: str) -> ErrorAnalysis:
        """
        分析错误类型

        Args:
            error: 异常
            sql: 失败的 SQL

        Returns:
            ErrorAnalysis: 错误分析结果
        """
        error_msg = str(error)

        # 模式匹配
        for pattern, error_type, confidence in self.ERROR_PATTERNS:
            match = re.search(pattern, error_msg, re.IGNORECASE)
            if match:
                suggested_fix = self._generate_fix_suggestion(
                    error_type, match, error_msg
                )
                return ErrorAnalysis(
                    error_type=error_type,
                    error_message=error_msg,
                    suggested_fix=suggested_fix,
                    needs_schema_update=(error_type in [
                        ErrorType.TABLE_NOT_FOUND,
                        ErrorType.COLUMN_NOT_FOUND,
                    ]),
                    confidence=confidence,
                )

        # 默认未知错误
        return ErrorAnalysis(
            error_type=ErrorType.UNKNOWN_ERROR,
            error_message=error_msg,
            confidence=0.5,
        )

    def _generate_fix_suggestion(
        self,
        error_type: ErrorType,
        match: re.Match,
        error_msg: str,
    ) -> Optional[str]:
        """生成修复建议"""
        if error_type == ErrorType.TABLE_NOT_FOUND:
            table_name = match.group(1) if match.groups() else "unknown"
            return f"表 {table_name} 不存在，请检查表名或更新 Schema"

        elif error_type == ErrorType.COLUMN_NOT_FOUND:
            col_name = match.group(1) if match.groups() else "unknown"
            return f"列 {col_name} 不存在，请检查列名"

        elif error_type == ErrorType.SYNTAX_ERROR:
            return "SQL 语法错误，请检查语法"

        return None

    async def correct(
        self,
        context: CorrectionContext,
    ) -> str:
        """
        尝试修复 SQL

        Args:
            context: 修正上下文

        Returns:
            str: 修正后的 SQL
        """
        if not self.llm_client:
            logger.warning("未配置 LLM 客户端，无法自动修正")
            return context.original_sql

        if context.retry_count >= self.max_corrections:
            logger.warning("已达到最大修正次数")
            return context.original_sql

        # 构建修正 Prompt
        prompt = self._build_correction_prompt(context)

        try:
            response = await self.llm_client.generate(prompt)
            corrected_sql = self._extract_sql(response.content)

            # 记录修正历史
            context.corrections_history.append(corrected_sql)
            context.retry_count += 1

            logger.info(f"SQL 修正成功 (第 {context.retry_count} 次): {corrected_sql}")
            return corrected_sql

        except Exception as e:
            logger.error(f"SQL 修正失败: {e}")
            return context.original_sql

    def _build_correction_prompt(self, context: CorrectionContext) -> str:
        """构建修正 Prompt"""
        error = context.error

        prompt = f"""你是一个 SQL 专家，负责修复有问题的 SQL 查询。

原始用户问题: {context.original_query}

有问题的 SQL:
```sql
{context.original_sql}
```

错误信息:
{error.error_message}

错误类型: {error.error_type.value}

Schema 信息:
{context.schema_context}

请修复 SQL，只输出修复后的 SQL 代码，不要解释。

修复规则：
1. 只生成 SELECT 查询
2. 所有 SELECT 必须有 LIMIT 1000
3. 使用正确的表名和列名
4. 确保 SQL 语法正确

修复后的 SQL:"""

        return prompt

    def _extract_sql(self, content: str) -> str:
        """提取 SQL"""
        # 从代码块中提取
        blocks = re.findall(r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
        if blocks:
            return blocks[0].strip()

        blocks = re.findall(r'```\s*(.*?)\s*```', content, re.DOTALL)
        if blocks:
            return blocks[0].strip()

        return content.strip()


class SelfCorrectionPipeline:
    """
    自愈流水线

    集成错误检测、分析、修正的完整流程。
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        max_retries: int = 3,
    ):
        self.corrector = SelfCorrector(llm_client, max_retries)
        self.max_retries = max_retries

    async def execute_with_correction(
        self,
        executor_func,  # async function that executes SQL
        sql: str,
        original_query: str,
        schema_context: str,
    ) -> tuple[str, bool]:
        """
        带自愈的执行

        Args:
            executor_func: SQL 执行函数
            sql: 要执行的 SQL
            original_query: 用户原始查询
            schema_context: Schema 上下文

        Returns:
            tuple: (result, was_corrected)
        """
        context = CorrectionContext(
            original_query=original_query,
            original_sql=sql,
            error=ErrorAnalysis(
                error_type=ErrorType.UNKNOWN_ERROR,
                error_message="",
            ),
            schema_context=schema_context,
        )

        current_sql = sql
        retry_count = 0

        while retry_count <= self.max_retries:
            try:
                # 尝试执行
                result = await executor_func(current_sql)
                return result, (retry_count > 0)

            except (SQLExecutionError, SQLValidationError) as e:
                # 分析错误
                error_analysis = self.corrector.analyze_error(e, current_sql)
                context.error = error_analysis

                if error_analysis.needs_schema_update:
                    # Schema 问题，需要手动修复
                    logger.error(f"Schema 问题无法自动修复: {error_analysis.error_message}")
                    raise

                if retry_count >= self.max_retries:
                    logger.error(f"达到最大重试次数: {self.max_retries}")
                    raise

                # 尝试修正
                logger.info(f"尝试修正 SQL (第 {retry_count + 1} 次): {error_analysis.error_message}")
                current_sql = await self.corrector.correct(context)
                retry_count += 1

            except Exception as e:
                # 其他错误，直接抛出
                logger.error(f"执行失败: {e}")
                raise


# =============================================================================
# 便捷函数
# =============================================================================

def analyze_error(error: Exception, sql: str) -> ErrorAnalysis:
    """
    便捷函数：分析错误

    Args:
        error: 异常
        sql: SQL

    Returns:
        ErrorAnalysis: 错误分析
    """
    corrector = SelfCorrector()
    return corrector.analyze_error(error, sql)
