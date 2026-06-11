"""AskService - 核心查询服务

整合意图分类、语义检索、SQL生成、SQL验证、执行的完整流水线。
"""

from __future__ import annotations

import time
import re
from dataclasses import dataclass, field
from typing import Optional, Any
from datetime import datetime

from micro_genbi import get_logger, track_duration
from micro_genbi.models import (
    QueryRequest,
    QueryResponse,
    QueryResult,
    IntentType,
    IntentClassification,
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
    validate_sql,
)
from micro_genbi.llm.base import LLMClient, create_llm_client
from micro_genbi.semantic.schema_registry import SchemaRegistry
from micro_genbi.db.engine import DatabaseExecutor

logger = get_logger(__name__)


@dataclass
class PipelineContext:
    """流水线上下文"""
    request: QueryRequest
    start_time: float
    user_id: Optional[str] = None
    role: str = "user"
    session_id: Optional[str] = None

    # 中间结果
    intent: Optional[IntentClassification] = None
    schema_context: Optional[str] = None
    generated_sql: Optional[str] = None
    validated_sql: Optional[str] = None
    query_result: Optional[list[dict]] = None
    error: Optional[str] = None

    # 时间统计
    steps_timing: dict[str, int] = field(default_factory=dict)


class AskService:
    """
    核心查询服务

    提供端到端的自然语言查询能力：
    1. Prompt 安全检查
    2. 意图分类
    3. Schema 检索
    4. SQL 生成
    5. SQL 验证
    6. SQL 执行
    7. 数据脱敏
    8. 结果返回
    """

    def __init__(
        self,
        llm_client: Optional[LLMClient] = None,
        schema_registry: Optional[SchemaRegistry] = None,
        executor: Optional[DatabaseExecutor] = None,
        schema_path: Optional[str] = None,
        max_retries: int = 3,
        enable_security: bool = True,
        enable_masking: bool = True,
    ):
        self.llm_client = llm_client or create_llm_client()
        self.executor = executor
        self.max_retries = max_retries
        self.enable_security = enable_security
        self.enable_masking = enable_masking

        # Schema Registry
        if schema_registry:
            self.schema_registry = schema_registry
        else:
            self.schema_registry = SchemaRegistry(schema_path=schema_path)
            self.schema_registry.load()

        # 安全组件
        self.sql_validator = SQLSafetyValidator(
            max_limit=1000,
            max_join_count=10,
        )
        self.prompt_detector = PromptInjectionDetector(
            enable_oil_depot_sensitive=True,
        )
        self.data_masker = DataMasker(enable_oil_depot=True)

        # 意图分类器
        self.intent_classifier = IntentClassifier(self.llm_client)

        # SQL 生成器
        self.sql_generator = SQLGenerator(self.llm_client)

    async def close(self) -> None:
        """关闭服务，释放资源"""
        if self.llm_client:
            await self.llm_client.close()

    async def ask(
        self,
        query: str,
        user_id: Optional[str] = None,
        role: str = "user",
        session_id: Optional[str] = None,
        max_retries: Optional[int] = None,
        skip_execution: bool = False,
    ) -> QueryResponse:
        """
        执行自然语言查询

        Args:
            query: 自然语言查询
            user_id: 用户 ID
            role: 用户角色
            session_id: 会话 ID
            max_retries: 最大重试次数

        Returns:
            QueryResponse: 查询响应
        """
        request = QueryRequest(
            query=query,
            user_id=user_id,
            role=role,
            session_id=session_id,
        )

        ctx = PipelineContext(
            request=request,
            start_time=time.time(),
            user_id=user_id,
            role=role,
            session_id=session_id,
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

                # 转换为重试异常
                e.retry_count = retry_count
                raise to_retry(e, max_retries=max_r, retry_count=retry_count)

            except GenBIError as e:
                if should_propagate(e):
                    raise
                raise

            except Exception as e:
                logger.error(f"查询失败: {e}")
                raise

    async def _execute_pipeline(self, ctx: PipelineContext) -> QueryResponse:
        """执行流水线"""
        query = ctx.request.query

        # ========== 步骤 1: Prompt 安全检查 ==========
        with track_duration("prompt_security_check") as timer:
            if self.enable_security:
                self.prompt_detector.detect_and_raise(query)
            ctx.steps_timing["prompt_security_check_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 2: 意图分类 ==========
        with track_duration("intent_classification") as timer:
            ctx.intent = await self.intent_classifier.classify(query)
            ctx.steps_timing["intent_classification_ms"] = int(timer.elapsed * 1000)
            logger.debug(f"意图分类: {ctx.intent.intent}, 置信度: {ctx.intent.confidence}")

        # ========== 步骤 3: Schema 检索 ==========
        with track_duration("schema_retrieval") as timer:
            ctx.schema_context = self.schema_registry.build_llm_context(
                max_tables=5,
            )
            ctx.steps_timing["schema_retrieval_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 4: SQL 生成 ==========
        with track_duration("sql_generation") as timer:
            ctx.generated_sql = await self.sql_generator.generate(
                query=query,
                schema_context=ctx.schema_context,
                intent=ctx.intent,
            )
            ctx.steps_timing["sql_generation_ms"] = int(timer.elapsed * 1000)
            logger.debug(f"生成的 SQL: {ctx.generated_sql}")

        # ========== 步骤 5: SQL 验证 ==========
        with track_duration("sql_validation") as timer:
            ctx.validated_sql = self.sql_validator.validate_and_raise(ctx.generated_sql)
            ctx.steps_timing["sql_validation_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 6: SQL 执行 ==========
        if skip_execution:
            ctx.query_result = []
            ctx.steps_timing["sql_execution_ms"] = 0
        else:
            with track_duration("sql_execution") as timer:
                ctx.query_result = await self._execute_sql(ctx.validated_sql)
                ctx.steps_timing["sql_execution_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 7: 数据脱敏 ==========
        with track_duration("data_masking") as timer:
            if self.enable_masking:
                ctx.query_result = self.data_masker.mask_result(
                    ctx.query_result,
                    user_role=ctx.role,
                )
            ctx.steps_timing["data_masking_ms"] = int(timer.elapsed * 1000)

        # ========== 步骤 8: 构建响应 ==========
        total_time = int((time.time() - ctx.start_time) * 1000)

        return QueryResponse(
            sql=ctx.validated_sql,
            data=ctx.query_result or [],
            columns=[],
            row_count=len(ctx.query_result) if ctx.query_result else 0,
            chart=None,
            summary=self._build_summary(ctx, skip_execution),
            session_id=ctx.session_id,
            execution_time_ms=total_time,
            steps_timing=ctx.steps_timing,
        )

    async def _execute_sql(self, sql: str) -> list[dict]:
        """执行 SQL 查询"""
        if self.executor is None:
            # 无数据库连接，返回模拟数据
            logger.warning("未配置数据库执行器，返回模拟数据")
            return [
                {"id": 1, "message": "模拟数据 - 请配置数据库"},
            ]

        try:
            return await self.executor.execute(sql)
        except Exception as e:
            raise SQLExecutionError(
                message=f"SQL 执行失败: {e}",
                sql=sql,
            )

    def _build_summary(self, ctx: PipelineContext, skip_execution: bool = False) -> str:
        """构建结果摘要"""
        if ctx.error:
            return f"查询失败: {ctx.error}"

        row_count = len(ctx.query_result) if ctx.query_result else 0
        if skip_execution:
            row_count = 0
        intent = ctx.intent.intent.value if ctx.intent else "query"

        return f"查询成功，识别为【{intent}】，返回 {row_count} 行数据"


class IntentClassifier:
    """
    意图分类器

    采用三层分类策略：
    1. 规则匹配（低成本）
    2. LLM 分类（高置信度）
    """

    # 意图关键词映射
    INTENT_PATTERNS = {
        IntentType.AGGREGATION: [
            "统计", "合计", "总计", "sum", "count", "avg", "平均",
            "总数", "count", "汇总", "聚合",
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
        """
        分类用户查询的意图

        Args:
            query: 用户查询

        Returns:
            IntentClassification: 分类结果
        """
        # ========== 第一层：规则匹配 ==========
        for intent, keywords in self.INTENT_PATTERNS.items():
            for keyword in keywords:
                if keyword.lower() in query.lower():
                    return IntentClassification(
                        intent=intent,
                        confidence=0.85,
                        reasoning=f"关键词匹配: {keyword}",
                    )

        # ========== 第二层：LLM 分类 ==========
        prompt = f"""请分析以下用户查询的意图类型，只回答一个词（query/aggregation/comparison/trend/filter/ranking）。

用户查询: {query}

只回答意图类型，不要解释。"""

        try:
            response = await self.llm_client.generate(prompt)
            intent_str = response.content.strip().lower()

            # 映射到 IntentType
            intent_map = {
                "query": IntentType.QUERY,
                "aggregation": IntentType.AGGREGATION,
                "comparison": IntentType.COMPARISON,
                "trend": IntentType.TREND,
                "filter": IntentType.FILTER,
                "ranking": IntentType.RANKING,
            }

            intent = intent_map.get(intent_str, IntentType.QUERY)

            return IntentClassification(
                intent=intent,
                confidence=0.75,
                reasoning="LLM 分类",
            )

        except Exception as e:
            logger.warning(f"LLM 意图分类失败: {e}，使用默认分类")
            return IntentClassification(
                intent=IntentType.QUERY,
                confidence=0.5,
                reasoning="默认分类（LLM 失败）",
            )


class SQLGenerator:
    """
    SQL 生成器

    使用 LLM 生成 SQL 查询语句。
    """

    SYSTEM_PROMPT = """你是一个 SQL 专家，负责根据用户的自然语言问题生成准确的 SQL 查询。

重要规则：
1. 只生成 SELECT 查询，禁止 INSERT、UPDATE、DELETE 等写操作
2. 所有 SELECT 必须有 LIMIT，默认为 1000
3. 必须使用表名和列名的真实名称，不要使用中文
4. SQL 必须符合 PostgreSQL 语法
5. 不要使用 SELECT *，必须明确列出需要的列
6. 适当的表别名可以提高可读性

请根据以下 Schema 信息生成 SQL："""

    def __init__(self, llm_client: LLMClient):
        self.llm_client = llm_client

    async def generate(
        self,
        query: str,
        schema_context: str,
        intent: Optional[IntentClassification] = None,
    ) -> str:
        """
        生成 SQL

        Args:
            query: 用户查询
            schema_context: Schema 上下文
            intent: 意图分类结果

        Returns:
            str: 生成的 SQL
        """
        user_prompt = f"""用户问题: {query}

Schema 信息:
{schema_context}

请生成 SQL 查询。"""

        try:
            response = await self.llm_client.generate(
                prompt=user_prompt,
                system=self.SYSTEM_PROMPT,
            )

            # 提取 SQL
            sql = self._extract_sql(response.content)
            return sql

        except Exception as e:
            raise SQLExecutionError(
                message=f"SQL 生成失败: {e}",
                phase="sql_generation",
            )

    def _extract_sql(self, content: str) -> str:
        """从 LLM 输出中提取 SQL"""
        # 尝试从代码块中提取
        sql_blocks = re.findall(r'```sql\s*(.*?)\s*```', content, re.DOTALL | re.IGNORECASE)
        if sql_blocks:
            return sql_blocks[0].strip()

        # 尝试从 ``` 中提取
        code_blocks = re.findall(r'```\s*(.*?)\s*```', content, re.DOTALL)
        if code_blocks:
            return code_blocks[0].strip()

        # 直接返回清理后的内容
        sql = content.strip()

        # 移除可能的引号前缀
        if sql.startswith('"') and sql.endswith('"'):
            sql = sql[1:-1]
        if sql.startswith("'") and sql.endswith("'"):
            sql = sql[1:-1]

        return sql
