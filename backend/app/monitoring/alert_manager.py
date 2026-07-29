# backend/app/monitoring/alert_manager.py
"""告警管理器

根据详细设计说明书 7.3 节实现。
负责告警的发送、记录和通知。
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Dict, List, Optional
import logging
import json
from app.common.time import utcnow

logger = logging.getLogger(__name__)


class AlertSeverity(str, Enum):
    """告警级别"""
    INFO = "info"           # 信息
    WARNING = "warning"     # 警告
    ERROR = "error"         # 错误
    CRITICAL = "critical"   # 严重


class AlertChannel(str, Enum):
    """告警通道"""
    LOG = "log"             # 日志记录
    EMAIL = "email"         # 邮件通知
    WEBHOOK = "webhook"     # Webhook通知
    SMS = "sms"             # 短信通知


@dataclass
class Alert:
    """告警对象"""
    id: str
    title: str
    message: str
    severity: AlertSeverity
    source: str                     # 告警来源（gpu, task, storage等）
    timestamp: datetime
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, Any] = field(default_factory=dict)
    resolved: bool = False
    resolved_at: Optional[datetime] = None


@dataclass
class AlertRule:
    """告警规则"""
    name: str
    condition: str                  # 条件描述
    severity: AlertSeverity
    channels: List[AlertChannel]
    cooldown_seconds: int = 300     # 冷却时间，避免重复告警
    enabled: bool = True


class AlertManager:
    """告警管理器

    功能：
    1. 发送告警
    2. 记录告警历史
    3. 多渠道通知（日志、邮件、Webhook）
    4. 告警去重和冷却
    """

    # 默认告警冷却时间（秒）
    DEFAULT_COOLDOWN = 300

    def __init__(
        self,
        cache_client=None,
        email_config: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None
    ):
        """初始化告警管理器

        Args:
            cache_client: 缓存客户端（用于存储告警历史和去重）
            email_config: 邮件配置
            webhook_url: Webhook URL
        """
        self.cache = cache_client
        self.email_config = email_config
        self.webhook_url = webhook_url

        # 告警历史（内存缓存，用于无Redis场景）
        self._alert_history: List[Alert] = []
        self._last_alert_times: Dict[str, datetime] = {}

        # 通知处理器
        self._handlers: Dict[AlertChannel, Callable] = {
            AlertChannel.LOG: self._log_alert,
            AlertChannel.EMAIL: self._send_email_alert,
            AlertChannel.WEBHOOK: self._send_webhook_alert,
        }

    async def send_alert(
        self,
        title: str,
        message: str,
        severity: AlertSeverity,
        source: str,
        labels: Optional[Dict[str, str]] = None,
        annotations: Optional[Dict[str, Any]] = None,
        channels: Optional[List[AlertChannel]] = None,
        dedupe_key: Optional[str] = None,
        cooldown: int = DEFAULT_COOLDOWN
    ) -> Optional[Alert]:
        """发送告警

        Args:
            title: 告警标题
            message: 告警消息
            severity: 告警级别
            source: 告警来源
            labels: 标签
            annotations: 注解
            channels: 通知渠道（默认仅日志）
            dedupe_key: 去重键
            cooldown: 冷却时间

        Returns:
            Optional[Alert]: 告警对象，如果被去重则返回None
        """
        import uuid

        # 生成去重键
        if dedupe_key is None:
            dedupe_key = f"{source}:{title}"

        # 检查冷却
        if not await self._check_cooldown(dedupe_key, cooldown):
            logger.debug(f"Alert suppressed (cooldown): {dedupe_key}")
            return None

        # 创建告警
        alert = Alert(
            id=str(uuid.uuid4()),
            title=title,
            message=message,
            severity=severity,
            source=source,
            timestamp=utcnow(),
            labels=labels or {},
            annotations=annotations or {}
        )

        # 默认渠道
        if channels is None:
            channels = [AlertChannel.LOG]
            # 严重告警添加更多渠道
            if severity in (AlertSeverity.ERROR, AlertSeverity.CRITICAL):
                if self.webhook_url:
                    channels.append(AlertChannel.WEBHOOK)
                if self.email_config:
                    channels.append(AlertChannel.EMAIL)

        # 发送到各渠道
        for channel in channels:
            handler = self._handlers.get(channel)
            if handler:
                try:
                    await handler(alert)
                except Exception as e:
                    logger.error(f"Failed to send alert via {channel}: {e}")

        # 记录历史
        await self._record_alert(alert)

        # 更新冷却时间
        self._last_alert_times[dedupe_key] = utcnow()

        return alert

    async def resolve_alert(
        self,
        alert_id: str,
        message: Optional[str] = None
    ) -> bool:
        """解除告警

        Args:
            alert_id: 告警ID
            message: 解除消息

        Returns:
            bool: 是否成功
        """
        # 从历史中查找并标记为已解除
        for alert in self._alert_history:
            if alert.id == alert_id and not alert.resolved:
                alert.resolved = True
                alert.resolved_at = utcnow()
                if message:
                    alert.annotations["resolve_message"] = message

                logger.info(
                    f"Alert resolved: {alert.title}",
                    extra={"alert_id": alert_id, "message": message}
                )
                return True

        return False

    async def _check_cooldown(self, dedupe_key: str, cooldown: int) -> bool:
        """检查冷却时间

        Args:
            dedupe_key: 去重键
            cooldown: 冷却时间（秒）

        Returns:
            bool: 是否可以发送
        """
        last_time = self._last_alert_times.get(dedupe_key)
        if last_time is None:
            return True

        elapsed = (utcnow() - last_time).total_seconds()
        return elapsed >= cooldown

    async def _log_alert(self, alert: Alert) -> None:
        """记录告警到日志"""
        log_data = {
            "alert_id": alert.id,
            "title": alert.title,
            "source": alert.source,
            "severity": alert.severity.value,
            "labels": alert.labels
        }

        if alert.severity == AlertSeverity.CRITICAL:
            logger.critical(alert.message, extra=log_data)
        elif alert.severity == AlertSeverity.ERROR:
            logger.error(alert.message, extra=log_data)
        elif alert.severity == AlertSeverity.WARNING:
            logger.warning(alert.message, extra=log_data)
        else:
            logger.info(alert.message, extra=log_data)

    async def _send_email_alert(self, alert: Alert) -> None:
        """发送邮件告警"""
        if not self.email_config:
            logger.warning("Email alert skipped: no email config")
            return

        try:
            import smtplib
            from email.mime.text import MIMEText
            from email.mime.multipart import MIMEMultipart

            smtp_host = self.email_config.get("smtp_host")
            smtp_port = self.email_config.get("smtp_port", 587)
            username = self.email_config.get("username")
            password = self.email_config.get("password")
            from_addr = self.email_config.get("from_addr")
            to_addrs = self.email_config.get("to_addrs", [])

            if not all([smtp_host, username, password, from_addr, to_addrs]):
                logger.warning("Email alert skipped: incomplete config")
                return

            # 构建邮件
            msg = MIMEMultipart()
            msg["Subject"] = f"[{alert.severity.value.upper()}] {alert.title}"
            msg["From"] = from_addr
            msg["To"] = ", ".join(to_addrs)

            body = f"""
