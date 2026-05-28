"""SQL 自愈重试模块单元测试"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from micro_genbi.pipeline.self_correction import (
    SelfCorrector,
    SelfCorrectionPipeline,
    ErrorType,
    ErrorAnalysis,
    CorrectionContext,
    analyze_error,
)


# ── Tests: ErrorType Enum ────────────────────────────────────────────────────

class TestErrorType:
    """错误类型枚举测试"""

    def test_error_types_exist(self):
        """测试所有错误类型定义"""
        assert ErrorType.SYNTAX_ERROR.value == "syntax_error"
        assert ErrorType.TABLE_NOT_FOUND.value == "table_not_found"
        assert ErrorType.COLUMN_NOT_FOUND.value == "column_not_found"
        assert ErrorType.TYPE_MISMATCH.value == "type_mismatch"
        assert ErrorType.UNKNOWN_ERROR.value == "unknown_error"


# ── Tests: ErrorAnalysis ─────────────────────────────────────────────────────

class TestErrorAnalysis:
    """错误分析结果测试"""

    def test_error_analysis_creation(self):
        """测试错误分析创建"""
        analysis = ErrorAnalysis(
            error_type=ErrorType.SYNTAX_ERROR,
            error_message="syntax error at 'SELECT'",
            suggested_fix="Check SQL syntax",
            needs_schema_update=False,
            confidence=0.9,
        )
        assert analysis.error_type == ErrorType.SYNTAX_ERROR
        assert analysis.confidence == 0.9

    def test_error_analysis_defaults(self):
        """测试默认值"""
        analysis = ErrorAnalysis(
            error_type=ErrorType.UNKNOWN_ERROR,
            error_message="Some error",
        )
        assert analysis.suggested_fix is None
        assert analysis.needs_schema_update is False
        assert analysis.confidence == 0.0


# ── Tests: CorrectionContext ─────────────────────────────────────────────────

class TestCorrectionContext:
    """修正上下文测试"""

    def test_correction_context_creation(self):
        """测试上下文创建"""
        error = ErrorAnalysis(
            error_type=ErrorType.TABLE_NOT_FOUND,
            error_message="table not found",
        )
        context = CorrectionContext(
            original_query="查询订单",
            original_sql="SELECT * FROM oderrs",
            error=error,
            schema_context="orders(id, amount)",
        )
        assert context.original_query == "查询订单"
        assert context.retry_count == 0
        assert context.corrections_history == []

    def test_correction_context_defaults(self):
        """测试默认值"""
        context = CorrectionContext(
            original_query="test",
            original_sql="SELECT 1",
            error=MagicMock(),
            schema_context="",
        )
        assert context.retry_count == 0
        assert context.corrections_history == []


# ── Tests: SelfCorrector.analyze_error ──────────────────────────────────────

class TestSelfCorrectorAnalyzeError:
    """错误分析测试"""

    def setup_method(self):
        """Setup"""
        self.corrector = SelfCorrector()

    def test_analyze_pg_table_not_found(self):
        """测试 PostgreSQL 表不存在错误"""
        error = Exception('relation "users" does not exist')
        result = self.corrector.analyze_error(error, "SELECT * FROM users")
        assert result.error_type == ErrorType.TABLE_NOT_FOUND
        assert result.confidence == 0.95

    def test_analyze_pg_column_not_found(self):
        """测试 PostgreSQL 列不存在错误"""
        error = Exception('column "user_name" does not exist')
        result = self.corrector.analyze_error(error, "SELECT user_name FROM users")
        assert result.error_type == ErrorType.COLUMN_NOT_FOUND
        assert result.confidence == 0.95

    def test_analyze_mysql_table_not_found(self):
        """测试 MySQL 表不存在错误"""
        error = Exception("Table `orders` doesn't exist")
        result = self.corrector.analyze_error(error, "SELECT * FROM orders")
        assert result.error_type == ErrorType.TABLE_NOT_FOUND
        assert result.confidence == 0.95

    def test_analyze_chinese_table_not_found(self):
        """测试中文表不存在错误"""
        error = Exception('表 "订单" 不存在')
        result = self.corrector.analyze_error(error, "SELECT * FROM 订单")
        assert result.error_type == ErrorType.TABLE_NOT_FOUND
        assert result.confidence == 0.95

    def test_analyze_type_mismatch(self):
        """测试类型不匹配"""
        error = Exception("类型不匹配: INTEGER and VARCHAR")
        result = self.corrector.analyze_error(error, "SELECT * FROM orders")
        assert result.error_type == ErrorType.TYPE_MISMATCH
        assert result.confidence == 0.9

    def test_analyze_unknown_error(self):
        """测试未知错误"""
        error = Exception("some random error")
        result = self.corrector.analyze_error(error, "SELECT 1")
        assert result.error_type == ErrorType.UNKNOWN_ERROR
        assert result.confidence == 0.5

    def test_analyze_schema_update_flag_table(self):
        """测试表不存在需要更新 Schema"""
        error = Exception('relation "users" does not exist')
        result = self.corrector.analyze_error(error, "SELECT * FROM users")
        assert result.needs_schema_update is True

    def test_analyze_schema_update_flag_column(self):
        """测试列不存在需要更新 Schema"""
        error = Exception('column "name" does not exist')
        result = self.corrector.analyze_error(error, "SELECT name FROM users")
        assert result.needs_schema_update is True

    def test_analyze_schema_update_flag_syntax(self):
        """测试语法错误不需要更新 Schema"""
        error = Exception("syntax error")
        result = self.corrector.analyze_error(error, "SELECT")
        assert result.needs_schema_update is False


# ── Tests: SelfCorrector._generate_fix_suggestion ────────────────────────────

class TestSelfCorrectorFixSuggestion:
    """修复建议测试"""

    def test_suggestion_for_table_not_found(self):
        """测试表不存在的修复建议"""
        import re
        corrector = SelfCorrector()
        error = Exception('relation "users" does not exist')
        match = re.search(r'relation\s+"(\w+)"', str(error))
        suggestion = corrector._generate_fix_suggestion(
            ErrorType.TABLE_NOT_FOUND, match, str(error)
        )
        assert "users" in suggestion
        assert "不存在" in suggestion

    def test_suggestion_for_column_not_found(self):
        """测试列不存在的修复建议"""
        import re
        corrector = SelfCorrector()
        error = Exception('column "name" does not exist')
        match = re.search(r'column\s+"(\w+)"', str(error))
        suggestion = corrector._generate_fix_suggestion(
            ErrorType.COLUMN_NOT_FOUND, match, str(error)
        )
        assert "name" in suggestion
        assert "不存在" in suggestion

    def test_suggestion_for_syntax_error(self):
        """测试语法错误的修复建议"""
        import re
        corrector = SelfCorrector()
        error = Exception("syntax error")
        suggestion = corrector._generate_fix_suggestion(
            ErrorType.SYNTAX_ERROR, None, str(error)
        )
        assert "语法" in suggestion

    def test_suggestion_for_unknown(self):
        """测试未知错误的修复建议"""
        corrector = SelfCorrector()
        suggestion = corrector._generate_fix_suggestion(
            ErrorType.UNKNOWN_ERROR, None, "error"
        )
        assert suggestion is None


# ── Tests: SelfCorrector correct ─────────────────────────────────────────────

class TestSelfCorrectorCorrect:
    """修正功能测试（同步部分）"""

    def test_correct_no_llm_client_sync(self):
        """测试无 LLM 客户端时返回原始 SQL（同步检查）"""
        # correct 是 async 方法，这里测试同步部分逻辑
        corrector = SelfCorrector(llm_client=None)
        context = CorrectionContext(
            original_query="test",
            original_sql="SELECT 1",
            error=ErrorAnalysis(ErrorType.SYNTAX_ERROR, "error"),
            schema_context="",
        )
        # correct() 返回协程对象，无 LLM 时协程执行后返回原始 SQL
        # 使用 pytest-asyncio 的 mark
        import asyncio
        async def run_test():
            result = await corrector.correct(context)
            assert result == "SELECT 1"
        asyncio.run(run_test())


# ── Tests: SelfCorrector._extract_sql ────────────────────────────────────────

class TestSelfCorrectorExtractSQL:
    """SQL 提取测试"""

    def setup_method(self):
        self.corrector = SelfCorrector()

    def test_extract_sql_from_code_block(self):
        """测试从代码块提取 SQL"""
        content = "Here is the fixed SQL:\n```sql\nSELECT * FROM users\n```"
        sql = self.corrector._extract_sql(content)
        assert sql == "SELECT * FROM users"

    def test_extract_sql_from_code_block_no_lang(self):
        """测试从无语言标记的代码块提取"""
        content = "```\nSELECT * FROM orders\n```"
        sql = self.corrector._extract_sql(content)
        assert sql == "SELECT * FROM orders"

    def test_extract_sql_plain_text(self):
        """测试纯文本提取"""
        content = "SELECT * FROM users WHERE id = 1"
        sql = self.corrector._extract_sql(content)
        assert sql == "SELECT * FROM users WHERE id = 1"

    def test_extract_sql_with_trailing_whitespace(self):
        """测试提取时去除空白"""
        content = "  SELECT 1  \n\n"
        sql = self.corrector._extract_sql(content)
        assert sql == "SELECT 1"


# ── Tests: SelfCorrectionPipeline ────────────────────────────────────────────

class TestSelfCorrectionPipeline:
    """自愈流水线测试"""

    def test_pipeline_creation(self):
        """测试流水线创建"""
        pipeline = SelfCorrectionPipeline(max_retries=3)
        assert pipeline.max_retries == 3
        assert isinstance(pipeline.corrector, SelfCorrector)

    def test_pipeline_creation_with_llm(self):
        """测试带 LLM 的流水线创建"""
        mock_llm = MagicMock()
        pipeline = SelfCorrectionPipeline(llm_client=mock_llm, max_retries=2)
        assert pipeline.corrector.llm_client is mock_llm
        assert pipeline.max_retries == 2


# ── Tests: analyze_error convenience function ────────────────────────────────

class TestAnalyzeErrorConvenience:
    """便捷函数测试"""

    def test_analyze_error_function(self):
        """测试便捷函数"""
        error = Exception('relation "users" does not exist')
        result = analyze_error(error, "SELECT * FROM users")
        assert result.error_type == ErrorType.TABLE_NOT_FOUND
        assert result.confidence == 0.95
