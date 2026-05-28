"""数据库健康检查模块

提供数据库连接健康检查、连接池监控和自动恢复能力。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional, Any


class HealthStatus(Enum):
    """健康状态枚举"""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    UNHEALTHY = "unhealthy"
    UNKNOWN = "unknown"


@dataclass
class HealthCheckResult:
    """健康检查结果"""
    database: str
    status: HealthStatus
    latency_ms: float
    connection_working: bool
    error: Optional[str] = None
    checked_at: str = field(default_factory=lambda: datetime.now().isoformat())


class DatabaseHealthChecker:
    """
    数据库健康检查器

    功能：
    - 检测数据库连接是否可用
    - 测量查询延迟
    - 监控连接池状态
    - 支持配置化的超时和延迟阈值
    """

    def __init__(
        self,
        database_name: str,
        get_session,
        max_latency_ms: float = 5000.0,
        timeout_seconds: float = 10.0,
    ):
        """
        Args:
            database_name: 数据库名称/标识
            get_session: 获取数据库会话的可调用对象（同步或异步）
            max_latency_ms: 最大可接受延迟（毫秒），超出标记为 DEGRADED
            timeout_seconds: 健康检查超时时间
        """
        self.database_name = database_name
        self.get_session = get_session
        self.max_latency_ms = max_latency_ms
        self.timeout_seconds = timeout_seconds
        self._last_result: Optional[HealthCheckResult] = None
        self._consecutive_failures = 0

    async def check_async(self) -> HealthCheckResult:
        """异步执行健康检查"""
        return await self._run_check()

    def check_sync(self) -> HealthCheckResult:
        """同步执行健康检查"""
        loop = asyncio.new_event_loop()
        return loop.run_until_complete(self._run_check())

    async def _run_check(self) -> HealthCheckResult:
        """执行健康检查的内部逻辑"""
        start = time.perf_counter()

        try:
            session = await asyncio.wait_for(
                self._get_session_async(),
                timeout=self.timeout_seconds
            )

            query_start = time.perf_counter()
            result = await self._execute_ping(session)
            query_time_ms = (time.perf_counter() - query_start) * 1000

            latency_ms = (time.perf_counter() - start) * 1000
            self._consecutive_failures = 0

            if latency_ms > self.max_latency_ms:
                status = HealthStatus.DEGRADED
            else:
                status = HealthStatus.HEALTHY

            self._last_result = HealthCheckResult(
                database=self.database_name,
                status=status,
                latency_ms=latency_ms,
                connection_working=True,
                error=None,
            )
            return self._last_result

        except asyncio.TimeoutError:
            return self._fail_result("健康检查超时", start)

        except Exception as e:
            return self._fail_result(str(e), start)

    async def _get_session_async(self):
        """获取会话（支持异步）"""
        session = self.get_session()
        if asyncio.iscoroutine(session):
            return await session
        return session

    async def _execute_ping(self, session) -> Any:
        """执行 ping 查询"""
        if hasattr(session, "execute"):
            if asyncio.iscoroutine(session):
                return await session.execute("SELECT 1")
            else:
                return session.execute("SELECT 1")
        elif hasattr(session, "run"):
            return await session.run("SELECT 1", None)
        raise NotImplementedError(f"Unsupported session type: {type(session)}")

    def _fail_result(self, error: str, start: float) -> HealthCheckResult:
        """创建失败结果"""
        self._consecutive_failures += 1
        result = HealthCheckResult(
            database=self.database_name,
            status=HealthStatus.UNHEALTHY,
            latency_ms=(time.perf_counter() - start) * 1000,
            connection_working=False,
            error=error,
        )
        self._last_result = result
        return result

    def get_last_result(self) -> Optional[HealthCheckResult]:
        """获取最近一次检查结果"""
        return self._last_result

    def is_healthy(self) -> bool:
        """检查数据库是否健康"""
        if self._last_result is None:
            return False
        return self._last_result.status in (HealthStatus.HEALTHY, HealthStatus.DEGRADED)

    def needs_recovery(self) -> bool:
        """检查是否需要恢复操作（连续失败 >= 3 次）"""
        return self._consecutive_failures >= 3


class MultiDatabaseHealthMonitor:
    """
    多数据库健康监控器

    统一监控多个数据库实例的健康状态。
    """

    def __init__(self, check_interval_seconds: int = 30):
        self.check_interval = check_interval_seconds
        self._checkers: dict[str, DatabaseHealthChecker] = {}
        self._monitoring_task: Optional[asyncio.Task] = None
        self._running = False

    def register(self, name: str, checker: DatabaseHealthChecker) -> None:
        """注册数据库健康检查器"""
        self._checkers[name] = checker

    def unregister(self, name: str) -> None:
        """取消注册"""
        self._checkers.pop(name, None)

    async def check_all(self) -> dict[str, HealthCheckResult]:
        """并行检查所有数据库"""
        tasks = {
            name: checker.check_async()
            for name, checker in self._checkers.items()
        }
        results = {}
        for name, task in tasks.items():
            try:
                results[name] = await task
            except Exception as e:
                results[name] = HealthCheckResult(
                    database=name,
                    status=HealthStatus.UNHEALTHY,
                    latency_ms=0,
                    connection_working=False,
                    error=str(e),
                )
        return results

    async def start_monitoring(self) -> None:
        """启动持续监控循环"""
        self._running = True
        while self._running:
            await self.check_all()
            await asyncio.sleep(self.check_interval)

    def stop(self) -> None:
        """停止监控"""
        self._running = False
        if self._monitoring_task:
            self._monitoring_task.cancel()

    def get_summary(self) -> dict[str, Any]:
        """获取监控摘要"""
        healthy = degraded = unhealthy = 0
        details = {}

        for name, checker in self._checkers.items():
            result = checker.get_last_result()
            if result:
                details[name] = {
                    "status": result.status.value,
                    "latency_ms": round(result.latency_ms, 2),
                    "error": result.error,
                }
                if result.status == HealthStatus.HEALTHY:
                    healthy += 1
                elif result.status == HealthStatus.DEGRADED:
                    degraded += 1
                else:
                    unhealthy += 1

        return {
            "total": len(self._checkers),
            "healthy": healthy,
            "degraded": degraded,
            "unhealthy": unhealthy,
            "databases": details,
        }


# 全局健康监控器
_health_monitor: Optional[MultiDatabaseHealthMonitor] = None


def get_health_monitor() -> MultiDatabaseHealthMonitor:
    """获取全局健康监控器"""
    global _health_monitor
    if _health_monitor is None:
        _health_monitor = MultiDatabaseHealthMonitor()
    return _health_monitor
