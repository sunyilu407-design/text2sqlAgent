"""结构化日志配置"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

from rich.logging import RichHandler
from rich.console import Console

# 全局 console 实例
console = Console()


def setup_logging(
    level: str = "INFO",
    log_file: Optional[Path] = None,
    json_format: bool = False,
) -> None:
    """
    配置结构化日志系统

    Args:
        level: 日志级别 (DEBUG, INFO, WARNING, ERROR)
        log_file: 可选的日志文件路径
        json_format: 是否使用 JSON 格式（生产环境推荐）
    """
    # 获取根 logger
    root_logger = logging.getLogger("micro_genbi")
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # 清除现有 handlers
    root_logger.handlers.clear()

    # 日志格式
    if json_format:
        # JSON 格式（用于日志收集系统如 ELK）
        formatter = logging.Formatter(
            '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    else:
        # Rich 格式（人类可读）
        formatter = logging.Formatter(
            "%(message)s",
            datefmt="[%X]"
        )

    # Console handler（Rich）
    console_handler = RichHandler(
        console=console,
        rich_tracebacks=True,
        tracebacks_show_locals=False,
        show_time=True,
        show_path=False,
    )
    console_handler.setFormatter(formatter)
    root_logger.addHandler(console_handler)

    # 文件 handler（可选）
    if log_file:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file, encoding="utf-8")
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # 减少第三方库日志噪音
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)


def get_logger(name: str) -> logging.Logger:
    """
    获取子模块 logger

    Args:
        name: 模块名，如 "micro_genbi.api"

    Returns:
        配置好的 logger 实例
    """
    return logging.getLogger(f"micro_genbi.{name}")


class LogContext:
    """日志上下文管理器，用于添加额外字段"""

    _context: dict = {}

    def __init__(self, **kwargs):
        self._extra = kwargs
        self._old_context = {}

    def __enter__(self):
        for key, value in self._extra.items():
            self._old_context[key] = LogContext._context.get(key)
            LogContext._context[key] = value
        return self

    def __exit__(self, *args):
        for key in self._extra:
            LogContext._context[key] = self._old_context.get(key)

    @classmethod
    def get_context(cls) -> dict:
        return cls._context.copy()


# 预定义的日志级别常量
class LogLevel:
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"
