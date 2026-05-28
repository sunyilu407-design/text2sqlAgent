"""Micro-GenBI CLI 工具

用法：
    genbi ask "统计本月销售额"
    genbi schema --list
    genbi schema --table orders
    genbi config --validate
    genbi serve --port 8000
    genbi metrics
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.syntax import Syntax
from rich.markdown import Markdown

# 添加 src 目录到路径
src_path = Path(__file__).parent.parent.parent
if str(src_path) not in sys.path:
    sys.path.insert(0, str(src_path))

app = typer.Typer(
    name="genbi",
    help="Micro-GenBI CLI - 微分智能数据引擎",
    add_completion=False,
)
console = Console()


@app.command()
def ask(
    query: str = typer.Argument(..., help="自然语言查询"),
    schema_path: str = typer.Option(
        "schema.yaml", "--schema", "-s",
        help="Schema 文件路径"
    ),
    config_path: Optional[str] = typer.Option(
        None, "--config", "-c",
        help="配置文件路径"
    ),
    format: str = typer.Option(
        "auto", "--format", "-f",
        help="输出格式: auto, json, pretty"
    ),
) -> None:
    """
    执行自然语言数据分析查询
    """
    async def _run():
        try:
            # 延迟导入，避免启动慢
            from micro_genbi.service.ask_service import AskService

            service = AskService(schema_path=schema_path)

            console.print(f"[dim]正在分析: {query}[/dim]")

            result = await service.ask(query)

            # 输出结果
            if format == "json":
                console.print_json(json.dumps(result, ensure_ascii=False, default=str))
            elif format == "pretty" or format == "auto":
                _print_result_pretty(result)
            else:
                console.print(result)

        except Exception as e:
            console.print(f"[red]错误: {e}[/red]")
            raise typer.Exit(1)
        finally:
            try:
                await service.close()
            except Exception:
                pass

    asyncio.run(_run())


@app.command()
def schema(
    list_tables: bool = typer.Option(
        False, "--list", "-l",
        help="列出所有表"
    ),
    table: Optional[str] = typer.Option(
        None, "--table", "-t",
        help="查看指定表的详细信息"
    ),
    schema_path: str = typer.Option(
        "schema.yaml", "--schema", "-s",
        help="Schema 文件路径"
    ),
) -> None:
    """
    查看数据库 schema 信息
    """
    try:
        from micro_genbi.semantic.schema_registry import SchemaRegistry

        registry = SchemaRegistry(schema_path=schema_path)
        registry.load()

        if list_tables:
            all_tables = []
            for db in registry.get_all_databases():
                all_tables.extend(db.tables)

            table_info = Table(title="数据库表")
            table_info.add_column("表名", style="cyan")
            table_info.add_column("描述", style="dim")

            for t in all_tables:
                desc = getattr(t, "description", "") or ""
                table_info.add_row(t.name, desc[:50])

            console.print(table_info)
            console.print(f"\n共 {len(all_tables)} 张表")

        elif table:
            found = None
            for db in registry.get_all_databases():
                for t in db.tables:
                    if t.name == table or getattr(t, "logical_name", "") == table:
                        found = t
                        break
                if found:
                    break

            if found:
                info_parts = [f"[bold]{found.name}[/bold]"]
                if hasattr(found, "logical_name"):
                    info_parts.append(f"显示名: {found.logical_name}")
                if found.description:
                    info_parts.append(f"描述: {found.description}")
                info_parts.append(f"列数: {len(found.columns)}")

                for col in found.columns:
                    col_info = f"  - {col.name}({col.col_type})"
                    if col.description:
                        col_info += f": {col.description}"
                    info_parts.append(col_info)

                console.print(Panel(
                    "\n".join(info_parts),
                    title=f"表: {found.name}",
                    expand=False
                ))
            else:
                console.print(f"[yellow]未找到表: {table}[/yellow]")

        else:
            console.print("[yellow]请使用 --list 或 --table[/yellow]")
            raise typer.Exit(1)

    except Exception as e:
        console.print(f"[red]错误: {e}[/red]")
        raise typer.Exit(1)


@app.command()
def config(
    validate: bool = typer.Option(
        False, "--validate", "-v",
        help="验证配置文件"
    ),
    config_path: str = typer.Option(
        "genbi_config.yaml", "--config", "-c",
        help="配置文件路径"
    ),
) -> None:
    """
    配置管理命令
    """
    if validate:
        try:
            from micro_genbi.config import ConfigLoader

            cfg = ConfigLoader.load(config_path)
            console.print("[green]配置文件验证通过[/green]")
            console.print_json(json.dumps(cfg.model_dump(), indent=2, ensure_ascii=False))
        except Exception as e:
            console.print(f"[red]配置文件验证失败: {e}[/red]")
            raise typer.Exit(1)


@app.command()
def serve(
    host: str = typer.Option(
        "0.0.0.0", "--host",
        help="监听地址"
    ),
    port: int = typer.Option(
        8000, "--port", "-p",
        help="监听端口"
    ),
    workers: int = typer.Option(
        1, "--workers", "-w",
        help="Worker 数量"
    ),
    reload: bool = typer.Option(
        False, "--reload", "-r",
        help="开发模式（自动重载）"
    ),
    log_level: str = typer.Option(
        "info", "--log-level",
        help="日志级别"
    ),
) -> None:
    """
    启动 FastAPI 服务
    """
    import uvicorn
    from micro_genbi.monitoring import setup_logging

    setup_logging(level=log_level.upper())

    console.print(Panel(
        f"[bold green]Micro-GenBI 服务启动中[/bold green]\n\n"
        f"地址: http://{host}:{port}\n"
        f"文档: http://{host}:{port}/docs\n"
        f"Workers: {workers}",
        title="启动信息"
    ))

    uvicorn.run(
        "micro_genbi.api.main:app",
        host=host,
        port=port,
        workers=workers,
        reload=reload,
        log_level=log_level.lower(),
    )


@app.command()
def metrics(
    reset: bool = typer.Option(
        False, "--reset",
        help="重置指标"
    ),
) -> None:
    """
    查看系统指标
    """
    from micro_genbi.monitoring import get_metrics

    metrics_collector = get_metrics()

    if reset:
        metrics_collector.reset()
        console.print("[green]指标已重置[/green]")
        return

    summary = metrics_collector.summary()
    console.print(Panel(
        f"[white]{summary}[/white]",
        title="系统指标",
        expand=False
    ))


@app.command()
def init(
    project_path: str = typer.Argument(
        ".", help="项目路径"
    ),
    force: bool = typer.Option(
        False, "--force", "-f",
        help="覆盖已存在的文件"
    ),
) -> None:
    """
    初始化 Micro-GenBI 项目
    """
    path = Path(project_path)
    created_files = []

    # 需要创建的文件
    files = {
        "schema.yaml": """# Schema 配置示例
