"""Schema Registry 单元测试"""

import pytest
import tempfile
import os
from pathlib import Path
from unittest.mock import MagicMock, patch
from micro_genbi.semantic.schema_registry import (
    SchemaRegistry,
    ColumnInfo,
    TableInfo,
    DatabaseInfo,
    CrossDBRelation,
    get_schema_registry,
)


# ── Fixtures ────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_yaml_content():
    """示例 YAML 内容"""
    return """
databases:
  - id: sales
    display_name: 销售数据库
    db_category: primary
    description: 销售业务数据
    tables:
      - name: orders
        logical_name: 订单表
        description: 存储所有订单
        primary_key: id
        columns:
          - name: id
            logical_name: 订单ID
            type: INTEGER
            description: 主键
            is_primary_key: true
          - name: amount
            logical_name: 订单金额
            type: DECIMAL(18,2)
            description: 订单总金额
          - name: status
            logical_name: 订单状态
            type: VARCHAR(20)
            enum_values:
              pending: 待处理
              completed: 已完成
              cancelled: 已取消

  - id: warehouse
    display_name: 仓库数据库
    db_category: sibling
    siblings_group: inventory
    tables:
      - name: inventory
        logical_name: 库存表
        columns:
          - name: id
            logical_name: 库存ID
            type: INTEGER
          - name: quantity
            logical_name: 数量
            type: INTEGER

cross_db_relations:
  - source_table: sales.orders
    target_table: warehouse.inventory
    source_column: id
    target_column: order_id
    description: 订单关联库存
"""


@pytest.fixture
def yaml_file(sample_yaml_content):
    """创建临时 YAML 文件"""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".yaml", delete=False, encoding="utf-8"
    ) as f:
        f.write(sample_yaml_content)
        f.flush()
        yield Path(f.name)
    os.unlink(f.name)


@pytest.fixture
def schema_registry(yaml_file):
    """创建并加载 SchemaRegistry"""
    registry = SchemaRegistry(schema_path=yaml_file)
    registry.load()
    return registry


# ── Tests: Data Classes ─────────────────────────────────────────────────────

class TestColumnInfo:
    """列信息测试"""

    def test_column_info_creation(self):
        """测试列信息创建"""
        col = ColumnInfo(
            name="id",
            logical_name="ID",
            col_type="INTEGER",
            description="主键",
            enum_values={"active": "激活", "inactive": "未激活"},
            is_nullable=False,
            is_primary_key=True,
            sample_values=["1", "2", "3"],
        )
        assert col.name == "id"
        assert col.is_primary_key is True
        assert col.enum_values["active"] == "激活"

    def test_column_info_defaults(self):
        """测试默认值"""
        col = ColumnInfo(name="id", logical_name="ID", col_type="INTEGER")
        assert col.description == ""
        assert col.enum_values == {}
        assert col.is_nullable is True
        assert col.is_primary_key is False
        assert col.sample_values == []


class TestTableInfo:
    """表信息测试"""

    def test_table_info_creation(self):
        """测试表信息创建"""
        table = TableInfo(
            name="orders",
            logical_name="订单表",
            fqn="sales.orders",
            description="订单信息",
            primary_key="id",
        )
        assert table.name == "orders"
        assert table.fqn == "sales.orders"

    def test_table_info_defaults(self):
        """测试默认值"""
        table = TableInfo(name="t", logical_name="T", fqn="db.t")
        assert table.description == ""
        assert table.columns == []
        assert table.primary_key == ""


class TestDatabaseInfo:
    """数据库信息测试"""

    def test_database_info_creation(self):
        """测试数据库信息创建"""
        db = DatabaseInfo(
            id="sales",
            display_name="销售数据库",
            db_category="primary",
            siblings_group="sales",
            description="销售业务",
        )
        assert db.id == "sales"
        assert db.db_category == "primary"

    def test_database_info_defaults(self):
        """测试默认值"""
        db = DatabaseInfo(id="test", display_name="Test")
        assert db.db_category == "primary"
        assert db.siblings_group == ""
        assert db.description == ""
        assert db.connection_config == {}
        assert db.tables == []


class TestCrossDBRelation:
    """跨库关系测试"""

    def test_cross_db_relation_creation(self):
        """测试跨库关系创建"""
        rel = CrossDBRelation(
            source_table="sales.orders",
            target_table="warehouse.inventory",
            source_column="id",
            target_column="order_id",
            description="订单关联库存",
        )
        assert rel.source_table == "sales.orders"
        assert rel.target_column == "order_id"


