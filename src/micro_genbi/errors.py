"""Micro-GenBI 异常处理模块

基于 WrenAI 源码移植的异常处理体系。
"""

from __future__ import annotations

import re
from enum import Enum
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .models import ErrorPhase, ErrorCode


class GenBIError(Exception):
    """Micro-GenBI 基础异常类"""

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        phase: Optional[str] = None,
        details: Optional[dict] = None,
    ):
        super().__init__(message)
        self.message = message
        self.code = code or "INTERNAL_ERROR"
        self.phase = phase
        self.details = details or {}

    def to_dict(self) -> dict:
        return {
            "code": self.code,
            "message": self.message,
            "phase": self.phase,
            "details": self.details,
        }

    def __repr__(self) -> str:
        return f"GenBIError({self.code}, {self.phase}, {self.message})"


class GenBIReRetry(GenBIError):
    """可重试异常

    抛出此异常表示当前步骤失败，但可以在修正后重试。
    """

    def __init__(
        self,
        message: str,
        code: Optional[str] = None,
        phase: Optional[str] = None,
        max_retries: int = 3,
        retry_count: int = 0,
        details: Optional[dict] = None,
    ):
        super().__init__(message, code, phase, details)
        self.max_retries = max_retries
        self.retry_count = retry_count

    @property
    def can_retry(self) -> bool:
        return self.retry_count < self.max_retries


class SQLExecutionError(GenBIReRetry):
    """SQL 执行错误"""

    def __init__(
        self,
        message: str,
        sql: Optional[str] = None,
        phase: str = "sql_execution",
        **kwargs,
    ):
        super().__init__(
            message=message,
            code="SQL_EXECUTION_ERROR",
            phase=phase,
            **kwargs,
        )
        self.sql = sql


class SQLValidationError(GenBIError):
    """SQL 验证错误（安全检查失败）"""

    def __init__(
        self,
        message: str,
        sql: Optional[str] = None,
        violation_type: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code="SQL_VALIDATION_ERROR",
            phase="sql_validation",
        )
        self.sql = sql
        self.violation_type = violation_type or "unknown"


class LLMError(GenBIReRetry):
    """LLM 调用错误"""

    def __init__(
        self,
        message: str,
        provider: Optional[str] = None,
        model: Optional[str] = None,
        **kwargs,
    ):
        super().__init__(
            message=message,
            code="LLM_ERROR",
            phase="llm_call",
            **kwargs,
        )
        self.provider = provider
        self.model = model


class SchemaError(GenBIError):
    """Schema 相关错误"""

    def __init__(
        self,
        message: str,
        table: Optional[str] = None,
        column: Optional[str] = None,
    ):
        super().__init__(
            message=message,
            code="SCHEMA_ERROR",
            phase="schema_resolution",
        )
        self.table = table
        self.column = column


class AuthenticationError(GenBIError):
    """认证错误"""

    def __init__(self, message: str = "Authentication failed"):
        super().__init__(
            message=message,
            code="AUTHENTICATION_ERROR",
            phase="authentication",
        )


class PermissionDeniedError(GenBIError):
    """权限不足"""

    def __init__(self, message: str = "Permission denied"):
        super().__init__(
            message=message,
            code="PERMISSION_DENIED",
            phase="authorization",
        )


class RateLimitError(GenBIError):
    """请求过于频繁"""

    def __init__(
        self,
        message: str = "Rate limit exceeded",
        retry_after: Optional[int] = None,
    ):
        super().__init__(
            message=message,
            code="RATE_LIMITED",
            phase="rate_limit",
        )
        self.retry_after = retry_after


class TimeoutError(GenBIReRetry):
    """执行超时"""

    def __init__(
        self,
        message: str,
        operation: Optional[str] = None,
        timeout_seconds: Optional[int] = None,
    ):
        super().__init__(
            message=message,
            code="TIMEOUT",
            phase="execution",
            **kwargs,
        )
        self.operation = operation
        self.timeout_seconds = timeout_seconds


# =============================================================================
# 错误阶段与错误码定义
# =============================================================================

class ErrorPhase(str, Enum):
    """错误发生阶段"""

    # 输入阶段
    INPUT = "input"                    # 用户输入解析
    AUTHENTICATION = "authentication"  # 认证
    AUTHORIZATION = "authorization"    # 授权

    # 分析阶段
    INTENT_CLASSIFICATION = "intent_classification"  # 意图分类
    SCHEMA_RESOLUTION = "schema_resolution"          # Schema 解析
    SEMANTIC_RETRIEVAL = "semantic_retrieval"        # 语义检索

    # 生成阶段
    SQL_GENERATION = "sql_generation"    # SQL 生成
    SQL_VALIDATION = "sql_validation"    # SQL 验证
    SQL_EXECUTION = "sql_execution"      # SQL 执行

    # 输出阶段
    RESULT_FORMAT = "result_format"  # 结果格式化
    CHART_GENERATION = "chart_generation"  # 图表生成

    # 系统阶段
    LLM_CALL = "llm_call"          # LLM 调用
    DATABASE_CONNECTION = "database_connection"  # 数据库连接
    INTERNAL = "internal"          # 内部错误