schema_version: "1.0"

table_aliases:
  orders: "订单表"

semantic_descriptions:
  orders:
    name: "订单表"
    description: "包含所有销售订单"
    columns:
      order_id: "订单ID"
      amount: "订单金额"

row_level_access:
  - role: "admin"
    condition: "TRUE"
  - role: "user"
    condition: "TRUE"
""",
        ".env": "# 复制 .env.example 并配置",
    }

    for filename, content in files.items():
        file_path = path / filename
        if file_path.exists() and not force:
            console.print(f"[yellow]跳过 {filename} (已存在)[/yellow]")
            continue
        file_path.write_text(content, encoding="utf-8")
        created_files.append(filename)

    if created_files:
        console.print(f"[green]已创建: {', '.join(created_files)}[/green]")
    console.print("\n下一步:")
    console.print("  1. 配置数据库连接 (.env)")
    console.print("  2. 编辑 schema.yaml 添加表结构")
    console.print("  3. 运行: genbi serve")


def _print_result_pretty(result: dict) -> None:
    """美化输出查询结果"""
    # 处理 Pydantic 模型
    if hasattr(result, "model_dump"):
        result = result.model_dump()

    if "error" in result and result["error"]:
        console.print(Panel(
            f"[red]{result['error']}[/red]",
            title="错误"
        ))
        return

    if "sql" in result:
        sql = result["sql"]
        syntax = Syntax(sql, "sql", theme="monokai", line_numbers=False)
        console.print(Panel(
            syntax,
            title="生成的 SQL"
        ))

    if "data" in result and result["data"]:
        data = result["data"]
        console.print(f"\n[dim]返回 {len(data)} 行数据[/dim]")

        # 显示前 10 行
        table = Table(title="查询结果")
        columns = list(data[0].keys())
        for col in columns:
            table.add_column(str(col), style="cyan")

        for row in data[:10]:
            table.add_row(*[str(row.get(c, "")) for c in columns])

        console.print(table)

        if len(data) > 10:
            console.print(f"[dim]... 还有 {len(data) - 10} 行[/dim]")

    if "chart" in result and result["chart"]:
        console.print("\n[green]图表已生成[/green]")

    if "summary" in result and result["summary"]:
        console.print(Panel(
            result["summary"],
            title="结果摘要"
        ))


def main():
    """入口点"""
    app()


if __name__ == "__main__":
    main()
