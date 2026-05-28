"""多数据库执行引擎

根据 QueryPlan 执行跨库查询，负责：
1. 并发执行各子查询
2. 归并结果（UNION ALL / stream_join）
3. SQL 安全验证
4. 错误处理与重试
"""

from __future__ import annotations

import asyncio
import time
import logging
from dataclasses import dataclass, field
from typing import Optional, Any

from micro_genbi.db.router import QueryPlan, SubQueryPlan, QueryMode
from micro_genbi.db.connection_factory import MultiDBConnectionFactory
from micro_genbi.security import SQLSafetyValidator
from micro_genbi.errors import (
    GenBIError,
    GenBIReRetry,
    SQLExecutionError,
    SQLValidationError,
)

logger = logging.getLogger(__name__)


@dataclass
class SubQueryResult:
    """子查询结果"""
    connection_id: str
    connection_name: str
    sql: str
    data: list[dict[str, Any]]
    latency_ms: int
    error: Optional[str] = None
    success: bool = True


@dataclass
class ExecutionResult:
    """
    多库查询执行结果。

    归并后的数据可直接返回给前端。
    """
    mode: QueryMode
    data: list[dict[str, Any]]
    columns: list[str]
    row_count: int
    latency_ms: int
    sub_results: list[SubQueryResult] = field(default_factory=list)
    sql: str = ""    # 展示用 SQL（单库模式）或归并 SQL
    summary: str = ""  # 执行摘要

    @property
    def is_success(self) -> bool:
        return all(r.success for r in self.sub_results)


