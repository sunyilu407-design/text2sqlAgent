"""订阅调度服务

基于 Cron 的定时查询订阅服务，支持：
- 定时执行 SQL 查询
- 邮件/Webhook 通知
- 暂停/恢复订阅
- 订阅生命周期管理
"""

from __future__ import annotations

import json
import logging
import smtplib
import socket
import ssl
import tempfile
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

try:
    from croniter import croniter
except ImportError:
    croniter = None

try:
    import requests
except ImportError:
    requests = None

from micro_genbi.monitoring import get_logger
from micro_genbi.service.data_exporter import DataExporter, ExportRequest

logger = get_logger(__name__)


@dataclass
class Subscription:
    """订阅数据模型"""
    id: int
    user_id: str
    name: str
    query: str
    schedule: str  # Cron expression: "0 9 * * *" (daily at 9am)
    recipients: list[str]  # email addresses or webhook URLs
    format: str  # csv, excel, json
    is_active: bool
    last_run: Optional[datetime]
    next_run: Optional[datetime]
    created_at: datetime
    last_error: str = ""
    execution_count: int = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "name": self.name,
            "query": self.query,
            "schedule": self.schedule,
            "recipients": self.recipients,
            "format": self.format,
            "is_active": self.is_active,
            "last_run": self.last_run.isoformat() if self.last_run else None,
            "next_run": self.next_run.isoformat() if self.next_run else None,
            "created_at": self.created_at.isoformat(),
            "last_error": self.last_error,
            "execution_count": self.execution_count,
        }


@dataclass
class ExecutionResult:
    """执行结果"""
    subscription_id: int
    success: bool
    executed_at: datetime
    row_count: int = 0
    error_message: str = ""
    notification_sent: bool = False


