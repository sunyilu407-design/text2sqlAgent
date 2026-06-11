"""数据导出服务单元测试"""

import pytest
import os
import tempfile
import json
from unittest.mock import patch, MagicMock
from micro_genbi.service.data_exporter import (
    DataExporter,
    ExportRequest,
    ExportResult,
    export_to_csv,
    export_to_json,
    _check_rate_limit,
    rate_limit,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_data():
    """示例数据"""
    return [
        {"id": 1, "name": "Alice", "amount": 100.50},
        {"id": 2, "name": "Bob", "amount": 200.75},
        {"id": 3, "name": "Charlie", "amount": 150.00},
    ]


@pytest.fixture
def sample_columns():
    return ["id", "name", "amount"]


@pytest.fixture
def temp_dir():
    """临时目录"""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def exporter(temp_dir):
    """创建 DataExporter 实例"""
    return DataExporter(max_rows=10000, temp_dir=temp_dir)


# ── Tests: ExportRequest ─────────────────────────────────────────────────────

class TestExportRequest:
    """导出请求测试"""

    def test_export_request_creation(self):
        """测试请求创建"""
        req = ExportRequest(
            data=[{"id": 1}],
            columns=["id"],
            format="csv",
            filename="test",
            include_headers=True,
            max_rows=1000,
        )
        assert req.format == "csv"
        assert req.max_rows == 1000

    def test_export_request_defaults(self):
        """测试默认值"""
        req = ExportRequest(data=[], columns=["id"], format="csv")
        assert req.filename is None
        assert req.include_headers is True
        assert req.max_rows == 10000


# ── Tests: ExportResult ─────────────────────────────────────────────────────

class TestExportResult:
    """导出结果测试"""

    def test_export_result_creation(self):
        """测试结果创建"""
        from datetime import datetime
        result = ExportResult(
            file_path="/tmp/test.csv",
            file_size=1024,
            row_count=100,
            format="csv",
            created_at=datetime.now(),
        )
        assert result.file_size == 1024
        assert result.row_count == 100
        assert result.format == "csv"


# ── Tests: DataExporter initialization ─────────────────────────────────────

class TestDataExporterInit:
    """初始化测试"""

    def test_init_default_values(self):
        """测试默认值"""
        exporter = DataExporter()
        assert exporter._max_rows == 10000
        assert exporter._temp_dir == tempfile.gettempdir()
        assert exporter._executor is not None

    def test_init_custom_values(self, temp_dir):
        """测试自定义值"""
        exporter = DataExporter(max_rows=5000, temp_dir=temp_dir)
        assert exporter._max_rows == 5000
        assert exporter._temp_dir == temp_dir


# ── Tests: DataExporter._get_extension ──────────────────────────────────────

class TestGetExtension:
    """扩展名测试"""

    def test_extension_mapping(self, exporter):
        """测试扩展名映射"""
        assert exporter._get_extension("csv") == "csv"
        assert exporter._get_extension("excel") == "xlsx"
        assert exporter._get_extension("json") == "json"
        assert exporter._get_extension("sql") == "sql"
        assert exporter._get_extension("pdf") == "pdf"

    def test_extension_unknown(self, exporter):
        """测试未知格式"""
        assert exporter._get_extension("unknown") == "dat"


# ── Tests: DataExporter.export (format validation) ───────────────────────────

class TestExportFormatValidation:
    """格式验证测试"""

    def test_export_unsupported_format(self, exporter):
        """测试不支持的格式"""
        req = ExportRequest(
            data=[{"id": 1}],
            columns=["id"],
            format="unsupported",
        )
        with pytest.raises(ValueError) as exc_info:
            exporter.export(req)
        assert "unsupported" in str(exc_info.value).lower()

    def test_export_supported_formats(self, exporter):
        """测试支持的格式"""
        data = [{"id": 1, "name": "test"}]
        columns = ["id", "name"]
        for fmt in ["csv", "json", "sql"]:
            req = ExportRequest(data=data, columns=columns, format=fmt)
            # 不抛异常即通过
            result = exporter.export(req)
            assert result.format == fmt


# ── Tests: CSV Export ───────────────────────────────────────────────────────

class TestCSVExport:
    """CSV 导出测试"""

    def test_export_csv_creates_file(self, exporter, sample_data, sample_columns, temp_dir):
        """测试 CSV 文件创建"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="csv",
            filename="test_csv",
            include_headers=True,
        )
        result = exporter.export(req)
        assert os.path.exists(result.file_path)
        assert result.row_count == 3
        assert result.file_size > 0

    def test_export_csv_content(self, exporter, sample_data, sample_columns, temp_dir):
        """测试 CSV 内容"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="csv",
            include_headers=True,
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        assert "id" in content
        assert "Alice" in content
        assert "100.5" in content or "100.50" in content

    def test_export_csv_no_header(self, exporter, sample_data, sample_columns, temp_dir):
        """测试无表头导出"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="csv",
            include_headers=False,
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8-sig") as f:
            lines = f.readlines()
        # 第一行是数据，不是表头
        assert "Alice" in lines[0]
        assert lines[0].strip().count(",") == 2

    def test_export_csv_max_rows(self, exporter, temp_dir):
        """测试最大行数限制"""
        data = [{"id": i} for i in range(100)]
        req = ExportRequest(
            data=data,
            columns=["id"],
            format="csv",
            max_rows=10,
        )
        result = exporter.export(req)
        assert result.row_count == 10

    def test_export_csv_unicode(self, exporter, temp_dir):
        """测试中文导出"""
        data = [{"id": 1, "name": "张三", "amount": 100}]
        req = ExportRequest(
            data=data,
            columns=["id", "name", "amount"],
            format="csv",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
        assert "张三" in content


# ── Tests: JSON Export ──────────────────────────────────────────────────────

class TestJSONExport:
    """JSON 导出测试"""

    def test_export_json_creates_file(self, exporter, sample_data, sample_columns, temp_dir):
        """测试 JSON 文件创建"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="json",
            filename="test_json",
        )
        result = exporter.export(req)
        assert os.path.exists(result.file_path)
        assert result.row_count == 3

    def test_export_json_content(self, exporter, sample_data, sample_columns, temp_dir):
        """测试 JSON 内容"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="json",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        assert len(content) == 3
        assert content[0]["name"] == "Alice"

    def test_export_json_filters_columns(self, exporter, sample_data, temp_dir):
        """测试列过滤"""
        req = ExportRequest(
            data=sample_data,
            columns=["id", "name"],  # 不包含 amount
            format="json",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = json.load(f)
        assert "amount" not in content[0]
        assert "id" in content[0]


# ── Tests: SQL Export ───────────────────────────────────────────────────────

class TestSQLExport:
    """SQL 导出测试"""

    def test_export_sql_creates_file(self, exporter, sample_data, sample_columns, temp_dir):
        """测试 SQL 文件创建"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="sql",
            filename="test_sql",
        )
        result = exporter.export(req)
        assert os.path.exists(result.file_path)
        assert result.row_count == 3

    def test_export_sql_contains_create(self, exporter, sample_data, sample_columns, temp_dir):
        """测试包含 CREATE TABLE"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="sql",
            filename="my_table",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "CREATE TABLE" in content
        assert "my_table" in content

    def test_export_sql_contains_insert(self, exporter, sample_data, sample_columns, temp_dir):
        """测试包含 INSERT"""
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="sql",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "INSERT INTO" in content
        assert "Alice" in content

    def test_export_sql_escape_quotes(self, exporter, temp_dir):
        """测试引号转义"""
        data = [{"id": 1, "name": "O'Brien", "amount": 100}]
        req = ExportRequest(
            data=data,
            columns=["id", "name", "amount"],
            format="sql",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # O'Brien -> O''Brien
        assert "O''Brien" in content or "O\\'Brien" in content

    def test_export_sql_empty_data(self, exporter, sample_columns, temp_dir):
        """测试空数据"""
        req = ExportRequest(
            data=[],
            columns=sample_columns,
            format="sql",
        )
        result = exporter.export(req)
        with open(result.file_path, "r", encoding="utf-8") as f:
            content = f.read()
        assert "-- 无数据" in content


# ── Tests: Excel Export (fallback) ─────────────────────────────────────────

class TestExcelExport:
    """Excel 导出测试"""

    def test_export_excel_with_openpyxl(self, exporter, sample_data, sample_columns, temp_dir):
        """测试有 openpyxl 时的 Excel 导出"""
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            pytest.skip("openpyxl not installed")
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="excel",
        )
        result = exporter.export(req)
        assert os.path.exists(result.file_path)
        assert result.row_count == 3
        assert result.file_size > 0


# ── Tests: PDF Export (fallback) ─────────────────────────────────────────────

class TestPDFExport:
    """PDF 导出测试"""

    def test_export_pdf_with_reportlab(self, exporter, sample_data, sample_columns, temp_dir):
        """测试有 reportlab 时的 PDF 导出"""
        try:
            import reportlab  # noqa: F401
        except ImportError:
            pytest.skip("reportlab not installed")
        req = ExportRequest(
            data=sample_data,
            columns=sample_columns,
            format="pdf",
        )
        result = exporter.export(req)
        assert os.path.exists(result.file_path)
        assert result.row_count == 3
        assert result.file_size > 0


# ── Tests: Rate Limiting ─────────────────────────────────────────────────────

class TestRateLimiting:
    """频率限制测试"""

    def test_rate_limit_first_request(self):
        """测试首次请求通过"""
        import micro_genbi.service.data_exporter as de
        original_cache = de._rate_limit_cache.copy()
        de._rate_limit_cache.clear()
        try:
            result = de._check_rate_limit("user1", limit=10, window=60.0)
            assert result is True
        finally:
            de._rate_limit_cache.clear()
            de._rate_limit_cache.update(original_cache)

    def test_rate_limit_within_limit(self):
        """测试限制内请求"""
        import micro_genbi.service.data_exporter as de
        original_cache = de._rate_limit_cache.copy()
        de._rate_limit_cache.clear()
        de._rate_limit_cache["user1"] = [0.0, 1.0, 2.0]
        try:
            result = de._check_rate_limit("user1", limit=10, window=60.0)
            assert result is True
        finally:
            de._rate_limit_cache.clear()
            de._rate_limit_cache.update(original_cache)

    def test_rate_limit_exceeded(self):
        """测试超限拒绝"""
        import micro_genbi.service.data_exporter as de
        import time
        original_cache = de._rate_limit_cache.copy()
        now = time.time()
        de._rate_limit_cache.clear()
        # 填满 10 个请求（都在时间窗口内）
        de._rate_limit_cache["user1"] = [now - i for i in range(10)]
        try:
            result = de._check_rate_limit("user1", limit=10, window=60.0)
            assert result is False
        finally:
            de._rate_limit_cache.clear()
            de._rate_limit_cache.update(original_cache)

    def test_rate_limit_different_users(self):
        """测试不同用户独立计数"""
        import micro_genbi.service.data_exporter as de
        import time
        original_cache = de._rate_limit_cache.copy()
        now = time.time()
        de._rate_limit_cache.clear()
        # user1 满 10 个，user2 只有 1 个
        de._rate_limit_cache["user1"] = [now - i for i in range(10)]
        de._rate_limit_cache["user2"] = [now]
        try:
            result1 = de._check_rate_limit("user1", limit=10, window=60.0)
            result2 = de._check_rate_limit("user2", limit=10, window=60.0)
            assert result1 is False
            assert result2 is True
        finally:
            de._rate_limit_cache.clear()
            de._rate_limit_cache.update(original_cache)

    def test_rate_limit_cleans_old_records(self):
        """测试清理过期记录"""
        import micro_genbi.service.data_exporter as de
        import time
        original_cache = de._rate_limit_cache.copy()
        old_time = time.time() - 120  # 2 分钟前
        de._rate_limit_cache.clear()
        de._rate_limit_cache["user1"] = [old_time, old_time, old_time]
        try:
            result = de._check_rate_limit("user1", limit=3, window=60.0)
            assert result is True
        finally:
            de._rate_limit_cache.clear()
            de._rate_limit_cache.update(original_cache)


# ── Tests: Convenience Functions ─────────────────────────────────────────────

class TestConvenienceFunctions:
    """便捷函数测试"""

    def test_export_to_csv(self, sample_data, sample_columns, temp_dir):
        """测试 CSV 便捷导出"""
        file_path = os.path.join(temp_dir, "test_conv.csv")
        result = export_to_csv(sample_data, sample_columns, file_path)
        assert os.path.exists(result.file_path)
        assert result.format == "csv"

    def test_export_to_json(self, sample_data, sample_columns, temp_dir):
        """测试 JSON 便捷导出"""
        file_path = os.path.join(temp_dir, "test_conv.json")
        result = export_to_json(sample_data, sample_columns, file_path)
        assert os.path.exists(result.file_path)
        assert result.format == "json"
