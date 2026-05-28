#!/usr/bin/env python3
"""Schema 抽取工具

从数据库中抽取表结构，生成 schema.yaml 配置文件。
支持 PostgreSQL、MySQL、SQLite。
"""

import asyncio
import sys
import os
from pathlib import Path
from typing import Optional
import argparse
import json

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from micro_genbi import get_logger
from micro_genbi.db.engine import DatabaseExecutor

logger = get_logger(__name__)


# =============================================================================
# Schema 抽取器
# =============================================================================

class SchemaExtractor:
    """Schema 抽取器"""

    def __init__(self, db_url: str):
        self.db_url = db_url
        self.executor = DatabaseExecutor(db_url)

    async def extract(self) -> dict:
        """从数据库抽取 Schema"""
        logger.info(f"正在连接数据库: {self.db_url}")

        # 获取所有表
        tables = await self.get_tables()

        schema = {
            "schema_version": "1.0",
            "table_aliases": {},
            "semantic_descriptions": {},
            "relationships": [],
            "sample_values": {},
        }

        for table_name in tables:
            logger.info(f"抽取表: {table_name}")

            # 获取列信息
            columns = await self.get_columns(table_name)

            # 添加表别名
            schema["table_aliases"][table_name] = table_name

            # 添加表描述
            schema["semantic_descriptions"][table_name] = {
                "name": table_name,
                "description": f"表 {table_name}",
                "columns": {},
            }

            # 添加列描述
            for col in columns:
                col_name = col["name"]
                schema["semantic_descriptions"][table_name]["columns"][col_name] = (
                    f"{col_name} ({col['type']})"
                )

        return schema

    async def get_tables(self) -> list[str]:
        """获取所有表名"""
        db_type = self._get_db_type()

        if db_type == "postgresql":
            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                AND table_type = 'BASE TABLE'
            """
        elif db_type == "mysql":
            sql = """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = DATABASE()
                AND table_type = 'BASE TABLE'
            """
        elif db_type == "sqlite":
            sql = """
                SELECT name
                FROM sqlite_master
                WHERE type = 'table'
                AND name NOT LIKE 'sqlite_%'
            """
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        result = await self.executor.execute_raw(sql)
        return [row[0] for row in result]

    async def get_columns(self, table_name: str) -> list[dict]:
        """获取表的列信息"""
        db_type = self._get_db_type()

        if db_type == "postgresql":
            sql = """
                SELECT
                    column_name,
                    data_type,
                    is_nullable,
                    column_default,
                    character_maximum_length,
                    numeric_precision
                FROM information_schema.columns
                WHERE table_schema = 'public'
                AND table_name = %s
                ORDER BY ordinal_position
            """
        elif db_type == "mysql":
            sql = f"""
                SELECT
                    column_name,
                    CONCAT(data_type,
                        IF (character_maximum_length IS NOT NULL,
                            CONCAT('(', character_maximum_length, ')'),
                            IF (numeric_precision IS NOT NULL,
                                CONCAT('(', numeric_precision,
                                    IF (numeric_scale IS NOT NULL,
                                        CONCAT(',', numeric_scale),
                                        ''), ')'),
                                '')))
                    AS data_type,
                    is_nullable,
                    column_default
                FROM information_schema.columns
                WHERE table_schema = DATABASE()
                AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """
            result = await self.executor.execute_raw(sql)
            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": row[3],
                }
                for row in result
            ]
        elif db_type == "sqlite":
            sql = f"PRAGMA table_info({table_name})"
            result = await self.executor.execute_raw(sql)
            return [
                {
                    "name": row[1],
                    "type": row[2] or "TEXT",
                    "nullable": not row[3],
                    "default": row[4],
                }
                for row in result
            ]
        else:
            raise ValueError(f"不支持的数据库类型: {db_type}")

        if db_type == "postgresql":
            result = await self.executor.execute_raw(sql, (table_name,))
            return [
                {
                    "name": row[0],
                    "type": row[1],
                    "nullable": row[2] == "YES",
                    "default": row[3],
                }
                for row in result
            ]

        return []

    def _get_db_type(self) -> str:
        """获取数据库类型"""
        url = self.db_url.lower()
        if "postgresql" in url:
            return "postgresql"
        elif "mysql" in url:
            return "mysql"
        elif "sqlite" in url:
            return "sqlite"
        else:
            return "unknown"


def generate_yaml(schema: dict) -> str:
    """生成 YAML 格式的 Schema 配置"""
    lines = [
        "# Schema 配置文件",
        f"# 由 schema_extract.py 自动生成",
        f"# 生成时间: {__import__('datetime').datetime.now().isoformat()}",
        "",
        f"schema_version: \"{schema['schema_version']}\"",
        "",
        "# ---------------------------------------------------------------------------",
        "# 表别名映射（英文表名 -> 中文显示名）",
        "# ---------------------------------------------------------------------------",
        "table_aliases:",
    ]

    for table, alias in schema.get("table_aliases", {}).items():
        lines.append(f"  {table}: \"{alias}\"")

    lines.extend([
        "",
        "# ---------------------------------------------------------------------------",
        "# 语义描述",
        "# ---------------------------------------------------------------------------",
        "semantic_descriptions:",
    ])

    for table, desc in schema.get("semantic_descriptions", {}).items():
        lines.append(f"  {table}:")
        lines.append(f"    name: \"{desc.get('name', table)}\"")
        if desc.get("description"):
            lines.append(f"    description: \"{desc['description']}\"")
        if desc.get("columns"):
            lines.append("    columns:")

            col: str
            for col, col_desc in desc["columns"].items():
                if isinstance(col_desc, str):
                    lines.append(f"      {col}: \"{col_desc}\"")

    return "\n".join(lines)


# =============================================================================
# 主函数
# =============================================================================

async def main():
    """主函数"""
    parser = argparse.ArgumentParser(description="Micro-GenBI Schema 抽取工具")
    parser.add_argument("--db-url", "-d", help="数据库连接 URL")
    parser.add_argument("--output", "-o", default="schema.yaml", help="输出文件路径")
    parser.add_argument("--format", "-f", choices=["yaml", "json"], default="yaml", help="输出格式")

    args = parser.parse_args()

    # 获取数据库 URL
    db_url = args.db_url or os.getenv("DATABASE_URL")

    if not db_url:
        print("错误: 请通过 --db-url 参数或 DATABASE_URL 环境变量指定数据库连接")
        print("\n示例:")
        print("  # PostgreSQL")
        print("  python scripts/schema_extract.py --db-url 'postgresql://user:pass@localhost:5432/mydb'")
        print("")
        print("  # MySQL")
        print("  python scripts/schema_extract.py --db-url 'mysql://user:pass@localhost:3306/mydb'")
        print("")
        print("  # SQLite")
        print("  python scripts/schema_extract.py --db-url 'sqlite:///./mydb.db'")
        return 1

    print("=" * 50)
    print("Micro-GenBI Schema 抽取工具")
    print("=" * 50)
    print(f"数据库: {db_url}")
    print(f"输出文件: {args.output}")
    print("-" * 50)

    try:
        extractor = SchemaExtractor(db_url)
        schema = await extractor.extract()

        # 生成输出
        if args.format == "yaml":
            output = generate_yaml(schema)
        else:
            output = json.dumps(schema, indent=2, ensure_ascii=False)

        # 写入文件
        with open(args.output, "w", encoding="utf-8") as f:
            f.write(output)

        print("-" * 50)
        print(f"✅ Schema 抽取成功!")
        print(f"   表数量: {len(schema.get('table_aliases', {}))}")
        print(f"   输出文件: {args.output}")

        return 0

    except Exception as e:
        print("-" * 50)
        print(f"❌ Schema 抽取失败: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