class SubscriptionService:
    """
    订阅调度服务

    管理定时查询订阅的生命周期，包括：
    - 创建/暂停/恢复/删除订阅
    - 按 Cron 表达式调度执行
    - 执行结果通知（邮件/Webhook）
    """

    SUPPORTED_FORMATS = {"csv", "excel", "json"}
    SCHEDULER_INTERVAL = 60  # 调度器检查间隔（秒）

    def __init__(
        self,
        smtp_host: Optional[str] = None,
        smtp_port: int = 587,
        smtp_user: Optional[str] = None,
        smtp_password: Optional[str] = None,
        smtp_from: Optional[str] = None,
        use_tls: bool = True,
    ):
        """
        初始化订阅服务

        Args:
            smtp_host: SMTP 服务器地址
            smtp_port: SMTP 端口
            smtp_user: SMTP 用户名
            smtp_password: SMTP 密码
            smtp_from: 发件人地址
            use_tls: 是否使用 TLS
        """
        self._smtp_config = {
            "host": smtp_host,
            "port": smtp_port,
            "user": smtp_user,
            "password": smtp_password,
            "from": smtp_from or smtp_user,
            "use_tls": use_tls,
        }

        self._subscriptions: dict[int, Subscription] = {}
        self._lock = threading.RLock()
        self._next_id = 1

        self._scheduler_thread: Optional[threading.Thread] = None
        self._scheduler_running = threading.Event()
        self._scheduler_started = False

        self._executor: Optional[SubscriptionExecutor] = None

    def set_executor(self, executor: SubscriptionExecutor) -> None:
        """
        设置查询执行器

        Args:
            executor: SubscriptionExecutor 实例
        """
        self._executor = executor

    def create_subscription(
        self,
        name: str,
        query: str,
        schedule: str,
        recipients: list[str],
        format: str,
        user_id: str,
    ) -> int:
        """
        创建订阅

        Args:
            name: 订阅名称
            query: SQL 查询语句
            schedule: Cron 表达式
            recipients: 通知接收者列表（邮件或 Webhook URL）
            format: 数据格式（csv/excel/json）
            user_id: 用户 ID

        Returns:
            订阅 ID

        Raises:
            ValueError: 参数验证失败
        """
        if not name or not name.strip():
            raise ValueError("订阅名称不能为空")
        if not query or not query.strip():
            raise ValueError("查询语句不能为空")
        if not recipients:
            raise ValueError("至少需要一个接收者")
        if format not in self.SUPPORTED_FORMATS:
            raise ValueError(f"不支持的格式: {format}，支持: {self.SUPPORTED_FORMATS}")
        if not self._validate_cron(schedule):
            raise ValueError(f"无效的 Cron 表达式: {schedule}")

        next_run = self._get_next_run(schedule)

        with self._lock:
            sub_id = self._next_id
            self._next_id += 1

            subscription = Subscription(
                id=sub_id,
                user_id=user_id,
                name=name,
                query=query,
                schedule=schedule,
                recipients=recipients,
                format=format,
                is_active=True,
                last_run=None,
                next_run=next_run,
                created_at=datetime.now(),
            )
            self._subscriptions[sub_id] = subscription
            logger.info(f"创建订阅: id={sub_id}, name={name}, schedule={schedule}")

        return sub_id

    def pause_subscription(self, subscription_id: int) -> bool:
        """
        暂停订阅

        Args:
            subscription_id: 订阅 ID

        Returns:
            是否成功
        """
        with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            subscription = self._subscriptions[subscription_id]
            subscription.is_active = False
            subscription.next_run = None
            logger.info(f"暂停订阅: id={subscription_id}, name={subscription.name}")
            return True

    def resume_subscription(self, subscription_id: int) -> bool:
        """
        恢复订阅

        Args:
            subscription_id: 订阅 ID

        Returns:
            是否成功
        """
        with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            subscription = self._subscriptions[subscription_id]
            if subscription.is_active:
                logger.warning(f"订阅已是激活状态: {subscription_id}")
                return True

            subscription.is_active = True
            subscription.next_run = self._get_next_run(subscription.schedule)
            logger.info(f"恢复订阅: id={subscription_id}, next_run={subscription.next_run}")
            return True

    def delete_subscription(self, subscription_id: int) -> bool:
        """
        删除订阅

        Args:
            subscription_id: 订阅 ID

        Returns:
            是否成功
        """
        with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            subscription = self._subscriptions.pop(subscription_id)
            logger.info(f"删除订阅: id={subscription_id}, name={subscription.name}")
            return True

    def list_subscriptions(self, user_id: Optional[str] = None) -> list[Subscription]:
        """
        列出订阅

        Args:
            user_id: 用户 ID，为 None 时返回所有订阅

        Returns:
            订阅列表
        """
        with self._lock:
            if user_id is None:
                return list(self._subscriptions.values())
            return [s for s in self._subscriptions.values() if s.user_id == user_id]

    def get_subscription(self, subscription_id: int) -> Optional[Subscription]:
        """
        获取订阅详情

        Args:
            subscription_id: 订阅 ID

        Returns:
            订阅对象，不存在返回 None
        """
        with self._lock:
            return self._subscriptions.get(subscription_id)

    def update_subscription(
        self,
        subscription_id: int,
        name: Optional[str] = None,
        query: Optional[str] = None,
        schedule: Optional[str] = None,
        recipients: Optional[list[str]] = None,
        format: Optional[str] = None,
    ) -> bool:
        """
        更新订阅配置

        Args:
            subscription_id: 订阅 ID
            name: 新名称
            query: 新查询
            schedule: 新 Cron 表达式
            recipients: 新接收者列表
            format: 新格式

        Returns:
            是否成功
        """
        with self._lock:
            if subscription_id not in self._subscriptions:
                logger.warning(f"订阅不存在: {subscription_id}")
                return False

            subscription = self._subscriptions[subscription_id]

            if name is not None:
                if not name.strip():
                    raise ValueError("订阅名称不能为空")
                subscription.name = name

            if query is not None:
                if not query.strip():
                    raise ValueError("查询语句不能为空")
                subscription.query = query

            if schedule is not None:
                if not self._validate_cron(schedule):
                    raise ValueError(f"无效的 Cron 表达式: {schedule}")
                subscription.schedule = schedule

            if recipients is not None:
                if not recipients:
                    raise ValueError("至少需要一个接收者")
                subscription.recipients = recipients

            if format is not None:
                if format not in self.SUPPORTED_FORMATS:
                    raise ValueError(f"不支持的格式: {format}")
                subscription.format = format

            if subscription.is_active:
                subscription.next_run = self._get_next_run(subscription.schedule)

            logger.info(f"更新订阅: id={subscription_id}")
            return True

    def _validate_cron(self, schedule: str) -> bool:
        """
        验证 Cron 表达式

        Args:
            schedule: Cron 表达式

        Returns:
            是否有效
        """
        if croniter is None:
            logger.warning("croniter 未安装，使用简化验证")
            return self._simple_cron_validate(schedule)
        try:
            croniter(schedule)
            return True
        except (KeyError, ValueError):
            return False

    def _simple_cron_validate(self, schedule: str) -> bool:
        """
        简化 Cron 验证（无 croniter 时使用）

        Args:
            schedule: Cron 表达式

        Returns:
            是否有效
        """
        parts = schedule.split()
        if len(parts) not in (5, 6):
            return False
        for part in parts:
            if part == "*":
                continue
            if "/" in part:
                part = part.split("/")[0]
            if "-" in part:
                continue
            if "," in part:
                continue
            if not part.isdigit():
                return False
        return True

    def _parse_cron(self, schedule: str) -> Optional[croniter]:
        """
        解析 Cron 表达式

        Args:
            schedule: Cron 表达式

        Returns:
            croniter 实例，解析失败返回 None
        """
        if croniter is None:
            return None
        try:
            return croniter(schedule)
        except (KeyError, ValueError):
            return None

    def _get_next_run(self, schedule: str) -> datetime:
        """
        获取下次执行时间

        Args:
            schedule: Cron 表达式

        Returns:
            下次执行时间
        """
        now = datetime.now()
        if croniter:
            try:
                cron = croniter(schedule, now)
                timestamp = cron.get_next(datetime)
                return timestamp
            except (KeyError, ValueError):
                pass

        parts = schedule.split()
        if len(parts) >= 5:
            minute, hour = parts[0], parts[1]
            next_run = now.replace(hour=int(hour) if hour.isdigit() else 0,
                                   minute=int(minute) if minute.isdigit() else 0,
                                   second=0, microsecond=0)
            if next_run <= now:
                next_run = next_run.replace(hour=(next_run.hour + 1) % 24)
            return next_run

        return now.replace(second=0, microsecond=0)

    def _start_scheduler(self) -> None:
        """
        启动调度器（内部方法）

        调度器以守护线程运行，定期检查需要执行的订阅
        """
        if self._scheduler_started:
            logger.warning("调度器已启动")
            return

        self._scheduler_running.set()
        self._scheduler_thread = threading.Thread(
            target=self._scheduler_loop,
            name="SubscriptionScheduler",
            daemon=True,
        )
        self._scheduler_thread.start()
        self._scheduler_started = True
        logger.info("订阅调度器已启动")

    def _stop_scheduler(self) -> None:
        """
        停止调度器（内部方法）
        """
        if not self._scheduler_started:
            return

        self._scheduler_running.clear()
        if self._scheduler_thread and self._scheduler_thread.is_alive():
            self._scheduler_thread.join(timeout=5)
        self._scheduler_started = False
        logger.info("订阅调度器已停止")

    def _scheduler_loop(self) -> None:
        """
        调度器主循环
        """
        logger.info("调度器线程启动")
        while self._scheduler_running.is_set():
            try:
                self._check_and_execute()
            except Exception as e:
                logger.error(f"调度器执行出错: {e}")

            self._scheduler_running.wait(self.SCHEDULER_INTERVAL)

    def _check_and_execute(self) -> None:
        """
        检查并执行到期的订阅
        """
        now = datetime.now()

        with self._lock:
            due_subscriptions = [
                s for s in self._subscriptions.values()
                if s.is_active and s.next_run and s.next_run <= now
            ]

        for subscription in due_subscriptions:
            try:
                logger.info(f"执行订阅: id={subscription.id}, name={subscription.name}")
                result = self._execute_subscription(subscription.id)

                if result.success:
                    logger.info(
                        f"订阅执行成功: id={subscription.id}, "
                        f"rows={result.row_count}, notifications={result.notification_sent}"
                    )
                else:
                    logger.warning(
                        f"订阅执行失败: id={subscription.id}, error={result.error_message}"
                    )

                with self._lock:
                    sub = self._subscriptions.get(subscription.id)
                    if sub:
                        sub.last_run = now
                        sub.next_run = self._get_next_run(sub.schedule)
                        sub.execution_count += 1
                        if not result.success:
                            sub.last_error = result.error_message

            except Exception as e:
                logger.error(f"执行订阅时异常: id={subscription.id}, error={e}")
                with self._lock:
                    sub = self._subscriptions.get(subscription.id)
                    if sub:
                        sub.last_error = str(e)

    def _execute_subscription(self, subscription_id: int) -> ExecutionResult:
        """
        执行单个订阅

        Args:
            subscription_id: 订阅 ID

        Returns:
            执行结果
        """
        result = ExecutionResult(
            subscription_id=subscription_id,
            success=False,
            executed_at=datetime.now(),
        )

        with self._lock:
            subscription = self._subscriptions.get(subscription_id)
            if not subscription:
                result.error_message = f"订阅不存在: {subscription_id}"
                return result

        try:
            if self._executor is None:
                data = [{"id": 1, "message": "未配置执行器，返回模拟数据"}]
                columns = ["id", "message"]
                result.row_count = 1
            else:
                data, columns = self._executor.execute(subscription.query)
                result.row_count = len(data)

            content = self._prepare_content(data, columns, subscription.format)
            notification_sent = self._notify(subscription.recipients, content, subscription.format, subscription.name)
            result.notification_sent = notification_sent
            result.success = True

        except Exception as e:
            result.error_message = str(e)
            logger.error(f"执行订阅失败: {subscription_id}, {e}")

        return result

    def _prepare_content(
        self,
        data: list[dict],
        columns: list[str],
        format: str,
    ) -> bytes:
        """
        准备通知内容

        Args:
            data: 查询数据
            columns: 列名列表
            format: 数据格式

        Returns:
            格式化后的内容
        """
        if format == "json":
            return json.dumps(data, ensure_ascii=False, indent=2).encode("utf-8")

        if format in ("csv", "excel"):
            exporter = DataExporter()
            with tempfile.NamedTemporaryFile(
                suffix=f".{format}",
                delete=False,
            ) as f:
                temp_path = f.name

            export_result = exporter.export(ExportRequest(
                data=data,
                columns=columns,
                format=format,
            ))

            with open(export_result.file_path, "rb") as f:
                content = f.read()

            Path(export_result.file_path).unlink(missing_ok=True)
            return content

        return json.dumps(data, ensure_ascii=False).encode("utf-8")

    def _notify(
        self,
        recipients: list[str],
        content: bytes,
        format: str,
        subscription_name: str,
    ) -> bool:
        """
        发送通知

        Args:
            recipients: 接收者列表
            content: 通知内容
            format: 数据格式
            subscription_name: 订阅名称

        Returns:
            是否全部发送成功
        """
        all_sent = True
        for recipient in recipients:
            try:
                if self._is_email(recipient):
                    sent = self._send_email(recipient, content, format, subscription_name)
                else:
                    sent = self._send_webhook(recipient, content, format, subscription_name)
                if not sent:
                    all_sent = False
            except Exception as e:
                logger.error(f"通知发送失败: {recipient}, {e}")
                all_sent = False

        return all_sent

    def _is_email(self, recipient: str) -> bool:
        """
        判断是否为邮件地址

        Args:
            recipient: 接收者标识

        Returns:
            是否为邮件
        """
        return "@" in recipient and not recipient.startswith("http")

    def _send_email(
        self,
        to_email: str,
        content: bytes,
        format: str,
        subscription_name: str,
    ) -> bool:
        """
        发送邮件

        Args:
            to_email: 收件人邮箱
            content: 邮件内容
            format: 数据格式
            subscription_name: 订阅名称

        Returns:
            是否发送成功
        """
        smtp_config = self._smtp_config
        if not smtp_config.get("host"):
            logger.warning("SMTP 未配置，跳过邮件发送")
            return False

        try:
            msg = MIMEMultipart()
            msg["From"] = smtp_config["from"]
            msg["To"] = to_email
            msg["Subject"] = f"[Micro-GenBI] 订阅报告: {subscription_name}"

            body = f"""您好，

您的订阅 "{subscription_name}" 已执行完成。

附件为查询结果（格式：{format}）。

---
Micro-GenBI 自动发送
"""
            msg.attach(MIMEText(body, "plain", "utf-8"))

            ext = "csv" if format == "csv" else ("xlsx" if format == "excel" else "json")
            filename = f"{subscription_name}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{ext}"
            msg.attach(
                MIMEText(content.decode("utf-8", errors="replace"), "plain", "utf-8")
                if format == "json" else MIMEText(content.decode("latin-1", errors="replace"), "octet-stream")
            )

            context = None
            if smtp_config.get("use_tls"):
                context = ssl.create_default_context()

            with smtplib.SMTP(smtp_config["host"], smtp_config["port"]) as server:
                if smtp_config.get("use_tls"):
                    server.starttls(context=context)
                if smtp_config.get("user") and smtp_config.get("password"):
                    server.login(smtp_config["user"], smtp_config["password"])
                server.send_message(msg)

            logger.info(f"邮件发送成功: {to_email}")
            return True

        except Exception as e:
            logger.error(f"邮件发送失败: {to_email}, {e}")
            return False

    def _send_webhook(
        self,
        webhook_url: str,
        content: bytes,
        format: str,
        subscription_name: str,
    ) -> bool:
        """
        发送 Webhook

        Args:
            webhook_url: Webhook URL
            content: 内容
            format: 数据格式
            subscription_name: 订阅名称

        Returns:
            是否发送成功
        """
        if requests is None:
            logger.warning("requests 库未安装，跳过 Webhook 发送")
            return False

        try:
            headers = {
                "Content-Type": "application/json",
                "User-Agent": "Micro-GenBI-Subscription/1.0",
            }

            payload = {
                "subscription_name": subscription_name,
                "format": format,
                "timestamp": datetime.now().isoformat(),
                "data": json.loads(content.decode("utf-8")) if format == "json" else content.decode("utf-8"),
            }

            response = requests.post(
                webhook_url,
                json=payload,
                headers=headers,
                timeout=30,
            )
            response.raise_for_status()

            logger.info(f"Webhook 发送成功: {webhook_url}")
            return True

        except requests.RequestException as e:
            logger.error(f"Webhook 发送失败: {webhook_url}, {e}")
            return False
        except Exception as e:
            logger.error(f"Webhook 处理异常: {webhook_url}, {e}")
            return False

    def start(self) -> None:
        """启动订阅调度服务"""
        self._start_scheduler()

    def stop(self) -> None:
        """停止订阅调度服务"""
        self._stop_scheduler()

    def __enter__(self) -> "SubscriptionService":
        """上下文管理器入口"""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.stop()


