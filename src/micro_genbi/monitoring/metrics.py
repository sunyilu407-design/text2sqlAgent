"""Metrics 指标追踪模块"""

from __future__ import annotations

import time
from typing import Optional, Callable
from dataclasses import dataclass, field
from enum import Enum
from functools import wraps
import asyncio
from collections import defaultdict


class MetricType(Enum):
    """指标类型"""
    COUNTER = "counter"      # 计数器
    GAUGE = "gauge"          # 瞬时值
    HISTOGRAM = "histogram"   # 直方图
    TIMER = "timer"           # 计时器


@dataclass
class Metric:
    """指标数据"""
    name: str
    type: MetricType
    value: float = 0.0
    count: int = 0
    total: float = 0.0
    min_value: float = float("inf")
    max_value: float = float("-inf")
    tags: dict = field(default_factory=dict)


class MetricsCollector:
    """
    内存指标收集器

    提供计数器、直方图、计时器等功能。
    支持多维度标签。
    """

    def __init__(self):
        self._metrics: dict[str, Metric] = {}
        self._histograms: dict[str, list[float]] = defaultdict(list)

    def counter(
        self,
        name: str,
        value: float = 1.0,
        tags: Optional[dict] = None
    ) -> None:
        """增加计数器"""
        key = self._make_key(name, tags)
        if key not in self._metrics:
            self._metrics[key] = Metric(
                name=name,
                type=MetricType.COUNTER,
                tags=tags or {}
            )
        self._metrics[key].value += value
        self._metrics[key].count += 1

    def gauge(
        self,
        name: str,
        value: float,
        tags: Optional[dict] = None
    ) -> None:
        """设置瞬时值"""
        key = self._make_key(name, tags)
        self._metrics[key] = Metric(
            name=name,
            type=MetricType.GAUGE,
            value=value,
            tags=tags or {}
        )

    def histogram(
        self,
        name: str,
        value: float,
        tags: Optional[dict] = None
    ) -> None:
        """记录直方图值"""
        key = self._make_key(name, tags)
        if key not in self._metrics:
            self._metrics[key] = Metric(
                name=name,
                type=MetricType.HISTOGRAM,
                tags=tags or {}
            )

        m = self._metrics[key]
        m.count += 1
        m.total += value
        m.value = value  # 最新值

        # 更新统计
        m.min_value = min(m.min_value, value)
        m.max_value = max(m.max_value, value)

        # 存储原始值用于计算百分位数
        self._histograms[key].append(value)

    def timer(self, name: str, duration_ms: float, tags: Optional[dict] = None) -> None:
        """记录计时"""
        self.histogram(name, duration_ms, tags)

    def _make_key(self, name: str, tags: Optional[dict] = None) -> str:
        """生成指标 key"""
        if not tags:
            return name
        tag_str = ",".join(f"{k}={v}" for k, v in sorted(tags.items()))
        return f"{name}{{{tag_str}}}"

    def get(self, name: str, tags: Optional[dict] = None) -> Optional[Metric]:
        """获取指标"""
        return self._metrics.get(self._make_key(name, tags))

    def get_all(self) -> dict[str, Metric]:
        """获取所有指标"""
        return dict(self._metrics)

    def reset(self) -> None:
        """重置所有指标"""
        self._metrics.clear()
        self._histograms.clear()

    def get_percentile(self, name: str, percentile: float, tags: Optional[dict] = None) -> Optional[float]:
        """获取百分位数"""
        key = self._make_key(name, tags)
        values = self._histograms.get(key, [])
        if not values:
            return None
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * percentile / 100)
        return sorted_values[min(idx, len(sorted_values) - 1)]

    def summary(self) -> str:
        """生成指标摘要"""
        lines = ["=== Metrics Summary ==="]
        for m in self._metrics.values():
            if m.type == MetricType.COUNTER:
                lines.append(f"  {m.name}: {m.value} (count={m.count})")
            elif m.type == MetricType.GAUGE:
                lines.append(f"  {m.name}: {m.value}")
            elif m.type == MetricType.HISTOGRAM:
                avg = m.total / m.count if m.count > 0 else 0
                p50 = self.get_percentile(m.name, 50, m.tags)
                p95 = self.get_percentile(m.name, 95, m.tags)
                p99 = self.get_percentile(m.name, 99, m.tags)
                lines.append(
                    f"  {m.name}: count={m.count}, avg={avg:.2f}ms, "
                    f"min={m.min_value:.2f}ms, p50={p50:.2f}ms, p95={p95:.2f}ms, p99={p99:.2f}ms"
                )
        return "\n".join(lines)


