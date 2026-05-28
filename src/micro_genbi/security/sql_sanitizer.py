"""SQL 深度净化器

基于 sqlglot 的 SQL 安全检查和深度净化。
"""

from __future__ import annotations

import re
from typing import Optional, Set
from dataclasses import dataclass

import sqlglot
from sqlglot import exp, parse, dialects
from sqlglot.errors import SqlglotError

from micro_genbi.errors import SQLValidationError


@dataclass
class ValidationResult:
    """验证结果"""
    is_valid: bool
    sql: str
    violations: list[str]
    warnings: list[str]


class SQLSanitizer:
    """
    SQL 深度净化器

    在 SQLSafetyValidator 之后执行，对 SQL 进行额外的安全检查和规范化。
    """

    # 高危关键词黑名单（大小写不敏感）
    HIGH_RISK_KEYWORDS: Set[str] = {
        # 数据操作
        "INSERT", "UPDATE", "DELETE", "DROP", "TRUNCATE",
        "ALTER", "CREATE", "GRANT", "REVOKE", "DENY",
        "EXEC", "EXECUTE", "CALL", "LOAD", "INTO OUTFILE",
        "INTO DUMPFILE", "LOAD_FILE", "BENCHMARK", "SLEEP",
        # 系统命令
        "SHUTDOWN", "KILL", "RESET", "RESTORE",
        # 注释注入
        "--", "/*", "*/", "#",
    }

    # 危险函数黑名单
    DANGEROUS_FUNCTIONS: Set[str] = {
        # 系统函数
        "SYSTEM", "SESSION_USER", "CURRENT_USER",
        "LOAD_FILE", "INTO DUMPFILE", "BENCHMARK", "SLEEP",
        "DATABASE", "SCHEMA", "VERSION", "@@VERSION",
        # 文件操作
        "FILE", "LOAD", "OUTFILE", "DUMPFILE",
        # 编码函数（可能被用于绕过）
        "HEX(", "UNHEX(", "CHAR(",
        # 复杂编码
        "ENCODE", "DECODE", "AES_DECRYPT", "AES_ENCRYPT",
    }

    def sanitize(self, sql: str) -> str:
        """
        净化 SQL

        Args:
            sql: 原始 SQL 语句

        Returns:
            净化后的 SQL

        Raises:
            SQLValidationError: 检测到安全问题
        """
        # 1. 移除注释
        sql = self._remove_comments(sql)

        # 2. 规范化空白符
        sql = self._normalize_whitespace(sql)

        # 3. 检查高危关键词
        self._check_high_risk_keywords(sql)

        # 4. 检查危险函数
        self._check_dangerous_functions(sql)

        # 5. 检查注释注入
        self._check_comment_injection(sql)

        # 6. 检查编码注入
        self._check_encoding_injection(sql)

        return sql

    def _remove_comments(self, sql: str) -> str:
        """移除 SQL 注释"""
        # 移除 -- 注释（包括标记本身）
        sql = re.sub(r'--[^\n\r]*', '', sql)
        # 移除 /* */ 注释（包括标记本身）
        sql = re.sub(r'/\*.*?\*/', '', sql, flags=re.DOTALL)
        # 移除 # 注释（MySQL，包括标记本身）
        sql = re.sub(r'#[^\n\r]*', '', sql)
        return sql.strip()

    def _normalize_whitespace(self, sql: str) -> str:
        """规范化空白符"""
        return re.sub(r'\s+', ' ', sql).strip()

    def _check_high_risk_keywords(self, sql: str) -> None:
        """检查高危关键词"""
        sql_upper = sql.upper()
        for keyword in self.HIGH_RISK_KEYWORDS:
            # 使用词边界匹配
            if keyword in ("--", "/*", "*/", "#"):
                continue  # 已在 _remove_comments 中处理
            pattern = r'\b' + keyword + r'\b'
            if re.search(pattern, sql_upper):
                raise SQLValidationError(
                    message=f"检测到高危关键词: {keyword}",
                    violation_type="high_risk_keyword",
                )

    def _check_dangerous_functions(self, sql: str) -> None:
        """检查危险函数"""
        sql_upper = sql.upper()
        for func in self.DANGEROUS_FUNCTIONS:
            pattern = r'\b' + func.replace('(', r'\s*\(')
            if re.search(pattern, sql_upper, re.IGNORECASE):
                raise SQLValidationError(
                    message=f"检测到危险函数: {func}",
                    violation_type="dangerous_function",
                )

    def _check_comment_injection(self, sql: str) -> None:
        """检查注释注入"""
        if '--' in sql or '/*' in sql or '*/' in sql or '#' in sql:
            raise SQLValidationError(
                message="检测到注释注入尝试",
                violation_type="comment_injection",
            )

    def _check_encoding_injection(self, sql: str) -> None:
        """检查编码注入"""
        if re.search(r'0x[0-9a-fA-F]+', sql):
            raise SQLValidationError(
                message="检测到十六进制编码注入",
                violation_type="encoding_injection",
            )
        if re.search(r'CHAR\s*\(', sql, re.IGNORECASE):
            raise SQLValidationError(
                message="检测到 CHAR 编码注入",
                violation_type="encoding_injection",
            )