# ── Tests: SchemaRegistry.load ─────────────────────────────────────────────

class TestSchemaRegistryLoad:
    """Schema 加载测试"""

    def test_load_from_file(self, yaml_file):
        """测试从文件加载"""
        registry = SchemaRegistry(schema_path=yaml_file)
        registry.load()
        assert registry._loaded is True

    def test_load_parses_databases(self, schema_registry):
        """测试解析数据库"""
        assert len(schema_registry._databases) == 2
        assert "sales" in schema_registry._databases
        assert "warehouse" in schema_registry._databases

    def test_load_parses_tables(self, schema_registry):
        """测试解析表"""
        assert len(schema_registry._tables) == 2
        assert "sales.orders" in schema_registry._tables
        assert "warehouse.inventory" in schema_registry._tables

    def test_load_parses_columns(self, schema_registry):
        """测试解析列"""
        orders = schema_registry._tables["sales.orders"]
        assert len(orders.columns) == 3
        col_names = [c.name for c in orders.columns]
        assert "id" in col_names
        assert "amount" in col_names
        assert "status" in col_names

    def test_load_parses_cross_db_relations(self, schema_registry):
        """测试解析跨库关系"""
        assert len(schema_registry._cross_db_relations) == 1
        rel = schema_registry._cross_db_relations[0]
        assert rel.source_table == "sales.orders"
        assert rel.target_table == "warehouse.inventory"

    def test_load_nonexistent_file(self):
        """测试加载不存在的文件"""
        registry = SchemaRegistry(schema_path=Path("/nonexistent/path.yaml"))
        registry.load()
        # 不抛异常，静默失败，_loaded 保持 False
        assert registry._loaded is False
        assert len(registry._databases) == 0


# ── Tests: SchemaRegistry.get_database ─────────────────────────────────────

class TestSchemaRegistryGetDatabase:
    """获取数据库测试"""

    def test_get_existing_database(self, schema_registry):
        """测试获取存在的数据库"""
        db = schema_registry.get_database("sales")
        assert db is not None
        assert db.display_name == "销售数据库"
        assert db.db_category == "primary"

    def test_get_nonexistent_database(self, schema_registry):
        """测试获取不存在的数据库"""
        db = schema_registry.get_database("nonexistent")
        assert db is None

    def test_get_all_databases(self, schema_registry):
        """测试获取所有数据库"""
        dbs = schema_registry.get_all_databases()
        assert len(dbs) == 2
        assert all(isinstance(db, DatabaseInfo) for db in dbs)


# ── Tests: SchemaRegistry.get_table ─────────────────────────────────────────

class TestSchemaRegistryGetTable:
    """获取表测试"""

    def test_get_existing_table(self, schema_registry):
        """测试获取存在的表"""
        table = schema_registry.get_table("sales.orders")
        assert table is not None
        assert table.logical_name == "订单表"

    def test_get_nonexistent_table(self, schema_registry):
        """测试获取不存在的表"""
        table = schema_registry.get_table("sales.nonexistent")
        assert table is None


# ── Tests: SchemaRegistry.find_table ───────────────────────────────────────

class TestSchemaRegistryFindTable:
    """查找表测试"""

    def test_find_by_logical_name(self, schema_registry):
        """测试按逻辑名称查找"""
        results = schema_registry.find_table_by_logical_name("订单")
        assert len(results) > 0
        assert any(t.logical_name == "订单表" for t in results)

    def test_find_by_name(self, schema_registry):
        """测试按表名查找"""
        results = schema_registry.find_table_by_logical_name("orders")
        assert len(results) > 0

    def test_find_case_insensitive(self, schema_registry):
        """测试大小写不敏感"""
        results1 = schema_registry.find_table_by_logical_name("ORDERS")
        results2 = schema_registry.find_table_by_logical_name("orders")
        assert len(results1) == len(results2)

    def test_find_no_match(self, schema_registry):
        """测试无匹配"""
        results = schema_registry.find_table_by_logical_name("xyz123nonexistent")
        assert len(results) == 0


# ── Tests: SchemaRegistry.multi-database detection ───────────────────────────

