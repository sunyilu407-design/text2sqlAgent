#!/usr/bin/env python3
"""Schema 抽取脚本

从目标数据库自动抽取表结构并生成 schema.yaml 配置文件。
支持 PostgreSQL、MySQL、SQLite。

用法:
    python scripts/extract_schema.py --db-type postgresql --host localhost \
        --port 5432 --database mydb --username user --password pass \
        --output schema.yaml

    # 从连接 URL 读取
    python scripts/extract_schema.py --url "postgresql://user:pass@localhost:5432/mydb" \
        --output schema.yaml
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any, Optional

import yaml

# 添加 src 目录到路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="从数据库抽取 Schema 并生成 schema.yaml",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--url", "-u", type=str,
        help="数据库连接 URL（优先级最高）",
    )
    parser.add_argument(
        "--db-type", "-t", type=str,
        choices=["postgresql", "mysql", "sqlite"],
        default="postgresql",
        help="数据库类型",
    )
    parser.add_argument("--host", "-H", default="localhost", help="数据库主机")
    parser.add_argument("--port", "-p", type=int, default=5432, help="数据库端口")
    parser.add_argument("--database", "-d", required=True, help="数据库名")
    parser.add_argument("--username", "-U", default="postgres", help="用户名")
    parser.add_argument("--password", "-P", help="密码（建议使用环境变量）")
    parser.add_argument("--schema", "-s", default="public", help="Schema 名称（PostgreSQL 专用）")
    parser.add_argument("--output", "-o", default="schema.yaml", help="输出文件路径")
    parser.add_argument(
        "--include-samples", action="store_true",
        help="抽取样本数据用于枚举值推断",
    )
    parser.add_argument(
        "--sample-rows", type=int, default=100,
        help="样本数据行数（启用 --include-samples 时生效）",
    )
    parser.add_argument(
        "--exclude-tables", nargs="*", default=["spatial_ref_sys"],
        help="排除的表名（空格分隔）",
    )
    parser.add_argument(
        "--include-views", action="store_true",
        help="包含视图",
    )
    parser.add_argument(
        "--overwrite", "-f", action="store_true",
        help="覆盖已存在的输出文件",
    )
    return parser


def build_connection_url(args: argparse.Namespace) -> str:
    """构建数据库连接 URL"""
    if args.url:
        return args.url

    if args.db_type == "postgresql":
        return (
            f"postgresql://{args.username}:{args.password}"
            f"@{args.host}:{args.port}/{args.database}"
        )
    elif args.db_type == "mysql":
        return (
            f"mysql+pymysql://{args.username}:{args.password}"
            f"@{args.host}:{args.port}/{args.database}?charset=utf8mb4"
        )
    elif args.db_type == "sqlite":
        return f"sqlite:///{args.database}"
    else:
        raise ValueError(f"Unsupported database type: {args.db_type}")


async def extract_schema_async(args: argparse.Namespace) -> dict[str, Any]:
    """异步抽取 Schema"""
    try:
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
    except ImportError as e:
        print(f"错误: 缺少依赖 {e}", file=sys.stderr)
        print("请安装: pip install sqlalchemy asyncpg aiomysql aiosqlite", file=sys.stderr)
        sys.exit(1)

    url = build_connection_url(args)
    engine = create_async_engine(url, echo=False)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        tables = await _fetch_tables(session, args)
        schema: dict[str, Any] = {
            "schema_version": "1.0",
            "databases": [
                {
                    "id": "primary",
                    "display_name": args.database,
                    "db_category": "primary",
                    "description": f"从 {args.db_type} 抽取的数据库",
                    "tables": tables,
                }
            ],
            "relationships": [],
            "row_level_access": [
                {"role": "admin", "description": "管理员", "condition": "TRUE"},
                {"role": "user", "description": "普通用户", "condition": "TRUE"},
                {"role": "readonly", "description": "只读用户", "condition": "TRUE"},
            ],
            "business_keywords": {},
        }
        return schema


async def _fetch_tables(session: AsyncSession, args: argparse.Namespace) -> list[dict[str, Any]]:
    """获取所有表"""
    if args.db_type == "postgresql":
        sql = text("""
            SELECT table_name, table_type
            FROM information_schema.tables
            WHERE table_schema = :schema
            AND table_type IN ('BASE TABLE'::text, 'VIEW'::text)
            ORDER BY table_name
        """)
        params = {"schema": args.schema}
    elif args.db_type == "mysql":
        sql = text("""
            SELECT TABLE_NAME AS table_name, TABLE_TYPE AS table_type
            FROM information_schema.tables
            WHERE table_schema = :database
            AND TABLE_TYPE IN ('BASE TABLE', 'VIEW')
            ORDER BY TABLE_NAME
        """)
        params = {"database": args.database}
    else:  # sqlite
        sql = text("""
            SELECT name AS table_name, 'BASE TABLE' AS table_type
            FROM sqlite_master
            WHERE type = 'table' AND name NOT LIKE 'sqlite_%'
            UNION ALL
            SELECT name AS table_name, 'VIEW' AS table_type
            FROM sqlite_master
            WHERE type = 'view'
            ORDER BY name
        """)
        params = {}

    result = await session.execute(sql, params)
    rows = result.fetchall()

    tables = []
    for row in rows:
        table_name = row[0]
        table_type = row[1]

        if table_name in args.exclude_tables:
            continue
        if table_type == "VIEW" and not args.include_views:
            continue

        columns = await _fetch_columns(session, args, table_name)
        primary_key = next((c["name"] for c in columns if c.get("is_primary_key")), "")

        tables.append({
            "name": table_name,
            "logical_name": table_name,
            "description": "",
            "primary_key": primary_key,
            "columns": columns,
        })

    return tables


async def _fetch_columns(
    session: AsyncSession,
    args: argparse.Namespace,
    table_name: str,
) -> list[dict[str, Any]]:
    """获取表的列信息"""
    if args.db_type == "postgresql":
        sql = text("""
            SELECT
                c.column_name,
                c.data_type,
                c.is_nullable,
                c.column_default,
                c.character_maximum_length,
                c.numeric_precision,
                c.numeric_scale,
                CASE WHEN pk.column_name IS NOT NULL THEN true ELSE false END AS is_primary_key,
                col_description((
                    SELECT oid FROM pg_class WHERE relname = :table
                ), c.ordinal_position) AS column_comment
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT ku.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage ku
                    ON tc.constraint_name = ku.constraint_name
                WHERE tc.table_name = :table
                    AND tc.constraint_type = 'PRIMARY KEY'
                    AND tc.table_schema = :schema
            ) pk ON c.column_name = pk.column_name
            WHERE c.table_name = :table AND c.table_schema = :schema
            ORDER BY c.ordinal_position
        """)
        params = {"table": table_name, "schema": args.schema}
    elif args.db_type == "mysql":
        sql = text("""
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                c.IS_NULLABLE,
                c.COLUMN_DEFAULT,
                c.CHARACTER_MAXIMUM_LENGTH,
                c.NUMERIC_PRECISION,
                c.NUMERIC_SCALE,
                CASE WHEN c.COLUMN_KEY = 'PRI' THEN true ELSE false END AS is_primary_key,
                c.COLUMN_COMMENT
            FROM information_schema.columns c
            LEFT JOIN (
                SELECT COLUMN_NAME
                FROM information_schema.key_column_usage
                WHERE TABLE_NAME = :table
                    AND CONSTRAINT_NAME = 'PRIMARY'
                    AND TABLE_SCHEMA = :database
            ) pk ON c.COLUMN_NAME = pk.COLUMN_NAME
            WHERE c.TABLE_NAME = :table AND c.TABLE_SCHEMA = :database
            ORDER BY c.ORDINAL_POSITION
        """)
        params = {"table": table_name, "database": args.database}
    else:  # sqlite
        sql = text(f"PRAGMA table_info({table_name})")
        params = {}
        result = await session.execute(sql, params)
        rows = result.fetchall()
        return [
            {
                "name": str(row[1]),
                "type": _sqlite_type_to_yaml(row[2]),
                "is_nullable": not bool(row[3]),
                "is_primary_key": bool(row[5]),
                "description": "",
            }
            for row in rows
        ]

    result = await session.execute(sql, params)
    rows = result.fetchall()

    columns = []
    for row in rows:
        col_name = row[0]
        data_type = row[1]
        is_nullable = row[2] == "YES"
        is_pk = row[7]
        comment = row[8] or ""

        max_len = row[4]
        precision = row[5]
        scale = row[6]

        col_type = _format_type(data_type, max_len, precision, scale)

        columns.append({
            "name": col_name,
            "type": col_type,
            "is_nullable": is_nullable,
            "is_primary_key": is_pk,
            "description": str(comment) if comment else "",
        })

    return columns


def _format_type(
    base_type: str,
    max_len: Optional[int],
    precision: Optional[int],
    scale: Optional[int],
) -> str:
    """格式化列类型"""
    base_type = base_type.upper()
    if max_len and base_type in ("CHARACTER VARYING", "CHARACTER", "VARCHAR"):
        return f"VARCHAR({max_len})"
    if precision and scale is not None and base_type in ("NUMERIC", "DECIMAL"):
        return f"DECIMAL({precision},{scale})"
    if precision and base_type == "CHARACTER":
        return f"CHAR({precision})"
    return base_type


def _sqlite_type_to_yaml(type_code: int) -> str:
    """SQLite 类型码转 YAML 类型名"""
    type_map = {
        1: "INTEGER",
        2: "REAL",
        3: "TEXT",
        4: "BLOB",
        5: "NULL",
    }
    return type_map.get(type_code, "TEXT")


def infer_enum_values(rows: list[tuple]) -> dict[str, str]:
    """从样本数据推断枚举值（仅在 varchar 种类少时生效）"""
    if not rows:
        return {}

    unique_values: set[str] = set()
    for row in rows:
        for val in row:
            if val is not None and isinstance(val, str) and len(val) <= 50:
                unique_values.add(val)

    if 1 < len(unique_values) <= 20:
        return {v: v for v in sorted(unique_values)}
    return {}


async def run_async(args: argparse.Namespace) -> None:
    """运行异步抽取"""
    output_path = Path(args.output)
    if output_path.exists() and not args.overwrite:
        print(f"错误: 文件已存在 {args.output}，使用 --overwrite 覆盖", file=sys.stderr)
        sys.exit(1)

    print(f"正在连接到 {args.db_type}://{args.host}:{args.port}/{args.database} ...")
    schema = await extract_schema_async(args)

    table_count = sum(len(db.get("tables", [])) for db in schema["databases"])
    print(f"抽取完成: {len(schema['databases'])} 个数据库, {table_count} 张表")

    # 写入文件
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            schema,
            f,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
            indent=2,
        )
    print(f"Schema 已保存到: {args.output}")


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.password:
        import os
        args.password = os.getenv("DB_PASSWORD", "")

    import asyncio
    asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
