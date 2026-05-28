"""Micro-GenBI - 微分智能数据引擎

企业级 Text2SQL 垂直领域智能体。
"""

__version__ = "0.1.0"

from micro_genbi.monitoring import (
    setup_logging,
    get_logger,
    LogContext,
    MetricsCollector,
    get_metrics,
    track_duration,
    LLMCostTracker,
    get_cost_tracker,
    record_llm_call,
)
from micro_genbi.semantic import SchemaRegistry, get_schema_registry
from micro_genbi.db import (
    DatabaseHealthChecker,
    MultiDatabaseHealthMonitor,
    get_health_monitor,
    ConfigLoader,
    get_config,
    get_database_config,
    DatabaseExecutor,
    get_executor,
)
from micro_genbi.errors import (
    GenBIError,
    GenBIReRetry,
    SQLValidationError,
    SQLExecutionError,
    should_propagate,
    to_retry,
    redact_secrets,
)
from micro_genbi.security import (
    SQLSafetyValidator,
    SQLSanitizer,
    PromptInjectionDetector,
    DataMasker,
    validate_sql,
    sanitize_sql,
    check_prompt_safety,
    mask_sensitive_data,
)
from micro_genbi.llm.base import (
    LLMClient,
    LLMResponse,
    create_llm_client,
)

__all__ = [
    # 版本
    "__version__",
    # 可观测性
    "setup_logging",
    "get_logger",
    "LogContext",
    "MetricsCollector",
    "get_metrics",
    "track_duration",
    "LLMCostTracker",
    "get_cost_tracker",
    "record_llm_call",
    # 语义层
    "SchemaRegistry",
    "get_schema_registry",
    # 数据库
    "DatabaseHealthChecker",
    "MultiDatabaseHealthMonitor",
    "get_health_monitor",
    "ConfigLoader",
    "get_config",
    "get_database_config",
    "DatabaseExecutor",
    "get_executor",
    # 异常
    "GenBIError",
    "GenBIReRetry",
    "SQLValidationError",
    "SQLExecutionError",
    "should_propagate",
    "to_retry",
    "redact_secrets",
    # 安全
    "SQLSafetyValidator",
    "SQLSanitizer",
    "PromptInjectionDetector",
    "DataMasker",
    "validate_sql",
    "sanitize_sql",
    "check_prompt_safety",
    "mask_sensitive_data",
    # LLM
    "LLMClient",
    "LLMResponse",
    "create_llm_client",
]