Alert: {alert.title}
Severity: {alert.severity.value}
Source: {alert.source}
Time: {alert.timestamp.isoformat()}

Message:
{alert.message}

Labels:
{json.dumps(alert.labels, indent=2)}
"""
            msg.attach(MIMEText(body, "plain"))

            # 发送
            with smtplib.SMTP(smtp_host, smtp_port) as server:
                server.starttls()
                server.login(username, password)
                server.sendmail(from_addr, to_addrs, msg.as_string())

            logger.info(f"Email alert sent: {alert.title}")

        except Exception as e:
            logger.error(f"Failed to send email alert: {e}")
            raise

    async def _send_webhook_alert(self, alert: Alert) -> None:
        """发送Webhook告警"""
        if not self.webhook_url:
            logger.warning("Webhook alert skipped: no webhook URL")
            return

        try:
            import aiohttp

            payload = {
                "alert_id": alert.id,
                "title": alert.title,
                "message": alert.message,
                "severity": alert.severity.value,
                "source": alert.source,
                "timestamp": alert.timestamp.isoformat(),
                "labels": alert.labels,
                "annotations": alert.annotations
            }

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self.webhook_url,
                    json=payload,
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status >= 400:
                        logger.warning(
                            f"Webhook returned {response.status}: {await response.text()}"
                        )
                    else:
                        logger.info(f"Webhook alert sent: {alert.title}")

        except ImportError:
            logger.warning("aiohttp not installed, webhook alert skipped")
        except Exception as e:
            logger.error(f"Failed to send webhook alert: {e}")
            raise

    async def _record_alert(self, alert: Alert) -> None:
        """记录告警历史"""
        self._alert_history.append(alert)

        # 限制内存中的历史数量
        if len(self._alert_history) > 1000:
            self._alert_history = self._alert_history[-500:]

        # 存储到缓存
        if self.cache:
            try:
                alert_data = {
                    "id": alert.id,
                    "title": alert.title,
                    "message": alert.message,
                    "severity": alert.severity.value,
                    "source": alert.source,
                    "timestamp": alert.timestamp.isoformat(),
                    "labels": alert.labels,
                    "resolved": alert.resolved
                }
                await self.cache.lpush("alerts:history", json.dumps(alert_data))
                await self.cache.ltrim("alerts:history", 0, 999)
            except Exception as e:
                logger.warning(f"Failed to cache alert: {e}")

    async def get_alerts(
        self,
        limit: int = 100,
        severity: Optional[AlertSeverity] = None,
        source: Optional[str] = None,
        resolved: Optional[bool] = None
    ) -> List[Alert]:
        """获取告警列表

        Args:
            limit: 返回数量限制
            severity: 按级别筛选
            source: 按来源筛选
            resolved: 按是否解除筛选

        Returns:
            List[Alert]: 告警列表
        """
        alerts = self._alert_history.copy()

        # 筛选
        if severity:
            alerts = [a for a in alerts if a.severity == severity]
        if source:
            alerts = [a for a in alerts if a.source == source]
        if resolved is not None:
            alerts = [a for a in alerts if a.resolved == resolved]

        # 按时间倒序
        alerts.sort(key=lambda a: a.timestamp, reverse=True)

        return alerts[:limit]

    async def get_alert_stats(self) -> Dict[str, Any]:
        """获取告警统计

        Returns:
            Dict[str, Any]: 告警统计
        """
        alerts = self._alert_history

        # 按级别统计
        by_severity = {}
        for severity in AlertSeverity:
            by_severity[severity.value] = len(
                [a for a in alerts if a.severity == severity]
            )

        # 按来源统计
        by_source = {}
        for alert in alerts:
            by_source[alert.source] = by_source.get(alert.source, 0) + 1

        # 未解除告警
        active_count = len([a for a in alerts if not a.resolved])

        return {
            "total": len(alerts),
            "active": active_count,
            "resolved": len(alerts) - active_count,
            "by_severity": by_severity,
            "by_source": by_source
        }


# 全局告警管理器
_alert_manager: Optional[AlertManager] = None


def get_alert_manager() -> AlertManager:
    """获取告警管理器单例"""
    global _alert_manager
    if _alert_manager is None:
        _alert_manager = AlertManager()
    return _alert_manager


# 便捷函数
async def send_alert(
    title: str,
    message: str,
    severity: AlertSeverity = AlertSeverity.WARNING,
    source: str = "system",
    **kwargs
) -> Optional[Alert]:
    """发送告警的便捷函数"""
    manager = get_alert_manager()
    return await manager.send_alert(
        title=title,
        message=message,
        severity=severity,
        source=source,
        **kwargs
    )
