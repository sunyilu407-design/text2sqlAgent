"""LLM 成本追踪模块

记录 API 调用次数、Token 消耗和预估成本。
"""

from __future__ import annotations

import csv
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Optional
from collections import defaultdict


class LLMProvider(Enum):
    """LLM 提供商"""
    DEEPSEEK = "deepseek"
    OPENAI = "openai"
    OLLAMA = "ollama"


# Token 单价配置（单位：USD / 1M tokens）
TOKEN_PRICING = {
    "deepseek-chat": {"input": 0.27, "output": 1.10},
    "deepseek-reasoner": {"input": 0.27, "output": 1.10},
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-3.5-turbo": {"input": 0.50, "output": 1.50},
    "ollama-local": {"input": 0.0, "output": 0.0},
}


@dataclass
class LLMCallRecord:
    """LLM 调用记录"""
    timestamp: str
    provider: str
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    duration_ms: float
    success: bool
    error: Optional[str] = None
    cost_usd: float = 0.0
    intent_type: Optional[str] = None


@dataclass
class CostSummary:
    """成本汇总"""
    total_calls: int
    successful_calls: int
    failed_calls: int
    total_prompt_tokens: int
    total_completion_tokens: int
    total_tokens: int
    total_cost_usd: float
    by_provider: dict[str, float] = field(default_factory=dict)
    by_model: dict[str, float] = field(default_factory=dict)
    by_intent: dict[str, int] = field(default_factory=dict)


