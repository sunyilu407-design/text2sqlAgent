"""PreviewAPI - 实时数据预览接口

提供快速、限量的数据预览能力，用于：
1. 用户在执行完整查询前预览数据
2. 基于历史查询 ID 快速获取预览
3. 数据预览缓存与加速
"""

from __future__ import annotations

import re
import time
import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, Any

from micro_genbi import get_logger
from micro_genbi.errors import (
    GenBIError,
    SQLValidationError,
    SQLExecutionError,
)
from micro_genbi.db.engine import DatabaseExecutor, get_executor
from micro_genbi.service.query_history import get_query_history, QueryHistory
from micro_genbi.security import SQLSafetyValidator

logger = get_logger(__name__)

# 预览默认限制行数
DEFAULT_PREVIEW_LIMIT = 5
MAX_PREVIEW_LIMIT = 100
PREVIEW_TIMEOUT_SECONDS = 10


@dataclass
class PreviewResult:
    """预览结果

    Attributes:
        sql: 执行的 SQL 语句
        columns: 列信息列表
        rows: 预览数据行（限制为 preview_count 行）
        row_count: 实际返回的行数（未截断前的总数）
        preview_count: 预览的行数（截断后）
        execution_time_ms: 执行耗时（毫秒）
        generated_at: 结果生成时间
        is_truncated: 是否被截断（row_count > preview_count）
    """
    sql: str
    columns: list[str]
    rows: list[dict[str, Any]]
    row_count: int
    preview_count: int
    execution_time_ms: int
    generated_at: datetime = field(default_factory=datetime.now)
    is_truncated: bool = False

    def to_dict(self) -> dict[str, Any]:
        """转换为字典格式"""
        return {
            "sql": self.sql,
            "columns": self.columns,
            "rows": self.rows,
            "row_count": self.row_count,
            "preview_count": self.preview_count,
            "execution_time_ms": self.execution_time_ms,
            "generated_at": self.generated_at.isoformat(),
            "is_truncated": self.is_truncated,
        }


@dataclass
class PreviewRequest:
    """预览请求"""
    sql: str
    db_profile: str = "default"
    limit: int = DEFAULT_PREVIEW_LIMIT


