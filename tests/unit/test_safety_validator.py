"""SQLSafetyValidator 单元测试"""

import pytest
from micro_genbi.security.sql_sanitizer import (
    SQLSafetyValidator,
    SQLSanitizer,
    ValidationResult,
)


class TestSQLSafetyValidator:
    """SQL 安全验证器测试"""

    @pytest.fixture
    def validator(self) -> SQLSafetyValidator:
        """创建验证器实例（无表白名单）"""
        return SQLSafetyValidator(
            max_limit=1000,
            max_join_count=10,
        )

    @pytest.mark.parametrize("sql,should_pass", [
        # 写操作应该被拦截
        ("DROP TABLE users", False),
        ("DELETE FROM orders", False),
        ("UPDATE orders SET status='cancelled'", False),
        ("INSERT INTO orders VALUES(1)", False),
        ("TRUNCATE TABLE orders", False),
        ("ALTER TABLE orders ADD COLUMN test", False),
        ("CREATE TABLE evil (id int)", False),
        ("GRANT ALL ON orders TO public", False),
        ("REVOKE SELECT ON orders FROM public", False),
        # 组合恶意 SQL
        ("SELECT * FROM orders; DROP TABLE orders;", False),
        # 危险函数应该被拦截
        ("SELECT SLEEP(5)", False),
        ("SELECT BENCHMARK(1000000, MD5('test'))", False),
        # 编码注入
        ("SELECT * FROM users WHERE name=0x61646d696e", False),
        # 只读查询应该通过
        ("SELECT * FROM orders LIMIT 100", True),
        ("SELECT COUNT(*) FROM orders", True),
        ("SELECT * FROM orders WHERE status='completed'", True),
        ("SELECT o.*, c.name FROM orders o JOIN customers c ON o.customer_id = c.id", True),
    ])
    def test_sql_validation(
        self,
        validator: SQLSafetyValidator,
        sql: str,
        should_pass: bool,
    ):
        """测试 SQL 验证"""
        result = validator.validate(sql)

        if should_pass:
            assert result.is_valid, \
                f"应该允许: {sql}\nviolations: {result.violations}"
        else:
            assert not result.is_valid, \
                f"应该拦截: {sql}\nviolations: {result.violations}"

    def test_limit_enforcement(self, validator: SQLSafetyValidator):
        """测试 LIMIT 强制追加"""
        result = validator.validate("SELECT * FROM orders")
        assert "LIMIT 1000" in result.sql.upper(), "应该追加 LIMIT"

        result = validator.validate("SELECT * FROM orders LIMIT 5000")
        assert "LIMIT 1000" in result.sql.upper(), "LIMIT 应该被截断"

        result = validator.validate("SELECT * FROM orders LIMIT 100")
        assert "LIMIT 100" in result.sql.upper(), "正常 LIMIT 应该保留"

    def test_with_table_whitelist(self):
        """测试表白名单检查"""
        validator = SQLSafetyValidator(
            max_limit=1000,
            max_join_count=10,
            allowed_tables={"orders", "customers"},
        )

        result = validator.validate("SELECT * FROM orders LIMIT 10")
        assert result.is_valid

        result = validator.validate("SELECT * FROM unknown_table LIMIT 10")
        assert not result.is_valid
        assert any("不在白名单中" in v or "unknown_table" in v.lower() for v in result.violations)

    def test_complexity_check(self, validator: SQLSafetyValidator):
        """测试复杂度检查（JOIN 数量）"""
        complex_sql = """
        SELECT * FROM orders o1
        JOIN customers c1 ON o1.c1 = c1.id
        JOIN customers c2 ON o1.c2 = c2.id
        JOIN customers c3 ON o1.c3 = c3.id
        JOIN customers c4 ON o1.c4 = c4.id
        JOIN customers c5 ON o1.c5 = c5.id
        JOIN customers c6 ON o1.c6 = c6.id
        JOIN customers c7 ON o1.c7 = c7.id
        JOIN customers c8 ON o1.c8 = c8.id
        JOIN customers c9 ON o1.c9 = c9.id
        JOIN customers c10 ON o1.c10 = c10.id
        JOIN customers c11 ON o1.c11 = c11.id
        """
        result = validator.validate(complex_sql)
        assert not result.is_valid, "JOIN 数量超过限制应该被拦截"

    def test_cte_query(self, validator: SQLSafetyValidator):
        """测试 CTE 查询"""
        sql = """
        WITH order_stats AS (
            SELECT customer_id, COUNT(*) as order_count
            FROM orders
            GROUP BY customer_id
        )
        SELECT * FROM order_stats LIMIT 100
        """
        result = validator.validate(sql)
        assert result.is_valid, f"CTE 查询应该通过: {result.violations}"

    def test_subquery(self, validator: SQLSafetyValidator):
        """测试子查询"""
        sql = "SELECT * FROM (SELECT id, name FROM customers) AS sub LIMIT 10"
        result = validator.validate(sql)
        assert result.is_valid, f"子查询应该通过: {result.violations}"

    def test_validate_and_raise_passes_for_valid(self, validator: SQLSafetyValidator):
        """测试 validate_and_raise 对有效 SQL 不抛异常"""
        sql = "SELECT * FROM orders LIMIT 100"
        result = validator.validate_and_raise(sql)
        assert "LIMIT" in result.upper()

    def test_validate_and_raise_raises_for_invalid(self, validator: SQLSafetyValidator):
        """测试 validate_and_raise 对无效 SQL 抛异常"""
        from micro_genbi.errors import SQLValidationError
        sql = "DROP TABLE users"
        with pytest.raises(SQLValidationError):
            validator.validate_and_raise(sql)


class TestSQLSanitizer:
    """SQL 深度净化器测试"""

    @pytest.fixture
    def sanitizer(self) -> SQLSanitizer:
        return SQLSanitizer()

    def test_remove_comments(self, sanitizer: SQLSanitizer):
        """测试注释移除"""
        sql = "SELECT * FROM users -- comment"
        result = sanitizer._remove_comments(sql)
        assert "-- comment" not in result

    def test_normalize_whitespace(self, sanitizer: SQLSanitizer):
        """测试空白符规范化"""
        sql = "SELECT   *  FROM   users"
        result = sanitizer._normalize_whitespace(sql)
        assert "   " not in result

    def test_high_risk_keywords(self, sanitizer: SQLSanitizer):
        """测试高危关键词检测"""
        from micro_genbi.errors import SQLValidationError
        for keyword in ["DROP", "DELETE", "INSERT", "UPDATE"]:
            with pytest.raises(SQLValidationError):
                sanitizer._check_high_risk_keywords(f"SELECT * FROM {keyword}")

    def test_comment_injection(self, sanitizer: SQLSanitizer):
        """测试注释注入检测"""
        from micro_genbi.errors import SQLValidationError
        with pytest.raises(SQLValidationError):
            sanitizer._check_comment_injection("SELECT * FROM users -- evil")

    def test_encoding_injection(self, sanitizer: SQLSanitizer):
        """测试编码注入检测"""
        from micro_genbi.errors import SQLValidationError
        with pytest.raises(SQLValidationError):
            sanitizer._check_encoding_injection("SELECT * FROM users WHERE name=0x61646d696e")

    def test_sanitize_valid_sql(self, sanitizer: SQLSanitizer):
        """测试净化有效 SQL"""
        sql = "SELECT * FROM orders WHERE status='active' LIMIT 100"
        result = sanitizer.sanitize(sql)
        assert "SELECT" in result.upper()