class TestSchemaRegistryMultiDB:
    """多数据库查询判断测试"""

    def test_single_database_query(self, schema_registry):
        """测试单数据库查询"""
        is_multi, mode = schema_registry.is_multi_database_query(["orders"])
        assert is_multi is False
        assert mode == "single"

    def test_multi_database_federated(self, schema_registry):
        """测试跨库查询"""
        is_multi, mode = schema_registry.is_multi_database_query(
            ["orders", "inventory"]
        )
        assert is_multi is True

    def test_multi_database_aggregate(self, schema_registry):
        """测试同构聚合查询"""
        # warehouse 是 sibling 组
        is_multi, mode = schema_registry.is_multi_database_query(["inventory"])
        # inventory 只在一个库中
        assert is_multi is False


# ── Tests: SchemaRegistry.get_cross_db_targets ─────────────────────────────

class TestSchemaRegistryCrossDB:
    """跨库关系测试"""

    def test_get_cross_db_targets(self, schema_registry):
        """测试获取跨库目标"""
        targets = schema_registry.get_cross_db_targets("sales.orders")
        assert len(targets) == 1
        assert targets[0].target_table == "warehouse.inventory"

    def test_get_cross_db_targets_none(self, schema_registry):
        """测试无跨库目标"""
        targets = schema_registry.get_cross_db_targets("warehouse.inventory")
        assert len(targets) == 0


# ── Tests: SchemaRegistry.build_llm_context ─────────────────────────────────

class TestSchemaRegistryBuildLLMContext:
    """LLM 上下文构建测试"""

    def test_build_context_basic(self, schema_registry):
        """测试基本上下文构建"""
        context = schema_registry.build_llm_context()
        assert "销售数据库" in context
        assert "订单表" in context
        assert "订单ID" in context

    def test_build_context_filtered_by_db(self, schema_registry):
        """测试按数据库过滤"""
        context = schema_registry.build_llm_context(involved_db_ids=["sales"])
        assert "销售数据库" in context
        # warehouse 不应该出现
        assert context.count("仓库数据库") == 0

    def test_build_context_max_tables(self, schema_registry):
        """测试最大表数量限制"""
        context = schema_registry.build_llm_context(max_tables=1)
        # 只有一个表
        assert "sales.orders" in context

    def test_build_context_without_relations(self, schema_registry):
        """测试不包含关系"""
        context = schema_registry.build_llm_context(include_relations=False)
        assert "跨库关联" not in context

    def test_build_context_includes_enum_values(self, schema_registry):
        """测试包含枚举值"""
        context = schema_registry.build_llm_context()
        assert "pending" in context or "待处理" in context

    def test_build_context_includes_primary_key(self, schema_registry):
        """测试包含主键标识"""
        context = schema_registry.build_llm_context()
        assert "PK" in context or "(PK)" in context


# ── Tests: SchemaRegistry.to_dict ───────────────────────────────────────────

class TestSchemaRegistryToDict:
    """导出字典测试"""

    def test_to_dict_structure(self, schema_registry):
        """测试导出结构"""
        d = schema_registry.to_dict()
        assert "databases" in d
        assert "cross_db_relations" in d
        assert len(d["databases"]) == 2

    def test_to_dict_database(self, schema_registry):
        """测试导出数据库"""
        d = schema_registry.to_dict()
        sales = next((db for db in d["databases"] if db["id"] == "sales"), None)
        assert sales is not None
        assert sales["display_name"] == "销售数据库"

    def test_to_dict_tables(self, schema_registry):
        """测试导出表"""
        d = schema_registry.to_dict()
        sales = next((db for db in d["databases"] if db["id"] == "sales"), None)
        tables = sales["tables"]
        assert len(tables) == 1
        assert tables[0]["name"] == "orders"

    def test_to_dict_columns(self, schema_registry):
        """测试导出列"""
        d = schema_registry.to_dict()
        sales = next((db for db in d["databases"] if db["id"] == "sales"), None)
        cols = sales["tables"][0]["columns"]
        assert len(cols) == 3
        assert cols[0]["name"] == "id"


# ── Tests: get_schema_registry ───────────────────────────────────────────────

class TestGetSchemaRegistry:
    """全局实例测试"""

    def test_get_schema_registry_returns_same_instance(self):
        """测试返回单例"""
        reg1 = get_schema_registry()
        reg2 = get_schema_registry()
        assert reg1 is reg2