class ErrorCode(str, Enum):
    """错误码定义"""

    # 输入错误
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_QUERY = "INVALID_QUERY"

    # 认证/授权错误
    AUTHENTICATION_ERROR = "AUTHENTICATION_ERROR"
    PERMISSION_DENIED = "PERMISSION_DENIED"
    TENANT_VIOLATION = "TENANT_VIOLATION"

    # SQL 相关
    SQL_VALIDATION_ERROR = "SQL_VALIDATION_ERROR"
    SQL_EXECUTION_ERROR = "SQL_EXECUTION_ERROR"
    SQL_SYNTAX_ERROR = "SQL_SYNTAX_ERROR"
    SQL_INJECTION_BLOCKED = "SQL_INJECTION_BLOCKED"
    TABLE_NOT_FOUND = "TABLE_NOT_FOUND"
    COLUMN_NOT_FOUND = "COLUMN_NOT_FOUND"

    # LLM 相关
    LLM_ERROR = "LLM_ERROR"
    LLM_TIMEOUT = "LLM_TIMEOUT"
    LLM_RATE_LIMIT = "LLM_RATE_LIMIT"

    # Schema 相关
    SCHEMA_ERROR = "SCHEMA_ERROR"
    SCHEMA_NOT_FOUND = "SCHEMA_NOT_FOUND"

    # 执行错误
    TIMEOUT = "TIMEOUT"
    RATE_LIMITED = "RATE_LIMITED"

    # 系统错误
    INTERNAL_ERROR = "INTERNAL_ERROR"
    DATABASE_ERROR = "DATABASE_ERROR"


# =============================================================================
# 错误处理辅助函数
# =============================================================================

# 基础设施错误（直接抛出，不重试）
INFRASTRUCTURE_ERROR_CODES = {
    "AUTHENTICATION_ERROR",
    "PERMISSION_DENIED",
    "TENANT_VIOLATION",
    "SCHEMA_NOT_FOUND",
    "RATE_LIMITED",
    "INTERNAL_ERROR",
}

# LLM 可修复错误（触发重试）
LLM_RETRY_ERROR_CODES = {
    "SQL_SYNTAX_ERROR",
    "LLM_ERROR",
    "LLM_TIMEOUT",
    "TIMEOUT",
    "INVALID_REQUEST",
}


def should_propagate(exc: Exception) -> bool:
    """
    判断异常是否应该直接传播（不重试）

    基础设施错误（如认证失败、权限不足）直接传播。
    LLM 可修复错误（如语法错误、超时）可以重试。
    """
    if isinstance(exc, GenBIError):
        return exc.code in INFRASTRUCTURE_ERROR_CODES
    return True


def to_retry(
    exc: Exception,
    max_retries: int = 3,
    retry_count: int = 0,
) -> GenBIReRetry:
    """
    将异常转换为可重试异常
    """
    if isinstance(exc, GenBIReRetry):
        exc.retry_count = retry_count
        exc.max_retries = max_retries
        return exc

    if isinstance(exc, GenBIError):
        return GenBIReRetry(
            message=exc.message,
            code=exc.code,
            phase=exc.phase,
            max_retries=max_retries,
            retry_count=retry_count,
            details=exc.details,
        )

    # 其他异常包装
    return GenBIReRetry(
        message=str(exc),
        code="INTERNAL_ERROR",
        phase="internal",
        max_retries=max_retries,
        retry_count=retry_count,
    )


def get_error_phase(code: str) -> ErrorPhase:
    """根据错误码获取错误阶段"""
    phase_mapping = {
        "AUTHENTICATION_ERROR": ErrorPhase.AUTHENTICATION,
        "PERMISSION_DENIED": ErrorPhase.AUTHORIZATION,
        "TENANT_VIOLATION": ErrorPhase.AUTHORIZATION,
        "SQL_VALIDATION_ERROR": ErrorPhase.SQL_VALIDATION,
        "SQL_EXECUTION_ERROR": ErrorPhase.SQL_EXECUTION,
        "SQL_SYNTAX_ERROR": ErrorPhase.SQL_GENERATION,
        "SQL_INJECTION_BLOCKED": ErrorPhase.SQL_VALIDATION,
        "TABLE_NOT_FOUND": ErrorPhase.SCHEMA_RESOLUTION,
        "COLUMN_NOT_FOUND": ErrorPhase.SCHEMA_RESOLUTION,
        "LLM_ERROR": ErrorPhase.LLM_CALL,
        "LLM_TIMEOUT": ErrorPhase.LLM_CALL,
        "SCHEMA_ERROR": ErrorPhase.SCHEMA_RESOLUTION,
        "SCHEMA_NOT_FOUND": ErrorPhase.SCHEMA_RESOLUTION,
        "TIMEOUT": ErrorPhase.EXECUTION,
        "RATE_LIMITED": ErrorPhase.RATE_LIMIT,
        "INVALID_REQUEST": ErrorPhase.INPUT,
        "INVALID_QUERY": ErrorPhase.INPUT,
    }
    return phase_mapping.get(code, ErrorPhase.INTERNAL)


# =============================================================================
# 敏感信息脱敏
# =============================================================================

# 需要脱敏的敏感字段
SENSITIVE_PATTERNS = [
    (r'password["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'password": "***"'),
    (r'secret["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'secret": "***"'),
    (r'api[_-]?key["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'api_key": "***"'),
    (r'token["\']?\s*[:=]\s*["\']?[^"\'\s,}]+', 'token": "***"'),
    (r'Authorization["\']?\s*[:=]\s*["\']?Bearer\s+[^\s"\'}]+', 'Authorization": "Bearer ***"'),
]


def redact_secrets(text: str) -> str:
    """
    脱敏敏感信息

    将日志和错误消息中的敏感信息替换为 ***。
    """
    result = text
    for pattern, replacement in SENSITIVE_PATTERNS:
        result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)
    return result


def safe_error_message(error: Exception) -> str:
    """安全的错误消息（已脱敏）"""
    return redact_secrets(str(error))