class MultiDBExecutionEngine:
    """
    多数据库执行引擎。

    接收 QueryPlan，并发执行子查询，然后根据 merge_strategy 归并结果。

    使用方式：
        engine = MultiDBExecutionEngine(factory)

        # 单库执行
        result = await engine.execute(plan, {"conn-uuid": "SELECT ..."})

        # 多库归并执行
        result = await engine.execute(plan, {
            "conn-a": "SELECT ... FROM orders",
            "conn-b": "SELECT ... FROM orders",
        })
    """

    def __init__(
        self,
        factory: MultiDBConnectionFactory,
        safety_validator: Optional[SQLSafetyValidator] = None,
        max_limit: int = 1000,
    ):
        self._factory = factory
        self._safety = safety_validator or SQLSafetyValidator(
            max_limit=max_limit,
            max_join_count=10,
        )

    async def execute(
        self,
        plan: QueryPlan,
        sql_by_connection: dict[str, str],
    ) -> ExecutionResult:
        """
        执行查询计划。

        Args:
            plan: 路由决策生成的执行计划
            sql_by_connection: {connection_id: sql} 映射

        Returns:
            ExecutionResult: 归并后的执行结果
        """
        start = time.time()

        # 检查是否为拒绝查询
        if plan.mode == QueryMode.FEDERATED and not plan.sub_plans:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary=plan.description,
            )

        if plan.mode == QueryMode.SINGLE:
            return await self._execute_single(plan, sql_by_connection, start)
        elif plan.mode == QueryMode.AGGREGATE:
            return await self._execute_aggregate(plan, sql_by_connection, start)
        elif plan.mode == QueryMode.FEDERATED:
            return await self._execute_federated(plan, sql_by_connection, start)
        else:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary=f"未知模式: {plan.mode}",
            )

    async def _execute_single(
        self,
        plan: QueryPlan,
        sql_by_connection: dict[str, str],
        start: float,
    ) -> ExecutionResult:
        """单库查询执行"""
        if not plan.sub_plans:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary="无子查询计划",
            )

        sub = plan.sub_plans[0]
        sql = sql_by_connection.get(sub.connection_id, "")
        if not sql:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary="未提供 SQL",
            )

        # SQL 安全验证
        validated_sql = self._validate_sql(sql)

        # 执行
        try:
            data = await self._factory.execute(sub.connection_id, validated_sql)
            columns = list(data[0].keys()) if data else []

            return ExecutionResult(
                mode=plan.mode,
                data=data,
                columns=columns,
                row_count=len(data),
                latency_ms=int((time.time() - start) * 1000),
                sub_results=[SubQueryResult(
                    connection_id=sub.connection_id,
                    connection_name=sub.connection_name,
                    sql=validated_sql,
                    data=data,
                    latency_ms=int((time.time() - start) * 1000),
                    success=True,
                )],
                sql=validated_sql,
                summary=f"单库查询成功，返回 {len(data)} 行",
            )
        except Exception as e:
            logger.error(f"单库查询失败: {e}")
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                sub_results=[SubQueryResult(
                    connection_id=sub.connection_id,
                    connection_name=sub.connection_name,
                    sql=validated_sql,
                    data=[],
                    latency_ms=int((time.time() - start) * 1000),
                    error=str(e),
                    success=False,
                )],
                sql=validated_sql,
                summary=f"查询失败: {e}",
            )

    async def _execute_aggregate(
        self,
        plan: QueryPlan,
        sql_by_connection: dict[str, str],
        start: float,
    ) -> ExecutionResult:
        """
        同构多库聚合执行。

        策略：在各库上并发执行子查询（已包含聚合函数如 SUM/COUNT），
        然后在 Python 层 UNION ALL 归并结果。
        """
        if not plan.sub_plans:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary="无子查询计划",
            )

        # 验证所有 SQL
        validated_sqls: dict[str, str] = {}
        for sub in plan.sub_plans:
            sql = sql_by_connection.get(sub.connection_id, "")
            if sql:
                validated_sqls[sub.connection_id] = self._validate_sql(sql)

        # 并发执行所有子查询
        sub_tasks = []
        for sub in plan.sub_plans:
            if sub.connection_id in validated_sqls:
                sub_tasks.append(
                    self._execute_subquery(
                        sub, validated_sqls[sub.connection_id], start
                    )
                )

        sub_results = await asyncio.gather(*sub_tasks, return_exceptions=True)

        # 过滤异常
        valid_results: list[SubQueryResult] = []
        for r in sub_results:
            if isinstance(r, SubQueryResult):
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.error(f"子查询异常: {r}")

        # UNION ALL 归并
        merged_data = self._merge_union_all(valid_results)
        columns = list(merged_data[0].keys()) if merged_data else []

        return ExecutionResult(
            mode=plan.mode,
            data=merged_data,
            columns=columns,
            row_count=len(merged_data),
            latency_ms=int((time.time() - start) * 1000),
            sub_results=valid_results,
            sql=f"/* {len(valid_results)} 个库 UNION ALL */",
            summary=(
                f"同构聚合成功：{len(valid_results)} 个库，"
                f"返回 {len(merged_data)} 行"
            ),
        )

    async def _execute_federated(
        self,
        plan: QueryPlan,
        sql_by_connection: dict[str, str],
        start: float,
    ) -> ExecutionResult:
        """
        异构多库联邦执行。

        策略：并发执行各库子查询，然后在 Python 层按跨库关联键流式归并。
        归并逻辑依赖 CrossDBRelation 中配置的 source/target column。
        """
        if not plan.sub_plans:
            return ExecutionResult(
                mode=plan.mode,
                data=[],
                columns=[],
                row_count=0,
                latency_ms=int((time.time() - start) * 1000),
                summary="无子查询计划",
            )

        # 验证所有 SQL
        validated_sqls: dict[str, str] = {}
        for sub in plan.sub_plans:
            sql = sql_by_connection.get(sub.connection_id, "")
            if sql:
                validated_sqls[sub.connection_id] = self._validate_sql(sql)

        # 并发执行所有子查询
        sub_tasks = []
        for sub in plan.sub_plans:
            if sub.connection_id in validated_sqls:
                sub_tasks.append(
                    self._execute_subquery(
                        sub, validated_sqls[sub.connection_id], start
                    )
                )

        sub_results = await asyncio.gather(*sub_tasks, return_exceptions=True)

        valid_results: list[SubQueryResult] = []
        for r in sub_results:
            if isinstance(r, SubQueryResult):
                valid_results.append(r)
            elif isinstance(r, Exception):
                logger.error(f"子查询异常: {r}")

        # 流式归并（基于 CrossDBRelation）
        merged_data = await self._merge_stream_join(valid_results, plan)
        columns = list(merged_data[0].keys()) if merged_data else []

        return ExecutionResult(
            mode=plan.mode,
            data=merged_data,
            columns=columns,
            row_count=len(merged_data),
            latency_ms=int((time.time() - start) * 1000),
            sub_results=valid_results,
            sql=f"/* {len(valid_results)} 个库 STREAM JOIN */",
            summary=(
                f"异构联邦成功：{len(valid_results)} 个库，"
                f"返回 {len(merged_data)} 行"
            ),
        )

    async def _execute_subquery(
        self,
        sub: SubQueryPlan,
        sql: str,
        start: float,
    ) -> SubQueryResult:
        """执行单个子查询"""
        sub_start = time.time()
        try:
            data = await self._factory.execute(sub.connection_id, sql)
            return SubQueryResult(
                connection_id=sub.connection_id,
                connection_name=sub.connection_name,
                sql=sql,
                data=data,
                latency_ms=int((time.time() - sub_start) * 1000),
                success=True,
            )
        except Exception as e:
            logger.error(f"SubQuery [{sub.connection_name}] failed: {e}")
            return SubQueryResult(
                connection_id=sub.connection_id,
                connection_name=sub.connection_name,
                sql=sql,
                data=[],
                latency_ms=int((time.time() - sub_start) * 1000),
                error=str(e),
                success=False,
            )

    def _validate_sql(self, sql: str) -> str:
        """SQL 安全验证"""
        return self._safety.validate_and_raise(sql)

    def _merge_union_all(
        self, results: list[SubQueryResult]
    ) -> list[dict[str, Any]]:
        """
        UNION ALL 归并。

        前提：所有子查询返回相同的列结构（通常已包含 GROUP BY 的聚合值）。
        """
        merged: list[dict[str, Any]] = []
        for result in results:
            merged.extend(result.data)
        return merged

    async def _merge_stream_join(
        self,
        results: list[SubQueryResult],
        plan: QueryPlan,
    ) -> list[dict[str, Any]]:
        """
        流式归并（STREAM JOIN）。

        基于 CrossDBRelation 中配置的 source_column / target_column，
        对多个子查询结果进行 JOIN 归并。

        策略：选择数据量最小的结果集作为驱动表，
        其他表按关联键哈希 join。
        """
        if len(results) == 1:
            return results[0].data
        if not results:
            return []

        # 收集所有跨库关联信息
        rel_map: dict[str, tuple[str, str, str, str]] = {}
        # rel_map[conn_id] = (join_key, other_conn_id, other_col, cardinality)

        # 构建连接 id → sub 映射
        conn_sub_map = {r.connection_id: r for r in results}

        # 获取归并键（从 plan 的 sub_plans 中获取）
        # 简化：使用第一个结果的列作为基础，逐个 JOIN
        base = results[0]
        merged = [dict(row) for row in base.data]

        for result in results[1:]:
            if not result.data:
                continue

            # 找归并键：从 CrossDBRelation 中查找两个连接间的关联字段
            join_key = self._find_join_key(base.connection_id, result.connection_id, plan)
            other_key = self._find_other_join_key(
                base.connection_id, result.connection_id, plan
            )

            # 在驱动表 merged 中查找关联键
            base_keys = {row.get(join_key) for row in merged if join_key in row}
            result_keys = {row.get(other_key) for row in result.data if other_key in row}

            # 构建哈希表
            result_map: dict[Any, dict] = {}
            for row in result.data:
                key_val = row.get(other_key)
                if key_val is not None:
                    result_map[key_val] = row

            # JOIN
            new_merged = []
            for row in merged:
                key_val = row.get(join_key)
                if key_val in result_map:
                    joined = dict(row)
                    for col, val in result_map[key_val].items():
                        if col != other_key:
                            joined[f"{result.connection_name}.{col}"] = val
                    new_merged.append(joined)
                # 可选：保留无关联的行（LEFT JOIN 语义）
                else:
                    new_merged.append(row)

            merged = new_merged

        return merged

    def _find_join_key(
        self, conn_a: str, conn_b: str, plan: QueryPlan
    ) -> str:
        """查找两个连接之间的 JOIN 键（conn_a 侧）"""
        for sub in plan.sub_plans:
            if sub.connection_id == conn_a:
                return sub.merge_column or "id"
        return "id"

    def _find_other_join_key(
        self, conn_a: str, conn_b: str, plan: QueryPlan
    ) -> str:
        """查找两个连接之间的 JOIN 键（conn_b 侧）"""
        for sub in plan.sub_plans:
            if sub.connection_id == conn_b:
                return sub.merge_column or "id"
        return "id"
