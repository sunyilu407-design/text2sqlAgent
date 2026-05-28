"""SQL Versioning Service

提供 SQL 版本管理能力，支持版本保存、查询、对比和回滚。
"""

from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from micro_genbi import get_logger

logger = get_logger(__name__)


@dataclass
class SQLVersion:
    """SQL 版本数据模型"""
    id: int
    user_id: str
    question: str
    sql: str
    created_at: datetime
    parent_version_id: Optional[int] = None
    change_summary: Optional[str] = None


class SQLVersioningService:
    """
    SQL 版本管理服务

    提供以下功能：
    - 保存 SQL 版本
    - 查询历史版本
    - 对比两个版本的差异
    - 回滚到指定版本

    使用内存存储，线程安全。
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._versions: dict[str, list[SQLVersion]] = {}
        self._version_counter: dict[str, int] = {}
        self._version_by_id: dict[int, SQLVersion] = {}

    def save_version(
        self,
        question: str,
        sql: str,
        user_id: str = "default",
        parent_version_id: Optional[int] = None,
        change_summary: Optional[str] = None,
    ) -> int:
        """
        保存新的 SQL 版本

        Args:
            question: 用户问题
            sql: 生成的 SQL
            user_id: 用户 ID
            parent_version_id: 父版本 ID
            change_summary: 变更摘要

        Returns:
            int: 新版本的 ID
        """
        with self._lock:
            if user_id not in self._versions:
                self._versions[user_id] = []
                self._version_counter[user_id] = 0

            self._version_counter[user_id] += 1
            version_id = self._version_counter[user_id]

            version = SQLVersion(
                id=version_id,
                user_id=user_id,
                question=question,
                sql=sql,
                created_at=datetime.now(),
                parent_version_id=parent_version_id,
                change_summary=change_summary,
            )

            self._versions[user_id].append(version)
            self._version_by_id[version_id] = version

            logger.debug(f"保存 SQL 版本: user={user_id}, version_id={version_id}")
            return version_id

    def get_version(self, version_id: int) -> Optional[SQLVersion]:
        """
        获取指定版本的详细信息

        Args:
            version_id: 版本 ID

        Returns:
            SQLVersion: 版本信息，不存在则返回 None
        """
        with self._lock:
            return self._version_by_id.get(version_id)

    def list_versions(
        self,
        question: str,
        user_id: str = "default",
        limit: int = 20,
    ) -> list[SQLVersion]:
        """
        列出指定问题相关的版本历史

        Args:
            question: 用户问题（模糊匹配）
            user_id: 用户 ID
            limit: 返回数量限制

        Returns:
            list[SQLVersion]: 版本列表，按创建时间倒序
        """
        with self._lock:
            if user_id not in self._versions:
                return []

            question_lower = question.lower()
            versions = [
                v for v in self._versions[user_id]
                if question_lower in v.question.lower()
            ]

            versions.sort(key=lambda v: v.created_at, reverse=True)
            return versions[:limit]

    def compare_versions(
        self,
        version_id1: int,
        version_id2: int,
    ) -> dict:
        """
        对比两个 SQL 版本的差异

        Args:
            version_id1: 版本 1 ID
            version_id2: 版本 2 ID

        Returns:
            dict: 包含以下键的差异分析：
                - added_tables: 新增的表
                - removed_tables: 移除的表
                - modified_where: WHERE 子句变化
                - modified_columns: SELECT 列变化
                - summary: 差异摘要
        """
        version1 = self.get_version(version_id1)
        version2 = self.get_version(version_id2)

        if version1 is None or version2 is None:
            raise ValueError(f"版本不存在: {version_id1} 或 {version_id2}")

        diff_result = self._diff_sql(version1.sql, version2.sql)

        diff_result["summary"] = self._generate_diff_summary(
            version1.sql,
            version2.sql,
            diff_result,
        )

        return diff_result

    def rollback(self, version_id: int) -> str:
        """
        回滚到指定版本

        Args:
            version_id: 要回滚到的版本 ID

        Returns:
            str: 该版本的 SQL

        Raises:
            ValueError: 版本不存在
        """
        version = self.get_version(version_id)
        if version is None:
            raise ValueError(f"版本不存在: {version_id}")

        logger.info(f"回滚到版本: version_id={version_id}")
        return version.sql

    def _diff_sql(self, sql1: str, sql2: str) -> dict:
        """
        使用 sqlglot 解析并对比两个 SQL

        Args:
            sql1: 原始 SQL
            sql2: 新 SQL

        Returns:
            dict: 差异分析结果
        """
        try:
            import sqlglot
        except ImportError:
            logger.warning("sqlglot 未安装，使用简单文本对比")
            return self._simple_diff_sql(sql1, sql2)

        result = {
            "added_tables": [],
            "removed_tables": [],
            "modified_where": False,
            "modified_columns": False,
        }

        try:
            tree1 = sqlglot.parse_one(sql1.lower())
            tree2 = sqlglot.parse_one(sql2.lower())

            tables1 = self._extract_tables(tree1)
            tables2 = self._extract_tables(tree2)

            result["added_tables"] = list(tables2 - tables1)
            result["removed_tables"] = list(tables1 - tables2)

            result["modified_where"] = self._compare_where_clauses(tree1, tree2)
            result["modified_columns"] = self._compare_select_columns(tree1, tree2)

        except Exception as e:
            logger.warning(f"SQL 解析失败，使用简单对比: {e}")
            return self._simple_diff_sql(sql1, sql2)

        return result

    def _simple_diff_sql(self, sql1: str, sql2: str) -> dict:
        """简单的文本级别 SQL 对比"""
        return {
            "added_tables": [],
            "removed_tables": [],
            "modified_where": sql1.lower() != sql2.lower(),
            "modified_columns": False,
        }

    def _extract_tables(self, tree) -> set[str]:
        """从 SQL AST 中提取所有表名"""
        tables = set()

        for node in tree.walk():
            if isinstance(node, sqlglot.exp.Table):
                if node.name:
                    tables.add(node.name.lower())

        return tables

    def _compare_where_clauses(self, tree1, tree2) -> bool:
        """对比 WHERE 子句是否变化"""
        where1 = None
        where2 = None

        for node in tree1.walk():
            if isinstance(node, sqlglot.exp.Where):
                where1 = str(node).lower()
                break

        for node in tree2.walk():
            if isinstance(node, sqlglot.exp.Where):
                where2 = str(node).lower()
                break

        if where1 is None and where2 is None:
            return False
        if where1 is None or where2 is None:
            return True

        return where1 != where2

    def _compare_select_columns(self, tree1, tree2) -> bool:
        """对比 SELECT 列是否变化"""
        cols1 = self._get_select_columns(tree1)
        cols2 = self._get_select_columns(tree2)

        return cols1 != cols2

    def _get_select_columns(self, tree) -> set[str]:
        """获取 SELECT 列名集合"""
        columns = set()

        for node in tree.walk():
            if isinstance(node, sqlglot.exp.Column):
                col_name = node.name.lower()
                columns.add(col_name)

        return columns

    def _generate_diff_summary(
        self,
        sql1: str,
        sql2: str,
        diff: dict,
    ) -> str:
        """生成差异摘要文本"""
        parts = []

        added = diff.get("added_tables", [])
        if added:
            parts.append(f"新增表: {', '.join(added)}")

        removed = diff.get("removed_tables", [])
        if removed:
            parts.append(f"移除表: {', '.join(removed)}")

        if diff.get("modified_where"):
            parts.append("WHERE 条件已修改")

        if diff.get("modified_columns"):
            parts.append("SELECT 列已修改")

        if not parts:
            parts.append("SQL 文本有变化但结构相同")

        return "; ".join(parts)
