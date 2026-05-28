"""多库感知查询服务

MultiDBAskService 是单库 AskService 的多数据库版本。

核心能力：
1. 自动检测查询模式（SINGLE / AGGREGATE / FEDERATED）
2. 调用 MultiDatabaseRouter 生成执行计划
3. 调用 MultiDBExecutionEngine 并发执行并归并结果
4. 调用 LLM 生成 SQL（为每个子查询生成适配该库方言的 SQL）
5. 集成安全验证、数据脱敏、错误自愈
"""

from __future__ import annotations

import time
import logging
import re
from dataclasses import dataclass, field
from typing import Optional, Any

from micro_genbi import get_logger, track_duration
from micro_genbi.models import (
    QueryRequest,
    QueryResponse,
    IntentType,
    IntentClassification,
    ColumnInfo,
)
from micro_genbi.errors import (
    GenBIError,
    GenBIReRetry,
    SQLValidationError,
    SQLExecutionError,
    should_propagate,
    to_retry,
)
from micro_genbi.security import (
    SQLSafetyValidator,
    PromptInjectionDetector,
    DataMasker,
)
from micro_genbi.llm.base import LLMClient, create_llm_client
from micro_genbi.semantic.schema_registry import SchemaRegistry
from micro_genbi.db.router import (
    MultiDatabaseRouter,
    QueryPlan,
    QueryMode,
)
from micro_genbi.db.connection_factory import get_multi_db_factory
from micro_genbi.db.execution import MultiDBExecutionEngine
from micro_genbi.llm.prompts import render_multi_db_prompt, render_sql_prompt

logger = get_logger(__name__)


@dataclass
class ServicePipelineContext:
    """服务流水线上下文"""
    request: QueryRequest
    start_time: float
    user_id: Optional[str]
    role: str
    session_id: Optional[str]
    tenant_id: str

    intent: Optional[IntentClassification] = None
    query_plan: Optional[QueryPlan] = None
    sql_by_connection: dict[str, str] = field(default_factory=dict)
    execution_result: Any = None
    error: Optional[str] = None
    steps_timing: dict[str, int] = field(default_factory=dict)


