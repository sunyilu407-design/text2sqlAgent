"""SQL Versioning Service 单元测试"""

import pytest
from micro_genbi.service.sql_versioning import (
    SQLVersioningService,
    SQLVersion,
)


class TestSQLVersioningService:
    """SQL 版本管理服务测试"""

    @pytest.fixture
    def service(self) -> SQLVersioningService:
        return SQLVersioningService()

    @pytest.fixture
    def sample_sql(self) -> str:
        return "SELECT city, SUM(sales) FROM orders GROUP BY city"

    def test_save_version(self, service: SQLVersioningService, sample_sql):
        """测试保存版本"""
        version_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        assert version_id > 0

    def test_list_versions(self, service: SQLVersioningService, sample_sql):
        """测试列出版本"""
        service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        service.save_version(
            question="各城市销售汇总",
            sql=sample_sql.replace("SUM", "AVG"),
            user_id="test_user",
        )
        versions = service.list_versions(
            question="各城市销售汇总",
            user_id="test_user",
        )
        assert len(versions) == 2

    def test_get_version(self, service: SQLVersioningService, sample_sql):
        """测试获取单个版本"""
        version_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        version = service.get_version(version_id)
        assert version is not None
        assert version.sql == sample_sql

    def test_get_nonexistent_version(self, service: SQLVersioningService):
        """测试获取不存在的版本返回 None"""
        version = service.get_version(999999)
        assert version is None

    def test_save_version_with_parent(self, service: SQLVersioningService, sample_sql):
        """测试保存带父版本的版本"""
        parent_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        child_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql.replace("SUM", "AVG"),
            user_id="test_user",
            parent_version_id=parent_id,
            change_summary="改用 AVG 替代 SUM",
        )
        child = service.get_version(child_id)
        assert child.parent_version_id == parent_id
        assert child.change_summary == "改用 AVG 替代 SUM"

    def test_rollback(self, service: SQLVersioningService, sample_sql):
        """测试回滚到指定版本"""
        v1_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        service.save_version(
            question="各城市销售汇总",
            sql=sample_sql.replace("SUM", "AVG"),
            user_id="test_user",
        )
        rolled_back_sql = service.rollback(v1_id)
        assert rolled_back_sql == sample_sql

    def test_compare_versions(self, service: SQLVersioningService, sample_sql):
        """测试对比两个版本"""
        v1_id = service.save_version(
            question="各城市销售汇总",
            sql=sample_sql,
            user_id="test_user",
        )
        v2_sql = sample_sql.replace("SUM", "AVG")
        v2_id = service.save_version(
            question="各城市销售汇总",
            sql=v2_sql,
            user_id="test_user",
        )
        diff = service.compare_versions(v1_id, v2_id)
        assert isinstance(diff, dict)
        assert "summary" in diff or "differences" in diff or "changes" in diff

    def test_version_model_fields(self, service: SQLVersioningService, sample_sql):
        """测试版本数据模型字段"""
        from datetime import datetime
        version_id = service.save_version(
            question="测试问题",
            sql=sample_sql,
            user_id="model_user",
            change_summary="初始版本",
        )
        version = service.get_version(version_id)
        assert version.id == version_id
        assert version.user_id == "model_user"
        assert version.question == "测试问题"
        assert version.sql == sample_sql
        assert isinstance(version.created_at, datetime)
        assert version.change_summary == "初始版本"

    def test_version_ordering(self, service: SQLVersioningService, sample_sql):
        """测试版本按时间排序（最新在前）"""
        service.save_version(question="q", sql=sample_sql + " v1", user_id="u")
        v2_id = service.save_version(question="q", sql=sample_sql + " v2", user_id="u")
        versions = service.list_versions(question="q", user_id="u")
        assert len(versions) == 2
        assert versions[0].id == v2_id  # 最新版本在前

    def test_multiple_users_isolated(self, service: SQLVersioningService, sample_sql):
        """测试多用户数据隔离"""
        service.save_version(question="q", sql="SQL_A", user_id="user_a")
        service.save_version(question="q", sql="SQL_B", user_id="user_b")
        versions_a = service.list_versions(question="q", user_id="user_a")
        versions_b = service.list_versions(question="q", user_id="user_b")
        assert len(versions_a) == 1
        assert len(versions_b) == 1
        assert versions_a[0].sql == "SQL_A"
        assert versions_b[0].sql == "SQL_B"

    def test_rollback_nonexistent(self, service: SQLVersioningService):
        """回滚不存在的版本应抛出异常"""
        with pytest.raises(ValueError):
            service.rollback(999999)
