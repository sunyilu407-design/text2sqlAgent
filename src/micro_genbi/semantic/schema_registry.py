"""Schema 注册表模块

负责多数据库语义配置的统一管理和 LLM 上下文构建。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, Any
import yaml


@dataclass
class ColumnInfo:
    """列信息"""
    name: str
    logical_name: str
    col_type: str
    description: str = ""
    enum_values: dict[str, str] = field(default_factory=dict)
    is_nullable: bool = True
    is_primary_key: bool = False
    sample_values: list[str] = field(default_factory=list)


@dataclass
class TableInfo:
    """表信息"""
    name: str
    logical_name: str
    fqn: str  # fully qualified name: db.schema.table
    description: str = ""
    columns: list[ColumnInfo] = field(default_factory=list)
    primary_key: str = ""


@dataclass
class DatabaseInfo:
    """数据库信息"""
    id: str
    display_name: str
    db_category: str = "primary"  # primary / sibling / heterogenous
    siblings_group: str = ""      # 同构组标识
    description: str = ""
    connection_config: dict[str, Any] = field(default_factory=dict)
    tables: list[TableInfo] = field(default_factory=list)


@dataclass
class CrossDBRelation:
    """跨库关系"""
    source_table: str
    target_table: str
    source_column: str
    target_column: str
    description: str = ""


class SchemaRegistry:
    """
    Schema 注册表

    负责：
    - 加载和缓存 schema.yaml 配置
    - 提供表/列的语义信息查询
    - 构建 LLM 可读的上下文信息
    - 支持多数据库场景下的语义隔离
    """

    def __init__(self, schema_path: str | Path | None = None):
        """
        Args:
            schema_path: schema.yaml 文件路径
        """
        self._schema_path = Path(schema_path) if schema_path else None
        self._databases: dict[str, DatabaseInfo] = {}
        self._tables: dict[str, TableInfo] = {}  # fqn -> TableInfo
        self._cross_db_relations: list[CrossDBRelation] = []
        self._loaded = False

    def load(self, schema_path: str | Path | None = None) -> None:
        """
        加载 schema 配置

        Args:
            schema_path: 可选的 schema.yaml 路径，优先级高于构造函数中的路径
        """
        path = Path(schema_path) if schema_path else self._schema_path
        if not path:
            return

        if not path.exists():
            return

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        self._parse_config(data)
        self._loaded = True

    def _parse_config(self, data: dict) -> None:
        """解析配置数据"""
        # 解析数据库信息
        for db_data in data.get("databases", []):
            db = DatabaseInfo(
                id=db_data["id"],
                display_name=db_data.get("display_name", db_data["id"]),
                db_category=db_data.get("db_category", "primary"),
                siblings_group=db_data.get("siblings_group", ""),
                description=db_data.get("description", ""),
                connection_config=db_data.get("connection", {}),
            )

            # 解析表信息
            for table_data in db_data.get("tables", []):
                table = TableInfo(
                    name=table_data["name"],
                    logical_name=table_data.get("logical_name", table_data["name"]),
                    fqn=f"{db.id}.{table_data['name']}",
                    description=table_data.get("description", ""),
                    primary_key=table_data.get("primary_key", ""),
                )

                # 解析列信息
                for col_data in table_data.get("columns", []):
                    col = ColumnInfo(
                        name=col_data["name"],
                        logical_name=col_data.get("logical_name", col_data["name"]),
                        col_type=col_data.get("type", "TEXT"),
                        description=col_data.get("description", ""),
                        enum_values=col_data.get("enum_values", {}),
                        is_nullable=col_data.get("nullable", True),
                        is_primary_key=col_data.get("is_primary_key", False),
                        sample_values=col_data.get("sample_values", []),
                    )
                    table.columns.append(col)

                db.tables.append(table)
                self._tables[table.fqn] = table

            self._databases[db.id] = db

        # 解析跨库关系
        for rel in data.get("cross_db_relations", []):
            self._cross_db_relations.append(CrossDBRelation(
                source_table=rel["source_table"],
                target_table=rel["target_table"],
                source_column=rel.get("source_column", "id"),
                target_column=rel.get("target_column", "id"),
                description=rel.get("description", ""),
            ))

    def get_database(self, db_id: str) -> Optional[DatabaseInfo]:
        """获取数据库信息"""
        return self._databases.get(db_id)

    def get_all_databases(self) -> list[DatabaseInfo]:
        """获取所有数据库"""
        return list(self._databases.values())

    def get_table(self, fqn: str) -> Optional[TableInfo]:
        """通过 FQN 获取表信息"""
        return self._tables.get(fqn)

    def find_table_by_logical_name(self, logical_name: str) -> list[TableInfo]:
        """通过逻辑名称查找表（模糊匹配）"""
        results = []
        name_lower = logical_name.lower()
        for table in self._tables.values():
            if (name_lower in table.logical_name.lower() or
                name_lower in table.name.lower()):
                results.append(table)
        return results

    def get_databases_involving_tables(self, table_names: list[str]) -> set[str]:
        """获取涉及指定表的所有数据库 ID"""
        db_ids = set()
        for table in self._tables.values():
            if table.name in table_names:
                db_ids.add(table.fqn.split(".")[0])
        return db_ids

    def get_siblings_group(self, db_id: str) -> list[str]:
        """获取同构组的其他数据库 ID"""
        db = self._databases.get(db_id)
        if not db or not db.siblings_group:
            return []

        return [
            d.id for d in self._databases.values()
            if d.siblings_group == db.siblings_group
        ]

    def get_cross_db_targets(self, table_fqn: str) -> list[CrossDBRelation]:
        """获取表的所有跨库关联关系"""
        return [
            r for r in self._cross_db_relations
            if r.source_table == table_fqn
        ]

    def is_multi_database_query(self, table_names: list[str]) -> tuple[bool, str]:
        """
        判断是否为多数据库查询

        Returns:
            (is_multi, mode)
            - (False, "single"): 单库查询
            - (True, "aggregate"): 同构多库聚合
            - (True, "federated"): 异构跨库 JOIN
        """
        involved_dbs = self.get_databases_involving_tables(table_names)

        if len(involved_dbs) <= 1:
            return False, "single"

        # 检查是否为同构聚合
        all_sources = set()
        for db in self._databases.values():
            if db.db_category == "sibling":
                all_sources.update(t.fqn for t in db.tables)

        involved = set()
        for table in self._tables.values():
            if table.name in table_names:
                involved.add(table.fqn)

        if involved.issubset(all_sources) and len(involved) > 1:
            return True, "aggregate"

        return True, "federated"

    def build_llm_context(
        self,
        involved_db_ids: list[str] | None = None,
        max_tables: int = 10,
        include_relations: bool = True,
    ) -> str:
        """
        构建 LLM 可读的语义上下文（用于注入 System Prompt）。

        Args:
            involved_db_ids: 只包含涉及这些数据库的 schema，None 表示全部
            max_tables: 最大表数量（防止 token 爆炸）
            include_relations: 是否包含跨库关系

        Returns:
            LLM 可读的 schema 上下文字符串
        """
        lines = ["# 数据库语义配置\n"]

        # 选择要包含的数据库
        if involved_db_ids:
            dbs = [self._databases[did] for did in involved_db_ids
                   if did in self._databases]
        else:
            dbs = list(self._databases.values())

        # 限制表数量
        all_tables: list[TableInfo] = []
        for db in dbs:
            all_tables.extend(db.tables)

        if len(all_tables) > max_tables:
            # 按表名长度优先（较短的表名通常更核心）
            all_tables.sort(key=lambda t: (len(t.name), t.name))
            all_tables = all_tables[:max_tables]

        # 按数据库分组
        db_table_map: dict[str, list[TableInfo]] = {}
        for table in all_tables:
            db_id = table.fqn.split(".")[0]
            if db_id not in db_table_map:
                db_table_map[db_id] = []
            db_table_map[db_id].append(table)

        for db in dbs:
            if db.id not in db_table_map:
                continue

            tables = db_table_map[db.id]
            category_desc = {
                "primary": "主库",
                "sibling": "同构聚合库",
                "heterogenous": "异构库",
            }.get(db.db_category, db.db_category)

            lines.append(f"## 数据库：{db.display_name} (ID: {db.id})")
            lines.append(f"类型：{category_desc}")

            for table in tables:
                lines.append(f"\n### {table.logical_name} (`{table.fqn}`)")
                if table.description:
                    lines.append(f"描述：{table.description}")

                for col in table.columns:
                    parts = [f"{col.logical_name}({col.name})", col.col_type]

                    # 添加枚举值信息
                    if col.enum_values:
                        items = " / ".join(f"{k}={v}" for k, v in col.enum_values.items())
                        parts.append(f"[枚举：{items}]")

                    # 添加主键标识
                    if col.is_primary_key or col.name == table.primary_key:
                        parts.append("(PK)")

                    # 添加可空标识
                    if not col.is_nullable:
                        parts.append("(NOT NULL)")

                    lines.append(f"- {' '.join(parts)}")

                    # 添加列描述
                    if col.description and col.description != col.logical_name:
                        lines.append(f"  说明：{col.description}")

                # 添加跨库关系
                if include_relations:
                    cross = self.get_cross_db_targets(table.fqn)
                    for rel in cross:
                        lines.append(f"  → 可跨库关联到 `{rel.target_table}` "
                                   f"({rel.source_column} → {rel.target_column})")

            lines.append("")

        # 添加跨库关系总览
        if include_relations and self._cross_db_relations:
            lines.append("## 跨库关系总览")
            for rel in self._cross_db_relations:
                lines.append(f"- `{rel.source_table}` → `{rel.target_table}` "
                           f"({rel.description or '跨库关联'})")
            lines.append("")

        return "\n".join(lines)

    def to_dict(self) -> dict:
        """导出为字典（用于调试）"""
        return {
            "databases": [
                {
                    "id": db.id,
                    "display_name": db.display_name,
                    "db_category": db.db_category,
                    "tables": [
                        {
                            "name": t.name,
                            "logical_name": t.logical_name,
                            "fqn": t.fqn,
                            "columns": [
                                {
                                    "name": c.name,
                                    "logical_name": c.logical_name,
                                    "type": c.col_type,
                                }
                                for c in t.columns
                            ],
                        }
                        for t in db.tables
                    ],
                }
                for db in self._databases.values()
            ],
            "cross_db_relations": [
                {
                    "source_table": r.source_table,
                    "target_table": r.target_table,
                }
                for r in self._cross_db_relations
            ],
        }


# 全局实例
_schema_registry: Optional[SchemaRegistry] = None


def get_schema_registry() -> SchemaRegistry:
    """获取全局 SchemaRegistry 实例"""
    global _schema_registry
    if _schema_registry is None:
        _schema_registry = SchemaRegistry()
    return _schema_registry