class SQLSafetyValidator:
    """
    SQL 安全验证器

    使用 sqlglot AST 遍历检查 SQL 安全性。
    """

    # 允许的 SQL 类型
    ALLOWED_STATEMENTS = {"SELECT", "WITH"}

    # 禁止的操作类型
    FORBIDDEN_OPERATIONS = {
        exp.Insert,
        exp.Update,
        exp.Delete,
        exp.Drop,
        exp.TruncateTable,
        exp.Alter,
        exp.Create,
        exp.Grant,
        exp.Revoke,
    }

    def __init__(
        self,
        max_limit: int = 1000,
        max_join_count: int = 10,
        allowed_tables: Optional[set[str]] = None,
        dialect: str = "postgres",
    ):
        self.max_limit = max_limit
        self.max_join_count = max_join_count
        self.allowed_tables = allowed_tables
        self.dialect = dialect
        self.sanitizer = SQLSanitizer()

    def validate(self, sql: str) -> ValidationResult:
        """
        验证 SQL 安全性

        Args:
            sql: SQL 语句

        Returns:
            ValidationResult: 验证结果
        """
        violations: list[str] = []
        warnings: list[str] = []

        try:
            # 1. 深度净化
            sql = self.sanitizer.sanitize(sql)

            # 2. 解析 SQL
            statements = parse(sql, dialect=self.dialect)
            if not statements:
                violations.append("无法解析 SQL 语句")
                return ValidationResult(False, sql, violations, warnings)

            # 3. 检查语句类型
            for stmt in statements:
                stmt_violations, stmt_warnings = self._validate_statement(stmt)
                violations.extend(stmt_violations)
                warnings.extend(stmt_warnings)

            # 4. 强制追加 LIMIT
            sql = self._ensure_limit(sql, statements)

            return ValidationResult(
                is_valid=len(violations) == 0,
                sql=sql,
                violations=violations,
                warnings=warnings,
            )

        except SQLValidationError as e:
            violations.append(str(e))
            return ValidationResult(False, sql, violations, warnings)
        except SqlglotError as e:
            violations.append(f"SQL 解析错误: {e}")
            return ValidationResult(False, sql, violations, warnings)

    def _validate_statement(
        self,
        stmt: exp.Expression,
    ) -> tuple[list[str], list[str]]:
        """验证单个语句"""
        violations: list[str] = []
        warnings: list[str] = []

        stmt_type = type(stmt).__name__.upper()

        # 检查语句类型
        if stmt_type not in self.ALLOWED_STATEMENTS:
            violations.append(f"不支持的 SQL 语句类型: {stmt_type}")
            return violations, warnings

        # 递归检查
        violations.extend(self._check_write_operations(stmt))

        # 检查复杂度
        join_count = self._count_joins(stmt)
        if join_count > self.max_join_count:
            violations.append(
                f"JOIN 数量超过限制: {join_count} > {self.max_join_count}"
            )

        # 检查表名白名单
        violations.extend(self._check_table_whitelist(stmt))

        # 检查子查询
        violations.extend(self._check_subqueries(stmt))

        return violations, warnings

    def _check_write_operations(self, expr: exp.Expression) -> list[str]:
        """检查写操作"""
        violations: list[str] = []

        for node in expr.walk():
            node_type = type(node)
            if node_type in self.FORBIDDEN_OPERATIONS:
                violations.append(f"检测到禁止的操作: {node_type.__name__}")

        return violations

    def _count_joins(self, stmt: exp.Expression) -> int:
        """计算 JOIN 数量"""
        count = 0
        for node in stmt.walk():
            if isinstance(node, (exp.Join, exp.CTE)):
                count += 1
        return count

    def _check_table_whitelist(self, stmt: exp.Expression) -> list[str]:
        """检查表名白名单"""
        if self.allowed_tables is None:
            return []

        violations: list[str] = []
        tables = set()

        # 提取所有表名
        for node in stmt.walk():
            if isinstance(node, exp.Table):
                tables.add(node.name.lower())

        # 检查白名单
        for table in tables:
            if table not in {t.lower() for t in self.allowed_tables}:
                violations.append(f"表不在白名单中: {table}")

        return violations

    def _check_subqueries(self, stmt: exp.Expression) -> list[str]:
        """检查子查询中的写操作"""
        violations: list[str] = []

        for node in stmt.walk():
            if isinstance(node, exp.Subquery):
                # 递归检查子查询
                subquery = node.this
                violations.extend(self._check_write_operations(subquery))

        return violations

    def _ensure_limit(
        self,
        sql: str,
        statements: list[exp.Expression],
    ) -> str:
        """确保 SQL 有 LIMIT"""
        # 检查是否已有 LIMIT
        for stmt in statements:
            if isinstance(stmt, exp.Select):
                limit_node = stmt.find(exp.Limit)
                if limit_node:
                    # 如果 LIMIT 超过上限，替换为上限值
                    if limit_node.args.get("expression"):
                        try:
                            limit_val = int(str(limit_node.args["expression"]))
                            if limit_val > self.max_limit:
                                sql = self._replace_limit(sql, self.max_limit)
                        except (ValueError, TypeError):
                            pass
                    return sql

        # 添加 LIMIT
        return f"{sql.rstrip(';')} LIMIT {self.max_limit}"

    def _replace_limit(self, sql: str, new_limit: int) -> str:
        """替换 SQL 中的 LIMIT 值"""
        import re
        pattern = r'LIMIT\s+\d+'
        replacement = f'LIMIT {new_limit}'
        return re.sub(pattern, replacement, sql, flags=re.IGNORECASE)

    def validate_and_raise(self, sql: str) -> str:
        """验证并抛出异常"""
        result = self.validate(sql)
        if not result.is_valid:
            raise SQLValidationError(
                message=f"SQL 验证失败: {result.violations[0]}",
                sql=sql,
                violation_type="validation_failed",
            )
        return result.sql


# =============================================================================
# 便捷函数
# =============================================================================

def validate_sql(
    sql: str,
    max_limit: int = 1000,
    max_join_count: int = 10,
    allowed_tables: Optional[set[str]] = None,
    dialect: str = "postgres",
) -> ValidationResult:
    """
    便捷函数：验证 SQL

    Args:
        sql: SQL 语句
        max_limit: 最大 LIMIT
        max_join_count: 最大 JOIN 数
        allowed_tables: 允许的表（白名单）
        dialect: SQL 方言

    Returns:
        ValidationResult: 验证结果
    """
    validator = SQLSafetyValidator(
        max_limit=max_limit,
        max_join_count=max_join_count,
        allowed_tables=allowed_tables,
        dialect=dialect,
    )
    return validator.validate(sql)


def sanitize_sql(sql: str) -> str:
    """
    便捷函数：净化 SQL

    Args:
        sql: 原始 SQL

    Returns:
        净化后的 SQL
    """
    sanitizer = SQLSanitizer()
    return sanitizer.sanitize(sql)
