"""Operation Trace Service

提供查询执行全链路追踪能力，记录每个步骤的输入输出和时间消耗。
"""

from __future__ import annotations

import threading
import uuid
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any

from micro_genbi import get_logger

logger = get_logger(__name__)


class StepType(str, Enum):
    """操作步骤类型"""
    INTENT_CLASSIFICATION = "intent_classification"
    SCHEMA_RETRIEVAL = "schema_retrieval"
    SQL_GENERATION = "sql_generation"
    SQL_VALIDATION = "sql_validation"
    SQL_EXECUTION = "sql_execution"
    CHART_GENERATION = "chart_generation"
    PROMPT_SECURITY_CHECK = "prompt_security_check"
    DATA_MASKING = "data_masking"


class TraceStatus(str, Enum):
    """追踪状态"""
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class OperationStep:
    """操作步骤数据模型"""
    id: str
    type: StepType
    input_summary: str
    output_summary: str
    duration_ms: int
    status: TraceStatus
    metadata: dict[str, Any] = field(default_factory=dict)
    started_at: datetime = field(default_factory=datetime.now)


@dataclass
class OperationTrace:
    """操作追踪数据模型"""
    id: str
    operation_id: str
    operation_type: str
    steps: list[OperationStep] = field(default_factory=list)
    started_at: datetime = field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    total_duration_ms: int = 0
    status: TraceStatus = TraceStatus.RUNNING
    metadata: dict[str, Any] = field(default_factory=dict)


