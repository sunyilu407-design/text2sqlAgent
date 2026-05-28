#!/usr/bin/env python3
"""数据库初始化脚本

创建系统数据库表、默认租户和超级管理员。
支持 PostgreSQL、MySQL、SQLite。

用法:
    # 使用环境变量或命令行参数
    python scripts/init_db.py --db-url "sqlite+aiosqlite:///./microgenbi.db"

    # PostgreSQL
    python scripts/init_db.py --db-type postgresql --host localhost \
        --port 5432 --database microgenbi --username postgres --password secret

    # MySQL
    python scripts/init_db.py --db-type mysql --host localhost \
        --port 3306 --database microgenbi --username root --password secret

    # 创建默认管理员
    python scripts/init_db.py --create-admin --admin-username admin --admin-password admin123
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import yaml

# 添加 src 目录到路径
src_path = Path(__file__).parent.parent / "src"
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="初始化 Micro-GenBI 系统数据库",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--db-url",
        help="数据库连接 URL（如 sqlite+aiosqlite:///./microgenbi.db）",
    )
    parser.add_argument(
        "--db-type", "-t", type=str,
        choices=["postgresql", "mysql", "sqlite"],
        default="sqlite",
        help="数据库类型（默认 sqlite）",
    )
    parser.add_argument("--host", default="localhost", help="数据库主机")
    parser.add_argument("--port", type=int, default=5432, help="数据库端口")
    parser.add_argument("--database", "-d", default="./microgenbi.db", help="数据库名/文件路径")
    parser.add_argument("--username", "-U", help="用户名")
    parser.add_argument("--password", "-P", help="密码")
    parser.add_argument("--echo", action="store_true", help="打印 SQL 语句")
    parser.add_argument(
        "--create-admin", action="store_true",
        help="创建默认管理员账户",
    )
    parser.add_argument("--admin-username", default="admin", help="管理员用户名")
    parser.add_argument("--admin-password", default="admin123", help="管理员密码")
    parser.add_argument("--admin-email", default="admin@example.com", help="管理员邮箱")
    parser.add_argument(
        "--load-sample-schema", type=str,
        help="加载示例 schema.yaml 文件",
    )
    return parser


def build_db_url(args: argparse.Namespace) -> str:
    """构建数据库连接 URL"""
    if args.db_url:
        return args.db_url

    if args.db_type == "postgresql":
        return (
            f"postgresql+asyncpg://{args.username}:{args.password}"
            f"@{args.host}:{args.port}/{args.database}"
        )
    elif args.db_type == "mysql":
        return (
            f"mysql+aiomysql://{args.username}:{args.password}"
            f"@{args.host}:{args.port}/{args.database}?charset=utf8mb4"
        )
    else:
        path = args.database.lstrip("/")
        return f"sqlite+aiosqlite:///{path}"


async def init_database(db_url: str, echo: bool = False) -> None:
    """初始化数据库表结构"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from micro_genbi.database.models import Base
    except ImportError as e:
        print(f"错误: 缺少依赖 {e}", file=sys.stderr)
        print(
            "请安装: pip install sqlalchemy asyncpg aiomysql aiosqlite bcrypt",
            file=sys.stderr,
        )
        sys.exit(1)

    print(f"连接数据库: {db_url.split('@')[-1] if '@' in db_url else db_url}")

    engine = create_async_engine(db_url, echo=echo)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    print("数据库表结构创建完成")


async def create_default_tenant_and_admin(
    db_url: str,
    admin_username: str,
    admin_password: str,
    admin_email: str,
    echo: bool = False,
) -> None:
    """创建默认租户和超级管理员"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from micro_genbi.database.models import Base, Tenant, User, TenantMember
        import bcrypt
    except ImportError as e:
        print(f"错误: 缺少依赖 {e}", file=sys.stderr)
        sys.exit(1)

    engine = create_async_engine(db_url, echo=echo)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # 检查是否已有租户
        from sqlalchemy import select
        result = await session.execute(select(Tenant).limit(1))
        existing = result.scalar_one_or_none()

        if existing:
            print(f"系统已有租户 '{existing.name}'，跳过创建")
            return

        # 创建默认租户
        tenant = Tenant(
            id=str(uuid.uuid4()),
            name="default",
            description="默认租户",
            is_active=True,
        )
        session.add(tenant)

        # 创建管理员用户
        password_hash = bcrypt.hashpw(
            admin_password.encode(), bcrypt.gensalt()
        ).decode()

        admin = User(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            username=admin_username,
            email=admin_email,
            password_hash=password_hash,
            role="admin",
            is_active=True,
        )
        session.add(admin)

        # 添加为租户成员
        member = TenantMember(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            user_id=admin.id,
            role="admin",
        )
        session.add(member)

        await session.commit()

        print(f"默认租户已创建: {tenant.id}")
        print(f"管理员账户已创建:")
        print(f"  用户名: {admin_username}")
        print(f"  密码:   {admin_password}")
        print(f"  角色:   admin")


async def load_sample_schema(db_url: str, schema_path: str, echo: bool = False) -> None:
    """加载示例 schema.yaml 到系统数据库"""
    try:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from micro_genbi.database.models import SchemaConfig
        import yaml
    except ImportError as e:
        print(f"错误: 缺少依赖 {e}", file=sys.stderr)
        sys.exit(1)

    if not Path(schema_path).exists():
        print(f"警告: schema.yaml 不存在，跳过加载: {schema_path}", file=sys.stderr)
        return

    with open(schema_path, encoding="utf-8") as f:
        yaml_content = f.read()

    schema_data = yaml.safe_load(yaml_content)
    databases = schema_data.get("databases", [])
    if not databases:
        print("警告: schema.yaml 中没有数据库配置")
        return

    engine = create_async_engine(db_url, echo=echo)
    async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        from sqlalchemy import select
        from micro_genbi.database.models import Tenant

        result = await session.execute(select(Tenant).limit(1))
        tenant = result.scalar_one_or_none()

        if not tenant:
            print("错误: 需要先创建租户（运行不带 --load-sample-schema 的 init_db.py）")
            sys.exit(1)

        db = databases[0]
        db_id = db.get("id", "primary")

        schema_config = SchemaConfig(
            id=str(uuid.uuid4()),
            tenant_id=tenant.id,
            connection_id="",
            name=db.get("display_name", db_id),
            description=db.get("description", ""),
            yaml_content=yaml_content,
            version=1,
            is_active=True,
        )
        session.add(schema_config)
        await session.commit()

        print(f"Schema 配置已加载: {schema_config.name}")


async def run_async(args: argparse.Namespace) -> None:
    """异步运行"""
    db_url = build_db_url(args)

    # 1. 创建表结构
    await init_database(db_url, echo=args.echo)

    # 2. 创建管理员
    if args.create_admin:
        await create_default_tenant_and_admin(
            db_url,
            args.admin_username,
            args.admin_password,
            args.admin_email,
            echo=args.echo,
        )

    # 3. 加载示例 schema
    if args.load_sample_schema:
        await load_sample_schema(db_url, args.load_sample_schema, echo=args.echo)

    print("\n初始化完成!")


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()

    if not args.password:
        args.password = os.getenv("DB_PASSWORD", "")

    print("=" * 60)
    print("Micro-GenBI 数据库初始化脚本")
    print("=" * 60)

    asyncio.run(run_async(args))


if __name__ == "__main__":
    main()