# 全局指标收集器实例
_metrics = MetricsCollector()


def get_metrics() -> MetricsCollector:
    """获取全局指标收集器"""
    return _metrics


class TimerContext:
    """可作为装饰器和上下文管理器使用的计时器"""

    def __init__(self, name: str, tags: Optional[dict] = None):
        self.name = name
        self.tags = tags
        self.start = time.perf_counter()
        self.elapsed: float = 0.0

    def __enter__(self) -> TimerContext:
        return self

    def __exit__(self, *args) -> None:
        self.elapsed = (time.perf_counter() - self.start) * 1000
        _metrics.timer(self.name, self.elapsed, self.tags)

    def __call__(self, func: Callable) -> Callable:
        """作为装饰器使用"""
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return await func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                _metrics.timer(self.name, duration_ms, self.tags)

        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            start = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start) * 1000
                _metrics.timer(self.name, duration_ms, self.tags)

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper


def track_duration(name: str, tags: Optional[dict] = None):
    """追踪函数执行时间，支持装饰器和上下文管理器两种用法。

    装饰器用法:
        @track_duration("my.operation")
        async def my_func():
            ...

    上下文管理器用法:
        with track_duration("my.operation") as timer:
            do_work()
        # timer.elapsed 包含耗时（毫秒）
    """
    return TimerContext(name, tags)


# 常用指标常量
class Metrics:
    """预定义的指标名称"""

    # SQL 生成
    SQL_GENERATION_DURATION = "sql.generation.duration"
    SQL_GENERATION_SUCCESS = "sql.generation.success"
    SQL_GENERATION_ERROR = "sql.generation.error"
    SQL_GENERATION_RETRY = "sql.generation.retry"

    # 数据库执行
    DB_EXECUTION_DURATION = "db.execution.duration"
    DB_EXECUTION_SUCCESS = "db.execution.success"
    DB_EXECUTION_ERROR = "db.execution.error"
    DB_EXECUTION_TIMEOUT = "db.execution.timeout"

    # LLM 调用
    LLM_CALL_DURATION = "llm.call.duration"
    LLM_CALL_SUCCESS = "llm.call.success"
    LLM_CALL_ERROR = "llm.call.error"
    LLM_TOKEN_USED = "llm.token.used"

    # 意图分类
    INTENT_CLASSIFICATION_DURATION = "intent.classification.duration"
    INTENT_CLASSIFICATION_LAYER1 = "intent.classification.layer1"
    INTENT_CLASSIFICATION_LAYER2 = "intent.classification.layer2"
    INTENT_CLASSIFICATION_LAYER3 = "intent.classification.layer3"

    # 图表生成
    CHART_GENERATION_DURATION = "chart.generation.duration"
    CHART_GENERATION_SUCCESS = "chart.generation.success"
    CHART_GENERATION_ERROR = "chart.generation.error"

    # 多库查询
    MULTI_DB_SUBQUERY_DURATION = "multi_db.subquery.duration"
    MULTI_DB_MERGE_DURATION = "multi_db.merge.duration"
    MULTI_DB_ERROR = "multi_db.error"

    # 预测服务
    PREDICTION_DURATION = "prediction.duration"
    PREDICTION_ERROR = "prediction.error"
    PREDICTION_ACCURACY = "prediction.accuracy"

    # HTTP 请求
    HTTP_REQUEST_DURATION = "http.request.duration"
    HTTP_REQUEST_ERROR = "http.request.error"