class PreviewAPI:
    """
    实时数据预览 API

    特性：
    - 快速预览：限制返回行数，减少数据传输
    - 安全验证：对 SQL 进行安全检查
    - 历史回溯：支持通过历史查询 ID 获取预览
    - 超时控制：预览操作有较短的超时限制
    """

    def __init__(
        self,
        executor: Optional[DatabaseExecutor] = None,
        history: Optional[QueryHistory] = None,
        max_limit: int = MAX_PREVIEW_LIMIT,
    ):
        """
        初始化 PreviewAPI

        Args:
            executor: 数据库执行器（可选，默认使用全局执行器）
            history: 查询历史服务（可选）
            max_limit: 最大预览行数限制
        """
        self._executor = executor
        self._history = history
        self._max_limit = max_limit
        self._sql_validator = SQLSafetyValidator(
            max_limit=max_limit,
            max_join_count=10,
        )

    @property
    def executor(self) -> DatabaseExecutor:
        """获取数据库执行器"""
        if self._executor is None:
            self._executor = get_executor()
        return self._executor

    @property
    def history(self) -> QueryHistory:
        """获取查询历史服务"""
        if self._history is None:
            self._history = get_query_history()
        return self._history

    async def preview(
        self,
        sql: str,
        db_profile: str = "default",
        limit: int = DEFAULT_PREVIEW_LIMIT,
    ) -> PreviewResult:
        """
        执行数据预览

        Args:
            sql: SQL 查询语句
            db_profile: 数据库配置名称
            limit: 预览行数限制（默认 5）

        Returns:
            PreviewResult: 预览结果

        Raises:
            SQLValidationError: SQL 安全验证失败
            SQLExecutionError: SQL 执行失败
            GenBIError: 其他错误
        """
        # 限制参数校验
        limit = min(max(1, limit), self._max_limit)

        # 构建预览 SQL
        preview_sql = self._build_preview_sql(sql, limit)

        # 安全验证（仅验证原始 SQL，预览 SQL 已内置 LIMIT）
        try:
            self._sql_validator.validate_and_raise(sql)
        except SQLValidationError:
            raise

        start_time = time.time()

        try:
            # 执行预览查询（带超时控制）
            rows = await asyncio.wait_for(
                self._execute_preview(preview_sql, db_profile),
                timeout=PREVIEW_TIMEOUT_SECONDS,
            )

            # 获取总行数（用于判断是否截断）
            row_count = await self._get_row_count(sql, db_profile)

            execution_time_ms = int((time.time() - start_time) * 1000)

            # 提取列名
            columns = list(rows[0].keys()) if rows else []

            # 构建结果
            return PreviewResult(
                sql=preview_sql,
                columns=columns,
                rows=rows,
                row_count=row_count,
                preview_count=len(rows),
                execution_time_ms=execution_time_ms,
                generated_at=datetime.now(),
                is_truncated=row_count > limit,
            )

        except asyncio.TimeoutError:
            logger.warning(f"预览查询超时: {sql[:50]}...")
            raise SQLExecutionError(
                message=f"预览查询超时（{PREVIEW_TIMEOUT_SECONDS}秒）",
                sql=sql,
                phase="sql_execution",
            )
        except SQLValidationError:
            raise
        except Exception as e:
            logger.error(f"预览查询失败: {e}")
            raise SQLExecutionError(
                message=f"预览查询失败: {e}",
                sql=sql,
                phase="sql_execution",
            )

    async def preview_by_query_id(
        self,
        query_id: int,
    ) -> PreviewResult:
        """
        通过历史查询 ID 获取预览

        Args:
            query_id: 历史查询记录 ID

        Returns:
            PreviewResult: 预览结果

        Raises:
            GenBIError: 查询不存在或预览失败
        """
        # 从历史记录中获取 SQL
        records = self.history.get_history(limit=1000)
        record = None
        for r in records:
            if r.id == query_id:
                record = r
                break

        if record is None:
            raise GenBIError(
                message=f"查询记录不存在: {query_id}",
                code="RECORD_NOT_FOUND",
                phase="input",
            )

        if not record.sql:
            raise GenBIError(
                message=f"查询记录 {query_id} 无关联 SQL",
                code="SQL_NOT_FOUND",
                phase="input",
            )

        # 执行预览
        return await self.preview(
            sql=record.sql,
            db_profile=record.db_profile,
            limit=DEFAULT_PREVIEW_LIMIT,
        )

    def _build_preview_sql(self, sql: str, limit: int) -> str:
        """
        构建预览 SQL（添加或修改 LIMIT）

        处理逻辑：
        1. 如果 SQL 已有 LIMIT，保持较小的那个值
        2. 如果 SQL 没有 LIMIT，在末尾添加 LIMIT
        3. 处理 LIMIT n OFFSET m 格式

        Args:
            sql: 原始 SQL 语句
            limit: 限制行数

        Returns:
            str: 添加了 LIMIT 的 SQL
        """
        sql = sql.strip()

        # 检查是否已有 LIMIT
        limit_pattern = r'\bLIMIT\s+(\d+)\s*(OFFSET\s+\d+)?'
        offset_pattern = r'\bOFFSET\s+(\d+)\b'

        limit_match = re.search(limit_pattern, sql, re.IGNORECASE)
        offset_match = re.search(offset_pattern, sql, re.IGNORECASE)

        if limit_match:
            # 已有 LIMIT，替换为较小的值
            existing_limit = int(limit_match.group(1))
            new_limit = min(existing_limit, limit)

            # 构建替换：保持原有 OFFSET（如果有）
            if offset_match:
                # LIMIT n OFFSET m
                offset_value = offset_match.group(1)
                new_sql = re.sub(
                    limit_pattern,
                    f"LIMIT {new_limit} OFFSET {offset_value}",
                    sql,
                    flags=re.IGNORECASE,
                )
            else:
                # 仅有 LIMIT n
                new_sql = re.sub(
                    limit_pattern,
                    f"LIMIT {new_limit}",
                    sql,
                    flags=re.IGNORECASE,
                )
            return new_sql

        # 没有 LIMIT，添加 LIMIT
        # 移除末尾的分号
        if sql.rstrip().endswith(";"):
            sql = sql.rstrip()[:-1]

        # 在 ORDER BY 之前添加 LIMIT（如果有 ORDER BY）
        order_by_match = re.search(
            r'\s+ORDER\s+BY\s+',
            sql,
            re.IGNORECASE,
        )
        if order_by_match:
            pos = order_by_match.start()
            return sql[:pos] + f" LIMIT {limit}" + sql[pos:]
        else:
            # 直接追加到末尾
            return sql + f" LIMIT {limit}"

    async def _execute_preview(
        self,
        sql: str,
        db_profile: str,
    ) -> list[dict[str, Any]]:
        """执行预览查询"""
        try:
            return await self.executor.execute(sql)
        except Exception as e:
            raise SQLExecutionError(
                message=f"预览 SQL 执行失败: {e}",
                sql=sql,
                phase="sql_execution",
            )

    async def _get_row_count(
        self,
        sql: str,
        db_profile: str,
    ) -> int:
        """获取查询的总行数（用于判断是否截断）"""
        try:
            # 提取 SELECT ... FROM 部分
            select_pattern = r'^(SELECT\s+.*?\s+FROM\s+.*?)(?:\s+ORDER\s+BY\s+.*?)?(?:\s+LIMIT\s+\d+(?:\s+OFFSET\s+\d+)?)?(?:\s+;?)$'
            match = re.match(select_pattern, sql, re.IGNORECASE | re.DOTALL)

            if match:
                base_sql = match.group(1)
                count_sql = f"SELECT COUNT(*) as cnt FROM ({base_sql}) as _subquery"
            else:
                # 兜底：使用近似计数（简单替换 SELECT ... 为 SELECT COUNT(*)
                count_sql = re.sub(
                    r'^SELECT\s+.*?\s+FROM',
                    'SELECT COUNT(*) as cnt FROM',
                    sql,
                    count=1,
                    flags=re.IGNORECASE | re.DOTALL,
                )
                # 移除 LIMIT
                count_sql = re.sub(r'\s+LIMIT\s+\d+(?:\s+OFFSET\s+\d+)?', '', count_sql, flags=re.IGNORECASE)

            result = await self.executor.execute_one(count_sql)
            if result:
                return result.get("cnt", 0) or 0
            return 0

        except Exception as e:
            logger.warning(f"获取行数失败: {e}")
            return 0


# 全局单例
_preview_api: Optional[PreviewAPI] = None


def get_preview_api() -> PreviewAPI:
    """获取 PreviewAPI 全局实例"""
    global _preview_api
    if _preview_api is None:
        _preview_api = PreviewAPI()
    return _preview_api