class MultiDBAskService:
    """
    多库感知查询服务。

    工作流程：
    1. Prompt 安全检查
    2. 意图分类
    3. 路由决策（Router）→ QueryPlan
       - 如果是拒绝查询（未配置跨库关联），直接返回
    4. Schema 检索（为每个涉及的库准备 schema context）
    5. SQL 生成（为每个子查询生成 SQL）
    6. 并发执行（ExecutionEngine）
    7. 结果归并
    8. 数据脱敏
    9. 返回响应
    """

    def __init__(
        self,
        session,                # AsyncSession from FastAPI
        llm_client: Optional[LLMClient] = None,
        schema_registry: Optional[SchemaRegistry] = None,
        default_connection_id: Optional[str] = None,
        max_retries: int = 3,
        enable_security: bool = True,
        enable_masking: bool = True,
    ):
        self.session = session
        self.llm_client = llm_client or create_llm_client()
        self.max_retries = max_retries
        self.enable_security = enable_security
        self.enable_masking = enable_masking

        # Schema Registry
        if schema_registry:
            self.schema_registry = schema_registry
        else:
            self.schema_registry = SchemaRegistry()
            self.schema_registry.load()

        # 路由器
        self.router = MultiDatabaseRouter(
            session=session,
            default_connection_id=default_connection_id,
        )

        # 连接工厂 + 执行引擎
        self.factory = get_multi_db_factory()
        self.executor = MultiDBExecutionEngine(
            factory=self.factory,
        )

        # 安全组件
        self.sql_validator = SQLSafetyValidator(max_limit=1000, max_join_count=10)
        self.prompt_detector = PromptInjectionDetector(enable_oil_depot_sensitive=True)
        self.data_masker = DataMasker(enable_oil_depot=True)

        # 意图分类器
        self.intent_classifier = _IntentClassifier(self.llm_client)

    async def close(self) -> None:
        if self.llm_client:
            await self.llm_client.close()

    async def ask(
        self,
        query: str,
        user_id: Optional[str] = None,
        role: str = "user",
        session_id: Optional[str] = None,
        connection_id: Optional[str] = None,
        tenant_id: str = "default",
        max_retries: Optional[int] = None,
    ) -> QueryResponse:
        """
        执行多库感知查询。

        Args:
            query: 自然语言查询
            user_id: 用户 ID
            role: 用户角色
            session_id: 会话 ID
            connection_id: 明确指定的数据源连接 ID（可空）
            tenant_id: 租户 ID
            max_retries: 最大重试次数

        Returns:
            QueryResponse: 查询响应（包含多库模式信息）
        """
        request = QueryRequest(
            query=query,
            user_id=user_id,
            role=role,
            session_id=session_id,
            connection_id=connection_id,
        )

        ctx = ServicePipelineContext(
            request=request,
            start_time=time.time(),
            user_id=user_id,
            role=role,
            session_id=session_id,
            tenant_id=tenant_id,
        )

        retry_count = 0
        max_r = max_retries or self.max_retries

        while True:
            try:
                return await self._execute_pipeline(ctx)

            except GenBIReRetry as e:
                if should_propagate(e) or not e.can_retry:
                    raise

                if retry_count >= max_r:
                    logger.warning(f"达到最大重试次数: {max_r}")
                    raise

                retry_count += 1
                logger.info(f"重试查询 (第 {retry_count} 次): {query}")
                e.retry_count = retry_count
                raise to_retry(e, max_retries=max_r, retry_count=retry_count)

            except GenBIError as e:
                if should_propagate(e):
                    raise
                raise

            except Exception as e:
                logger.error(f"查询失败: {e}")
                raise

    async def _execute_pipeline(
        self, ctx: ServicePipelineContext
    ) -> QueryResponse:
        """执行完整流水线"""
        query = ctx.request.query
        tenant_id = ctx.tenant_id
        conn_id = ctx.request.connection_id

        # ========== 步骤 1: Prompt 安全检查 ==========
        with track_duration("prompt_security_check") as timer:
            if self.enable_security:
                self.prompt_detector.detect_and_raise(query)
            ctx.steps_timing["prompt_security_check_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 2: 意图分类 ==========
        with track_duration("intent_classification") as timer:
            ctx.intent = await self.intent_classifier.classify(query)
            ctx.steps_timing["intent_classification_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 3: 路由决策 ==========
        with track_duration("query_routing") as timer:
            ctx.query_plan = await self.router.route(
                user_query=query,
                tables=[],          # 由 LLM 从 schema 推断
                tenant_id=tenant_id,
                requested_connection_id=conn_id,
            )
            ctx.steps_timing["query_routing_ms"] = int(timer.elapsed * 1000)
            logger.debug(
                f"路由决策: mode={ctx.query_plan.mode}, "
                f"description={ctx.query_plan.description}"
            )

        # ========== 步骤 3.5: 拒绝查询检查 ==========
        # 跨库查询未配置关联 → 直接返回拒绝原因
        if ctx.query_plan.mode == QueryMode.FEDERATED and not ctx.query_plan.sub_plans:
            return self._build_rejection_response(ctx)

        # ========== 步骤 4: SQL 生成 ==========
        with track_duration("sql_generation") as timer:
            await self._generate_sqls(ctx)
            ctx.steps_timing["sql_generation_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 5: 并发执行 ==========
        with track_duration("sql_execution") as timer:
            ctx.execution_result = await self.executor.execute(
                ctx.query_plan, ctx.sql_by_connection
            )
            ctx.steps_timing["sql_execution_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 6: 数据脱敏 ==========
        with track_duration("data_masking") as timer:
            data = ctx.execution_result.data
            if self.enable_masking:
                data = self.data_masker.mask_result(data, user_role=ctx.role)
            ctx.steps_timing["data_masking_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 7: 构建响应 ==========
        return self._build_response(ctx, data)

    async def _generate_sqls(self, ctx: ServicePipelineContext) -> None:
        """为每个子查询生成 SQL"""
        query = ctx.request.query
        plan = ctx.query_plan

        if plan.mode == QueryMode.SINGLE:
            # 单库：生成一条 SQL
            sub = plan.sub_plans[0]
            dialect = _dialect_from_type(sub.connection_type)
            schema_ctx = self.schema_registry.build_llm_context()
            prompt = render_sql_prompt(query, schema_ctx, dialect)
            raw_sql = await self.llm_client.generate(prompt)
            ctx.sql_by_connection[sub.connection_id] = self._extract_sql(raw_sql.content)

        elif plan.mode == QueryMode.AGGREGATE:
            # 同构聚合：生成一条 SQL，在所有库上执行
            dialect = _dialect_from_type(
                plan.sub_plans[0].connection_type if plan.sub_plans else "postgresql"
            )
            schema_ctx = self.schema_registry.build_llm_context()
            prompt = render_sql_prompt(query, schema_ctx, dialect)
            raw_sql = await self.llm_client.generate(prompt)
            unified_sql = self._extract_sql(raw_sql.content)

            # 所有同构库执行相同的 SQL
            for sub in plan.sub_plans:
                ctx.sql_by_connection[sub.connection_id] = unified_sql

        elif plan.mode == QueryMode.FEDERATED:
            # 异构联邦：为每个库生成适配的 SQL
            for sub in plan.sub_plans:
                dialect = _dialect_from_type(sub.connection_type)
                schema_ctx = self.schema_registry.build_llm_context()
                rels = self.router._get_relations_for_connection(sub.connection_id)
                extra_hint = ""
                if rels:
                    rel_descs = [
                        f"{r['source_table']}.{r['source_column']} "
                        f"→ {r['target_table']}.{r['target_column']}"
                        for r in rels
                    ]
                    extra_hint = (
                        f"\n\n【跨库关联（已配置）】\n" + "\n".join(rel_descs)
                    )
                prompt = render_sql_prompt(query, schema_ctx, dialect) + extra_hint
                raw_sql = await self.llm_client.generate(prompt)
                ctx.sql_by_connection[sub.connection_id] = self._extract_sql(
                    raw_sql.content
                )

    def _extract_sql(self, content: str) -> str:
        """从 LLM 输出中提取 SQL"""
        sql_blocks = re.findall(
            r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE
        )
        if sql_blocks:
            return sql_blocks[0].strip()

        code_blocks = re.findall(
            r'```\s*(.*?)\s*```', content, re.DOTALL
        )
        if code_blocks:
            return code_blocks[0].strip()

        sql = content.strip()
        if sql.startswith('"') and sql.endswith('"'):
            sql = sql[1:-1]
        if sql.startswith("'") and sql.endswith("'"):
            sql = sql[1:-1]
        return sql

    def _build_rejection_response(
        self, ctx: ServicePipelineContext
    ) -> QueryResponse:
        """构建拒绝查询响应"""
        total_time = int((time.time() - ctx.start_time) * 1000)
        emoji, label, color = self.router.get_query_mode_for_display(ctx.query_plan)

        return QueryResponse(
            sql="",
            data=[],
            columns=[],
            row_count=0,
            chart=None,
            summary="查询被拒绝",
            session_id=ctx.session_id,
            execution_time_ms=total_time,
            steps_timing=ctx.steps_timing,
            query_mode=ctx.query_plan.mode.value,
            query_mode_label=label,
            query_mode_emoji=emoji,
            query_mode_color=color,
            is_multi_db=True,
            rejected_reason=ctx.query_plan.description,
        )

    def _build_response(
        self,
        ctx: ServicePipelineContext,
        data: list[dict[str, Any]],
    ) -> QueryResponse:
        """构建成功响应"""
        total_time = int((time.time() - ctx.start_time) * 1000)
        result = ctx.execution_result
        plan = ctx.query_plan
        emoji, label, color = self.router.get_query_mode_for_display(plan)

        # 构建列信息
        columns = [
            ColumnInfo(name=c, data_type="TEXT") for c in result.columns
        ] if result.columns else []

        # 构建子结果摘要
        sub_results_summary = []
        for sub in result.sub_results:
            status_icon = "OK" if sub.success else "FAIL"
            sub_results_summary.append({
                "connection_id": sub.connection_id,
                "connection_name": sub.connection_name,
                "status": status_icon,
                "latency_ms": sub.latency_ms,
                "row_count": len(sub.data),
                "error": sub.error,
            })

        intent_name = (
            ctx.intent.intent.value if ctx.intent else "query"
        )

        return QueryResponse(
            sql=result.sql,
            data=data,
            columns=columns,
            row_count=len(data),
            chart=None,
            summary=result.summary,
            session_id=ctx.session_id,
            execution_time_ms=total_time,
            steps_timing=ctx.steps_timing,
            query_mode=plan.mode.value,
            query_mode_label=label,
            query_mode_emoji=emoji,
            query_mode_color=color,
            is_multi_db=plan.is_multi_db,
            sub_results=sub_results_summary,
        )


class _IntentClassifier:
    """意图分类器（内部使用）"""

    INTENT_PATTERNS = {
        IntentType.AGGREGATION: [
            "统计", "合计", "总计", "sum", "count", "avg", "平均",
            "总数", "汇总", "聚合",
        ],
        IntentType.COMPARISON: [
            "对比", "比较", "差异", "多了", "少了", "增减",
            "增长", "下降", "变化", "compare", "versus", "vs",
        ],
        IntentType.TREND: [
            "趋势", "走势", "变化趋势", "历史", "最近", "环比",
            "同比", "period", "trend", "over time",
        ],
        IntentType.FILTER: [
            "查找", "查询", "筛选", "过滤", "只看", "只要",
            "filter", "where", "find",
        ],
        IntentType.RANKING: [
            "排名", "top", "前三", "倒数", "排序", "最大", "最小",
            "rank", "highest", "lowest", "order by",
        ],
    }

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def classify(self, query: str) -> IntentClassification:
        # 规则匹配
        for intent, keywords in self.INTENT_PATTERNS.items():
            for keyword in keywords:
                if keyword.lower() in query.lower():
                    return IntentClassification(
                        intent=intent,
                        confidence=0.85,
                        reasoning=f"关键词匹配: {keyword}",
                    )
        # 默认
        return IntentClassification(
            intent=IntentType.QUERY,
            confidence=0.5,
            reasoning="默认分类",
        )


def _dialect_from_type(db_type: str) -> str:
    """数据库类型 → 方言名"""
    mapping = {
        "postgresql": "postgresql",
        "postgres": "postgresql",
        "mysql": "mysql",
        "sqlite": "sqlite",
        "clickhouse": "postgresql",   # 近似
        "oracle": "postgresql",
        "sqlserver": "postgresql",
    }
    return mapping.get(db_type.lower(), "postgresql")