class OperationTraceService:
    """
    操作追踪服务

    提供以下功能：
    - 启动追踪并获取追踪 ID
    - 记录各步骤的输入输出和耗时
    - 结束追踪并生成汇总
    - 支持上下文管理器方式使用

    使用内存存储，线程安全。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._traces: dict[str, OperationTrace] = {}
        self._step_counter: dict[str, int] = {}

    def start_trace(
        self,
        operation_id: str,
        operation_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ) -> str:
        """
        启动一个新的操作追踪

        Args:
            operation_id: 业务操作 ID
            operation_type: 操作类型
            metadata: 额外的元数据

        Returns:
            str: 追踪 ID
        """
        trace_id = str(uuid.uuid4())

        with self._lock:
            trace = OperationTrace(
                id=trace_id,
                operation_id=operation_id,
                operation_type=operation_type,
                metadata=metadata or {},
            )
            self._traces[trace_id] = trace
            self._step_counter[trace_id] = 0

        logger.debug(f"启动追踪: trace_id={trace_id}, operation_id={operation_id}")
        return trace_id

    def add_step(
        self,
        trace_id: str,
        step: OperationStep,
    ) -> None:
        """
        向追踪添加一个步骤

        Args:
            trace_id: 追踪 ID
            step: 操作步骤
        """
        with self._lock:
            if trace_id not in self._traces:
                logger.warning(f"追踪不存在: {trace_id}")
                return

            self._traces[trace_id].steps.append(step)

    def get_trace(self, trace_id: str) -> Optional[OperationTrace]:
        """
        获取追踪详情

        Args:
            trace_id: 追踪 ID

        Returns:
            OperationTrace: 追踪信息，不存在则返回 None
        """
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                return None

            self._compute_duration(trace)
            return trace

    def finish_trace(
        self,
        trace_id: str,
        status: str = "success",
    ) -> Optional[OperationTrace]:
        """
        结束追踪

        Args:
            trace_id: 追踪 ID
            status: 最终状态

        Returns:
            OperationTrace: 更新后的追踪信息
        """
        with self._lock:
            trace = self._traces.get(trace_id)
            if trace is None:
                logger.warning(f"追踪不存在: {trace_id}")
                return None

            trace.finished_at = datetime.now()
            trace.status = TraceStatus(status)
            self._compute_duration(trace)

            trace.metadata["summary"] = self._summarize_trace(trace)

        logger.debug(f"结束追踪: trace_id={trace_id}, status={status}")
        return trace

    @contextmanager
    def trace(
        self,
        operation_id: str,
        operation_type: str,
        metadata: Optional[dict[str, Any]] = None,
    ):
        """
        上下文管理器方式创建追踪

        用法:
            with trace_service.trace("query-123", "sql_generation") as trace_id:
                # 执行操作
                trace_service.add_step(trace_id, step1)
                trace_service.add_step(trace_id, step2)

        Args:
            operation_id: 业务操作 ID
            operation_type: 操作类型
            metadata: 额外的元数据

        Yields:
            str: 追踪 ID
        """
        trace_id = self.start_trace(operation_id, operation_type, metadata)
        try:
            yield trace_id
            self.finish_trace(trace_id, "success")
        except Exception as e:
            logger.error(f"追踪异常: trace_id={trace_id}, error={e}")
            self.finish_trace(trace_id, "failed")
            raise

    def create_step(
        self,
        trace_id: str,
        step_type: StepType,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        status: str = "success",
        metadata: Optional[dict[str, Any]] = None,
    ) -> OperationStep:
        """
        创建并添加一个步骤（便捷方法）

        Args:
            trace_id: 追踪 ID
            step_type: 步骤类型
            input_summary: 输入摘要
            output_summary: 输出摘要
            duration_ms: 耗时（毫秒）
            status: 步骤状态
            metadata: 额外元数据

        Returns:
            OperationStep: 创建的步骤
        """
        with self._lock:
            if trace_id not in self._step_counter:
                self._step_counter[trace_id] = 0
            self._step_counter[trace_id] += 1
            step_id = f"{trace_id}-step-{self._step_counter[trace_id]}"

        step = OperationStep(
            id=step_id,
            type=step_type,
            input_summary=input_summary,
            output_summary=output_summary,
            duration_ms=duration_ms,
            status=TraceStatus(status),
            metadata=metadata or {},
        )

        self.add_step(trace_id, step)
        return step

    def _compute_duration(self, trace: OperationTrace) -> None:
        """
        计算追踪的总耗时和各步骤的相对耗时

        Args:
            trace: 追踪对象
        """
        if not trace.steps:
            trace.total_duration_ms = 0
            return

        total = sum(step.duration_ms for step in trace.steps)
        trace.total_duration_ms = total

        for step in trace.steps:
            step.duration_ms = step.duration_ms

    def _summarize_trace(self, trace: OperationTrace) -> str:
        """
        生成追踪汇总文本

        Args:
            trace: 追踪对象

        Returns:
            str: 汇总文本
        """
        if not trace.steps:
            return "无执行步骤"

        step_summaries = []
        for step in trace.steps:
            step_summaries.append(
                f"{step.type.value}: {step.duration_ms}ms ({step.status.value})"
            )

        parts = [
            f"总耗时: {trace.total_duration_ms}ms",
            f"步骤数: {len(trace.steps)}",
            f"状态: {trace.status.value}",
        ]

        if trace.finished_at and trace.started_at:
            delta = trace.finished_at - trace.started_at
            parts.append(f"实际耗时: {int(delta.total_seconds() * 1000)}ms")

        return " | ".join(parts)

    def list_traces(
        self,
        operation_id: Optional[str] = None,
        operation_type: Optional[str] = None,
        limit: int = 100,
    ) -> list[OperationTrace]:
        """
        列出追踪记录

        Args:
            operation_id: 按业务操作 ID 过滤
            operation_type: 按操作类型过滤
            limit: 返回数量限制

        Returns:
            list[OperationTrace]: 追踪列表
        """
        with self._lock:
            traces = list(self._traces.values())

            if operation_id:
                traces = [t for t in traces if t.operation_id == operation_id]

            if operation_type:
                traces = [t for t in traces if t.operation_type == operation_type]

            traces.sort(key=lambda t: t.started_at, reverse=True)
            return traces[:limit]

    def clear_traces(self, before: Optional[datetime] = None) -> int:
        """
        清理追踪记录

        Args:
            before: 仅清理此时间之前的记录，None 则清理所有

        Returns:
            int: 清理的记录数
        """
        with self._lock:
            if before is None:
                count = len(self._traces)
                self._traces.clear()
                self._step_counter.clear()
                return count

            to_remove = [
                tid for tid, trace in self._traces.items()
                if trace.started_at < before
            ]

            for tid in to_remove:
                del self._traces[tid]
                self._step_counter.pop(tid, None)

            return len(to_remove)