class LLMCostTracker:
    """
    LLM 成本追踪器

    功能：
    - 记录每次 API 调用的 Token 消耗
    - 按 Provider / Model / Intent 类型分组统计
    - 计算预估成本（基于官方定价）
    - 支持成本上限告警
    """

    def __init__(
        self,
        daily_cost_limit: float = 10.0,
        monthly_cost_limit: float = 1000.0,
    ):
        self.daily_cost_limit = daily_cost_limit
        self.monthly_cost_limit = monthly_cost_limit
        self._records: list[LLMCallRecord] = []
        self._daily_cost: dict[str, float] = defaultdict(float)
        self._monthly_cost: dict[str, float] = defaultdict(float)
        self._by_provider: dict[str, float] = defaultdict(float)
        self._by_model: dict[str, float] = defaultdict(float)
        self._by_intent: dict[str, int] = defaultdict(int)

    def record(
        self,
        provider: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        duration_ms: float,
        success: bool = True,
        error: Optional[str] = None,
        intent_type: Optional[str] = None,
    ) -> LLMCallRecord:
        """记录一次 LLM 调用"""
        cost = self._calc_cost(model, prompt_tokens, completion_tokens)
        record = LLMCallRecord(
            timestamp=datetime.now().isoformat(),
            provider=provider,
            model=model,
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=prompt_tokens + completion_tokens,
            duration_ms=duration_ms,
            success=success,
            error=error,
            cost_usd=cost,
            intent_type=intent_type,
        )
        self._records.append(record)
        self._update_stats(record)
        self._check_cost_limits()
        return record

    def _calc_cost(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        """计算调用成本"""
        pricing = TOKEN_PRICING.get(model, {"input": 0.0, "output": 0.0})
        return round(
            (prompt_tokens / 1_000_000) * pricing["input"] +
            (completion_tokens / 1_000_000) * pricing["output"],
            6
        )

    def _update_stats(self, record: LLMCallRecord) -> None:
        """更新统计"""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        self._daily_cost[today] += record.cost_usd
        self._monthly_cost[month] += record.cost_usd
        self._by_provider[record.provider] += record.cost_usd
        self._by_model[record.model] += record.cost_usd
        if record.intent_type:
            self._by_intent[record.intent_type] += record.total_tokens

    def _check_cost_limits(self) -> Optional[list[dict]]:
        """检查成本上限，返回警告信息"""
        today = datetime.now().strftime("%Y-%m-%d")
        month = datetime.now().strftime("%Y-%m")
        warnings = []
        daily = self._daily_cost.get(today, 0.0)
        if daily > self.daily_cost_limit:
            warnings.append({
                "type": "daily_limit",
                "limit": self.daily_cost_limit,
                "current": daily,
                "message": f"日成本 ${daily:.4f} 已超出上限 ${self.daily_cost_limit}",
            })
        monthly = self._monthly_cost.get(month, 0.0)
        if monthly > self.monthly_cost_limit:
            warnings.append({
                "type": "monthly_limit",
                "limit": self.monthly_cost_limit,
                "current": monthly,
                "message": f"月成本 ${monthly:.4f} 已超出上限 ${self.monthly_cost_limit}",
            })
        return warnings if warnings else None

    def summary(self) -> CostSummary:
        """获取成本汇总"""
        successful = sum(1 for r in self._records if r.success)
        return CostSummary(
            total_calls=len(self._records),
            successful_calls=successful,
            failed_calls=len(self._records) - successful,
            total_prompt_tokens=sum(r.prompt_tokens for r in self._records),
            total_completion_tokens=sum(r.completion_tokens for r in self._records),
            total_tokens=sum(r.total_tokens for r in self._records),
            total_cost_usd=sum(r.cost_usd for r in self._records),
            by_provider=dict(self._by_provider),
            by_model=dict(self._by_model),
            by_intent=dict(self._by_intent),
        )

    def summary_by_date(self, days: int = 7) -> dict[str, float]:
        """获取最近 N 天的成本趋势"""
        return {
            (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"):
                self._daily_cost.get((datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d"), 0.0)
            for i in range(days)
        }

    def get_recent_records(self, limit: int = 10) -> list[dict]:
        """获取最近的调用记录"""
        return [
            {
                "timestamp": r.timestamp,
                "model": r.model,
                "tokens": r.total_tokens,
                "cost_usd": r.cost_usd,
                "duration_ms": r.duration_ms,
                "success": r.success,
                "intent": r.intent_type,
            }
            for r in self._records[-limit:]
        ]

    def reset(self) -> None:
        """重置统计数据"""
        self._records.clear()
        self._daily_cost.clear()
        self._monthly_cost.clear()
        self._by_provider.clear()
        self._by_model.clear()
        self._by_intent.clear()

    def export_csv(self, filepath: str) -> None:
        """导出记录到 CSV"""
        with open(filepath, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=[
                "timestamp", "provider", "model", "prompt_tokens",
                "completion_tokens", "total_tokens", "duration_ms",
                "cost_usd", "success", "error", "intent_type"
            ])
            writer.writeheader()
            for r in self._records:
                writer.writerow({
                    "timestamp": r.timestamp, "provider": r.provider,
                    "model": r.model, "prompt_tokens": r.prompt_tokens,
                    "completion_tokens": r.completion_tokens,
                    "total_tokens": r.total_tokens, "duration_ms": r.duration_ms,
                    "cost_usd": r.cost_usd, "success": r.success,
                    "error": r.error or "", "intent_type": r.intent_type or "",
                })


# 全局成本追踪器实例
_cost_tracker: Optional[LLMCostTracker] = None


def get_cost_tracker() -> LLMCostTracker:
    """获取全局成本追踪器"""
    global _cost_tracker
    if _cost_tracker is None:
        _cost_tracker = LLMCostTracker()
    return _cost_tracker


def record_llm_call(
    provider: str,
    model: str,
    prompt_tokens: int,
    completion_tokens: int,
    duration_ms: float,
    success: bool = True,
    error: Optional[str] = None,
    intent_type: Optional[str] = None,
) -> LLMCallRecord:
    """快速记录 LLM 调用"""
    return get_cost_tracker().record(
        provider=provider, model=model,
        prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
        duration_ms=duration_ms, success=success, error=error, intent_type=intent_type,
    )
