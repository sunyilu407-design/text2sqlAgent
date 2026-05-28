"""LLM 模块"""

from micro_genbi.llm.cost_tracker import (
    LLMCostTracker,
    LLMCallRecord,
    CostSummary,
    LLMProvider,
    TOKEN_PRICING,
    get_cost_tracker,
    record_llm_call,
)
from micro_genbi.llm.prompts import (
    SQL_SYSTEM_PROMPT,
    SQL_EXAMPLES,
    ERROR_CORRECTION_PROMPT,
    ERROR_CLASSIFICATION_PROMPT,
    RESULT_INTERPRET_PROMPT,
    MULTI_DB_SYSTEM_PROMPT,
    PROMPT_TEMPLATES,
    DIALECT_HINTS,
    get_dialect_hint,
    render_sql_prompt,
    render_error_correction_prompt,
    render_multi_db_prompt,
)

__all__ = [
    # 成本追踪
    "LLMCostTracker",
    "LLMCallRecord",
    "CostSummary",
    "LLMProvider",
    "TOKEN_PRICING",
    "get_cost_tracker",
    "record_llm_call",
    # Prompt 模板
    "SQL_SYSTEM_PROMPT",
    "SQL_EXAMPLES",
    "ERROR_CORRECTION_PROMPT",
    "ERROR_CLASSIFICATION_PROMPT",
    "RESULT_INTERPRET_PROMPT",
    "MULTI_DB_SYSTEM_PROMPT",
    "PROMPT_TEMPLATES",
    "DIALECT_HINTS",
    "get_dialect_hint",
    "render_sql_prompt",
    "render_error_correction_prompt",
    "render_multi_db_prompt",
]
