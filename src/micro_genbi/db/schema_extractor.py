"""Schema 抽取服务

从真实数据库中自动发现：
- 表结构（列名、类型、是否可空）
- 主键
- 外键（库内和跨库）
- 索引
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Any
import logging

from sqlalchemy import (
    text, inspect, MetaData, Table, Column,
    ForeignKeyConstraint, PrimaryKeyConstraint, Index,
)
from sqlalchemy.engine import Engine, Connection
from sqlalchemy.ext.asyncio import AsyncEngine

logger = logging.getLogger(__name__)


@dataclass
class ExtractedColumn:
    """抽取到的列"""
    name: str
    col_type: str
    nullable: bool = True
    is_primary_key: bool = False
    is_foreign_key: bool = False
    default_value: Optional[str] = None
    description: str = ""
    sample_values: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "type": self.col_type,
            "nullable": self.nullable,
            "is_primary_key": self.is_primary_key,
            "is_foreign_key": self.is_foreign_key,
            "default": self.default_value,
            "description": self.description,
        }


@dataclass
class ExtractedForeignKey:
    """抽取到的外键"""
    name: str
    constrained_columns: list[str]
    referred_table: str
    referred_columns: list[str]
    onupdate: str = "NO ACTION"
    ondelete: str = "NO ACTION"

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "constrained_columns": self.constrained_columns,
            "referred_table": self.referred_table,
            "referred_columns": self.referred_columns,
            "onupdate": self.onupdate,
            "ondelete": self.ondelete,
        }


@dataclass
class ExtractedIndex:
    """抽取到的索引"""
    name: str
    columns: list[str]
    unique: bool = False
    is_primary: bool = False

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "columns": self.columns,
            "unique": self.unique,
            "is_primary": self.is_primary,
        }


@dataclass
class ExtractedTable:
    """抽取到的表"""
    name: str
    schema: str = ""
    columns: list[ExtractedColumn] = field(default_factory=list)
    primary_keys: list[str] = field(default_factory=list)
    foreign_keys: list[ExtractedForeignKey] = field(default_factory=list)
    indexes: list[ExtractedIndex] = field(default_factory=list)
    row_count: Optional[int] = None
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "schema": self.schema,
            "columns": [c.to_dict() for c in self.columns],
            "primary_keys": self.primary_keys,
            "foreign_keys": [f.to_dict() for f in self.foreign_keys],
            "indexes": [i.to_dict() for i in self.indexes],
            "row_count": self.row_count,
            "description": self.description,
        }


@dataclass
class ExtractedSchema:
    """抽取到的完整 schema"""
    database_name: str
    database_type: str
    tables: list[ExtractedTable] = field(default_factory=list)
    relationships: list[ExtractedForeignKey] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "database_name": self.database_name,
            "database_type": self.database_type,
            "tables": [t.to_dict() for t in self.tables],
            "relationships": [r.to_dict() for r in self.relationships],
        }


class SchemaExtractor:
    """
    数据库 Schema 抽取器。

    支持 PostgreSQL、MySQL、SQLite 自动发现表结构、主键、外键和索引。
    """

    def __init__(self, engine: Engine | AsyncEngine):
        self.engine = engine
        self._inspector = None

    def _get_inspector(self):
        """获取 SQLAlchemy inspector（延迟初始化）"""
        if self._inspector is None:
            self._inspector = inspect(self.engine.sync_engine if hasattr(self.engine, "sync_engine") else self.engine)
        return self._inspector

    def extract_sync(self) -> ExtractedSchema:
        """
        同步抽取 schema。

        Returns:
            ExtractedSchema: 包含所有表结构和关系的 schema 对象
        """
        inspector = self._get_inspector()

        # 获取数据库名称
        db_name = self._get_database_name_sync()
        db_type = self._detect_db_type()

        # 获取所有表
        schema_name = self._get_schema_name()
        table_names = inspector.get_table_names(schema=schema_name or None)

        tables = []
        all_relationships = []

        for table_name in table_names:
            table_info = self._extract_table_sync(inspector, table_name, schema_name)
            tables.append(table_info)
            all_relationships.extend(table_info.foreign_keys)

        return ExtractedSchema(
            database_name=db_name,
            database_type=db_type,
            tables=tables,
            relationships=all_relationships,
        )

    def _extract_table_sync(
        self, inspector, table_name: str, schema_name: Optional[str]
    ) -> ExtractedTable:
        """同步抽取单个表"""
        # 获取列信息
        columns = []
        pk_columns = set()

        cols = inspector.get_columns(table_name, schema=schema_name or None)
        for col in cols:
            is_pk = col.get("primary_key", False)
            if is_pk:
                pk_columns.add(col["name"])
            columns.append(ExtractedColumn(
                name=col["name"],
                col_type=str(col["type"]),
                nullable=not col.get("nullable", False) if col.get("nullable") is not None else True,
                is_primary_key=is_pk,
                default_value=str(col.get("default")) if col.get("default") else None,
            ))

        # 获取主键
        pk_info = inspector.get_pk_constraint(table_name, schema=schema_name or None)
        primary_keys = list(pk_info.get("constrained_columns", [])) if pk_info else []

        # 获取外键
        foreign_keys = []
        fks = inspector.get_foreign_keys(table_name, schema=schema_name or None)
        for fk in fks:
            foreign_keys.append(ExtractedForeignKey(
                name=fk.get("name", ""),
                constrained_columns=fk.get("constrained_columns", []),
                referred_table=fk.get("referred_table", ""),
                referred_columns=fk.get("referred_columns", []),
                onupdate=fk.get("onupdate", "NO ACTION"),
                ondelete=fk.get("ondelete", "NO ACTION"),
            ))

        # 获取索引
        indexes = []
        idxs = inspector.get_indexes(table_name, schema=schema_name or None)
        for idx in idxs:
            if idx.get("name", "").startswith("idx_"):
                continue
            indexes.append(ExtractedIndex(
                name=idx.get("name", ""),
                columns=idx.get("column_names", []),
                unique=idx.get("unique", False),
                is_primary=False,
            ))

        # 标记列中的外键
        for fk in foreign_keys:
            for col_name in fk.constrained_columns:
                for col in columns:
                    if col.name == col_name:
                        col.is_foreign_key = True

        # 获取行数（可选，异步大表可能较慢）
        row_count = self._get_row_count_sync(table_name, schema_name)

        return ExtractedTable(
            name=table_name,
            schema=schema_name or "",
            columns=columns,
            primary_keys=primary_keys,
            foreign_keys=foreign_keys,
            indexes=indexes,
            row_count=row_count,
        )

    def _get_database_name_sync(self) -> str:
        """获取数据库名称"""
        try:
            with self.engine.connect() as conn:
                if self._detect_db_type() == "postgresql":
                    result = conn.execute(text("SELECT current_database()"))
                    row = result.fetchone()
                    return row[0] if row else "unknown"
                elif self._detect_db_type() == "mysql":
                    result = conn.execute(text("SELECT DATABASE()"))
                    row = result.fetchone()
                    return row[0] if row else "unknown"
                elif self._detect_db_type() == "sqlite":
                    result = conn.execute(text("SELECT sqlite_source_id()"))
                    row = result.fetchone()
                    return row[0] if row else "sqlite_db"
        except Exception:
            return "unknown"

    def _detect_db_type(self) -> str:
        """检测数据库类型"""
        url = str(self.engine.url)
        if "postgresql" in url:
            return "postgresql"
        elif "mysql" in url:
            return "mysql"
        elif "sqlite" in url:
            return "sqlite"
        elif "clickhouse" in url:
            return "clickhouse"
        return "unknown"

    def _get_schema_name(self) -> Optional[str]:
        """获取默认 schema 名称"""
        db_type = self._detect_db_type()
        if db_type == "postgresql":
            return "public"
        elif db_type == "mysql":
            return self.engine.url.database
        return None

    def _get_row_count_sync(self, table_name: str, schema_name: Optional[str]) -> Optional[int]:
        """获取表的行数"""
        try:
            with self.engine.connect() as conn:
                safe_table = self._quote_table_name(table_name, schema_name)
                result = conn.execute(text(f"SELECT COUNT(*) FROM {safe_table}"))
                row = result.fetchone()
                return int(row[0]) if row else 0
        except Exception as e:
            logger.warning(f"Failed to get row count for {table_name}: {e}")
            return None

    def _quote_table_name(self, table_name: str, schema_name: Optional[str]) -> str:
        """正确引用表名"""
        db_type = self._detect_db_type()
        if schema_name:
            full_name = f"{schema_name}.{table_name}"
        else:
            full_name = table_name

        if db_type == "postgresql":
            parts = full_name.split(".")
            return ".".join(f'"{p}"' for p in parts)
        elif db_type == "mysql":
            return f"`{full_name.replace('.', '`.`')}`"
        else:
            return full_name

    def build_er_context(self, schema: ExtractedSchema) -> str:
        """
        从抽取的 schema 构建 LLM 可读的 ER 上下文。

        用于注入到 LLM prompt 中，让 LLM 理解表之间的关联关系。
        """
        lines = [f"# 数据库：`{schema.database_name}` ({schema.database_type})"]
        lines.append("")

        for table in schema.tables:
            lines.append(f"## {table.name}")
            if table.description:
                lines.append(f"描述：{table.description}")
            lines.append(f"主键：{', '.join(table.primary_keys) if table.primary_keys else '无'}")

            # 列
            for col in table.columns:
                parts = [col.name, col.col_type]
                if col.is_primary_key:
                    parts.append("PK")
                if col.is_foreign_key:
                    parts.append("FK")
                if not col.nullable:
                    parts.append("NOT NULL")
                lines.append(f"- {' '.join(parts)}")

            # 库内关联
            if table.foreign_keys:
                for fk in table.foreign_keys:
                    lines.append(
                        f"  → 外键：{fk.constrained_columns} → "
                        f"{fk.referred_table}({fk.referred_columns})"
                    )

            lines.append("")

        return "\n".join(lines)

    def generate_yaml_config(self, schema: ExtractedSchema) -> str:
        """
        从抽取的 schema 生成 YAML 配置文件。

        用户可以在此基础上补充 description 和 enum_values。
        """
        import yaml

        tables_list = []
        for table in schema.tables:
            cols = []
            for col in table.columns:
                col_entry: dict[str, Any] = {
                    "name": col.name,
                    "logical_name": col.name,
                    "type": col.col_type,
                }
                if col.is_primary_key:
                    col_entry["is_primary_key"] = True
                if not col.nullable:
                    col_entry["nullable"] = False
                if col.description:
                    col_entry["description"] = col.description
                cols.append(col_entry)

            table_entry: dict[str, Any] = {
                "name": table.name,
                "logical_name": table.name,
                "columns": cols,
            }
            if table.description:
                table_entry["description"] = table.description

            tables_list.append(table_entry)

        config = {
            "database": {
                "id": schema.database_name,
                "display_name": schema.database_name,
                "dialect": schema.database_type,
            },
            "tables": tables_list,
        }

        return yaml.dump(config, allow_unicode=True, sort_keys=False, default_flow_style=False)