class SubscriptionExecutor:
    """
    订阅查询执行器

    负责执行订阅的 SQL 查询并返回结果。
    需要与数据库执行器集成。
    """

    def __init__(
        self,
        ask_service=None,
        executor=None,
    ):
        """
        初始化执行器

        Args:
            ask_service: AskService 实例（用于执行查询）
            executor: DatabaseExecutor 实例
        """
        self._ask_service = ask_service
        self._executor = executor

    def execute(self, query: str) -> tuple[list[dict], list[str]]:
        """
        执行查询

        Args:
            query: SQL 查询语句

        Returns:
            (数据列表, 列名列表)
        """
        if self._ask_service:
            import asyncio
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import nest_asyncio
                    nest_asyncio.apply()
                    result = loop.run_until_complete(self._ask_service.ask(query))
                    data = result.data if hasattr(result, "data") else []
                else:
                    data = loop.run_until_complete(self._ask_service.ask(query))
                    data = data.data if hasattr(data, "data") else data
            except RuntimeError:
                data = asyncio.run(self._ask_service.ask(query))
                data = data.data if hasattr(data, "data") else data
        elif self._executor:
            import asyncio
            data = asyncio.run(self._executor.execute(query))
        else:
            data = [{"id": 1, "message": "模拟数据"}]

        if not data:
            return [], []

        columns = list(data[0].keys()) if data else []
        return data, columns
