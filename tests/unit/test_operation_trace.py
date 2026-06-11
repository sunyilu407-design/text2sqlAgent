"""OperationTrace Service 单元测试"""

import pytest
import time
from micro_genbi.service.operation_trace import (
    OperationTraceService,
    OperationStep,
    StepType,
    OperationTrace,
    TraceStatus,
)


class TestOperationTraceService:
    """操作追踪服务测试"""

    @pytest.fixture
    def service(self) -> OperationTraceService:
        return OperationTraceService()

    def test_start_trace(self, service: OperationTraceService):
        """测试开始追踪"""
        trace_id = service.start_trace(
            operation_id="test_op_1",
            operation_type="test_operation",
        )
        assert trace_id is not None
        assert len(trace_id) > 0

    def test_add_step(self, service: OperationTraceService):
        """测试添加步骤"""
        trace_id = service.start_trace("test_op_2", "test_op")
        step = OperationStep(
            id="step_1",
            type=StepType.INTENT_CLASSIFICATION,
            input_summary="统计销售",
            output_summary="SINGLE",
            duration_ms=0,
            status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step)
        trace = service.get_trace(trace_id)
        assert trace is not None
        assert len(trace.steps) == 1
        assert trace.steps[0].type == StepType.INTENT_CLASSIFICATION

    def test_add_step_with_output(self, service: OperationTraceService):
        """测试带输出的步骤"""
        trace_id = service.start_trace("test_op_3", "test_op")
        step = OperationStep(
            id="step_2",
            type=StepType.SQL_GENERATION,
            input_summary="schema context",
            output_summary="SELECT 1",
            duration_ms=0,
            status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step)
        trace = service.get_trace(trace_id)
        assert len(trace.steps) == 1

    def test_get_trace(self, service: OperationTraceService):
        """测试获取追踪记录"""
        trace_id = service.start_trace("full_test", "full_op")
        step = OperationStep(
            id="s1",
            type=StepType.INTENT_CLASSIFICATION,
            input_summary="query",
            output_summary="result",
            duration_ms=0,
            status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step)
        trace = service.get_trace(trace_id)
        assert trace is not None
        assert trace.id == trace_id
        assert trace.operation_type == "full_op"

    def test_get_nonexistent_trace(self, service: OperationTraceService):
        """获取不存在的追踪返回 None"""
        trace = service.get_trace("nonexistent_id")
        assert trace is None

    def test_finish_trace(self, service: OperationTraceService):
        """测试完成追踪"""
        trace_id = service.start_trace("finish_test", "finish_op")
        step = OperationStep(
            id="s2",
            type=StepType.SCHEMA_RETRIEVAL,
            input_summary="",
            output_summary="",
            duration_ms=0,
            status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step)
        finished = service.finish_trace(trace_id, status="success")
        assert finished is not None
        assert finished.status == TraceStatus.SUCCESS

    def test_finish_trace_with_error(self, service: OperationTraceService):
        """测试追踪失败"""
        trace_id = service.start_trace("fail_test", "fail_op")
        finished = service.finish_trace(trace_id, status="failed")
        assert finished.status == TraceStatus.FAILED

    def test_trace_total_duration(self, service: OperationTraceService):
        """测试追踪总时长"""
        trace_id = service.start_trace("timing_test", "timing_op")
        step1 = OperationStep(
            id="s3", type=StepType.INTENT_CLASSIFICATION,
            input_summary="", output_summary="", duration_ms=0, status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step1)
        step2 = OperationStep(
            id="s4", type=StepType.SQL_GENERATION,
            input_summary="", output_summary="", duration_ms=0, status=TraceStatus.RUNNING,
        )
        service.add_step(trace_id, step2)
        trace = service.get_trace(trace_id)
        assert trace.total_duration_ms >= 0

    def test_list_traces(self, service: OperationTraceService):
        """测试列出追踪记录"""
        for i in range(5):
            service.start_trace(f"list_op_{i}", "list_operation")
        traces = service.list_traces()
        assert len(traces) >= 5

    def test_list_traces_by_operation_type(self, service: OperationTraceService):
        """测试按操作类型过滤追踪"""
        service.start_trace("type_a", "type_a")
        service.start_trace("type_b", "type_b")
        traces = service.list_traces(operation_type="type_a")
        assert all(t.operation_type == "type_a" for t in traces)

    def test_step_type_enum_values(self):
        """测试步骤类型枚举值"""
        assert StepType.INTENT_CLASSIFICATION.value == "intent_classification"
        assert StepType.SCHEMA_RETRIEVAL.value == "schema_retrieval"
        assert StepType.SQL_GENERATION.value == "sql_generation"
        assert StepType.SQL_VALIDATION.value == "sql_validation"
        assert StepType.SQL_EXECUTION.value == "sql_execution"
        assert StepType.CHART_GENERATION.value == "chart_generation"
        assert StepType.PROMPT_SECURITY_CHECK.value == "prompt_security_check"

    def test_operation_trace_model(self):
        """测试 OperationTrace 数据模型"""
        trace = OperationTrace(
            id="test_id",
            operation_id="op_1",
            operation_type="test",
            metadata={"key": "value"},
        )
        assert trace.id == "test_id"
        assert trace.operation_id == "op_1"
        assert trace.metadata["key"] == "value"
        assert trace.total_duration_ms == 0

    def test_operation_step_model(self):
        """测试 OperationStep 数据模型"""
        step = OperationStep(
            id="step_id",
            type=StepType.SQL_EXECUTION,
            input_summary="SELECT 1",
            output_summary="5 rows",
            duration_ms=10,
            status=TraceStatus.SUCCESS,
        )
        assert step.id == "step_id"
        assert step.type == StepType.SQL_EXECUTION
        assert step.input_summary == "SELECT 1"
        assert step.duration_ms == 10
        assert step.status == TraceStatus.SUCCESS
