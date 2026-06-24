# backend/app/monitoring/alert_rules.py
"""告警规则模块

根据详细设计说明书 7.3 节实现。
定义系统告警规则，用于检测各类异常情况。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Tuple
import asyncio
import logging

from app.common.time import utcnow
from app.monitoring.alert_manager import AlertManager, AlertSeverity, get_alert_manager

logger = logging.getLogger(__name__)


class RuleType(str, Enum):
    """规则类型"""
    THRESHOLD = "threshold"           # 阈值规则
    RATE = "rate"                     # 速率规则
    COMPARISON = "comparison"         # 比较规则
    ANOMALY = "anomaly"              # 异常检测规则


class ComparisonOperator(str, Enum):
    """比较运算符"""
    GT = "gt"       # 大于
    GTE = "gte"     # 大于等于
    LT = "lt"       # 小于
    LTE = "lte"     # 小于等于
    EQ = "eq"       # 等于
    NEQ = "neq"     # 不等于


@dataclass
class AlertRuleConfig:
    """告警规则配置"""
    name: str                           # 规则名称
    description: str                    # 规则描述
    rule_type: RuleType                 # 规则类型
    metric_name: str                    # 指标名称
    severity: AlertSeverity             # 告警级别
    threshold: Optional[float] = None   # 阈值
    operator: ComparisonOperator = ComparisonOperator.GT
    duration: int = 60                  # 持续时间（秒）
    cooldown: int = 300                 # 冷却时间（秒）
    enabled: bool = True                # 是否启用
    labels: Dict[str, str] = field(default_factory=dict)
    annotations: Dict[str, str] = field(default_factory=dict)


@dataclass
class RuleState:
    """规则状态"""
    rule_name: str
    is_firing: bool = False
    firing_since: Optional[datetime] = None
    last_triggered: Optional[datetime] = None
    last_value: Optional[float] = None
    trigger_count: int = 0


class AlertRuleEngine:
    """告警规则引擎

    负责评估告警规则并触发告警。
    """

    def __init__(self, alert_manager: Optional[AlertManager] = None):
        """初始化规则引擎

        Args:
            alert_manager: 告警管理器
        """
        self.alert_manager = alert_manager
        self.rules: Dict[str, AlertRuleConfig] = {}
        self.states: Dict[str, RuleState] = {}
        self._metric_providers: Dict[str, Callable] = {}

    def register_rule(self, rule: AlertRuleConfig) -> None:
        """注册告警规则

        Args:
            rule: 告警规则配置
        """
        self.rules[rule.name] = rule
        self.states[rule.name] = RuleState(rule_name=rule.name)
        logger.info(f"Registered alert rule: {rule.name}")

    def unregister_rule(self, rule_name: str) -> None:
        """注销告警规则

        Args:
            rule_name: 规则名称
        """
        if rule_name in self.rules:
            del self.rules[rule_name]
            del self.states[rule_name]
            logger.info(f"Unregistered alert rule: {rule_name}")

    def register_metric_provider(
        self,
        metric_name: str,
        provider: Callable[[], float]
    ) -> None:
        """注册指标提供者

        Args:
            metric_name: 指标名称
            provider: 指标获取函数
        """
        self._metric_providers[metric_name] = provider

    async def get_metric_value(self, metric_name: str) -> Optional[float]:
        """获取指标值

        Args:
            metric_name: 指标名称

        Returns:
            Optional[float]: 指标值
        """
        provider = self._metric_providers.get(metric_name)
        if provider is None:
            logger.warning(f"No provider for metric: {metric_name}")
            return None

        try:
            if asyncio.iscoroutinefunction(provider):
                return await provider()
            return provider()
        except Exception as e:
            logger.error(f"Error getting metric {metric_name}: {e}")
            return None

    def _compare(
        self,
        value: float,
        threshold: float,
        operator: ComparisonOperator
    ) -> bool:
        """比较值与阈值

        Args:
            value: 当前值
            threshold: 阈值
            operator: 比较运算符

        Returns:
            bool: 比较结果
        """
        if operator == ComparisonOperator.GT:
            return value > threshold
        elif operator == ComparisonOperator.GTE:
            return value >= threshold
        elif operator == ComparisonOperator.LT:
            return value < threshold
        elif operator == ComparisonOperator.LTE:
            return value <= threshold
        elif operator == ComparisonOperator.EQ:
            return value == threshold
        elif operator == ComparisonOperator.NEQ:
            return value != threshold
        return False

    async def evaluate_rule(self, rule: AlertRuleConfig) -> Tuple[bool, Optional[float]]:
        """评估单个规则

        Args:
            rule: 告警规则

        Returns:
            Tuple[bool, Optional[float]]: (是否触发, 当前值)
        """
        if not rule.enabled:
            return False, None

        value = await self.get_metric_value(rule.metric_name)
        if value is None:
            return False, None

        if rule.threshold is None:
            return False, value

        is_triggered = self._compare(value, rule.threshold, rule.operator)
        return is_triggered, value

    async def check_rule(self, rule_name: str) -> Optional[Dict[str, Any]]:
        """检查规则并可能触发告警

        Args:
            rule_name: 规则名称

        Returns:
            Optional[Dict]: 告警信息（如果触发）
        """
        rule = self.rules.get(rule_name)
        if rule is None:
            return None

        state = self.states[rule_name]
        now = utcnow()

        # 检查冷却时间
        if state.last_triggered:
            cooldown_end = state.last_triggered + timedelta(seconds=rule.cooldown)
            if now < cooldown_end:
                return None

        is_triggered, value = await self.evaluate_rule(rule)
        state.last_value = value

        if is_triggered:
            if not state.is_firing:
                state.is_firing = True
                state.firing_since = now
            else:
                # 检查持续时间
                duration = (now - state.firing_since).total_seconds()
                if duration >= rule.duration:
                    # 触发告警
                    state.last_triggered = now
                    state.trigger_count += 1

                    alert_info = {
                        "rule_name": rule.name,
                        "description": rule.description,
                        "severity": rule.severity.value,
                        "metric_name": rule.metric_name,
                        "current_value": value,
                        "threshold": rule.threshold,
                        "operator": rule.operator.value,
                        "duration": duration,
                        "trigger_count": state.trigger_count,
                        "labels": rule.labels,
                        "annotations": rule.annotations
                    }

                    # 发送告警
                    if self.alert_manager:
                        await self.alert_manager.send_alert(
                            alert_type=f"rule:{rule.name}",
                            severity=rule.severity,
                            title=f"Alert: {rule.name}",
                            message=f"{rule.description}. Current value: {value}, threshold: {rule.threshold}",
                            source="alert_rule_engine",
                            details=alert_info
                        )

                    logger.warning(f"Alert triggered: {rule.name}, value={value}, threshold={rule.threshold}")
                    return alert_info
        else:
            # 恢复
            if state.is_firing:
                state.is_firing = False
                state.firing_since = None
                logger.info(f"Alert resolved: {rule.name}")

        return None

    async def check_all_rules(self) -> List[Dict[str, Any]]:
        """检查所有规则

        Returns:
            List[Dict]: 触发的告警列表
        """
        alerts = []
        for rule_name in self.rules:
            alert = await self.check_rule(rule_name)
            if alert:
                alerts.append(alert)
        return alerts

    def get_rule_states(self) -> Dict[str, Dict[str, Any]]:
        """获取所有规则状态

        Returns:
            Dict: 规则状态
        """
        return {
            name: {
                "is_firing": state.is_firing,
                "firing_since": state.firing_since.isoformat() if state.firing_since else None,
                "last_triggered": state.last_triggered.isoformat() if state.last_triggered else None,
                "last_value": state.last_value,
                "trigger_count": state.trigger_count
            }
            for name, state in self.states.items()
        }


# 预定义的告警规则
def create_default_rules() -> List[AlertRuleConfig]:
    """创建默认告警规则

    Returns:
        List[AlertRuleConfig]: 默认规则列表
    """
    return [
        # 任务失败率告警
        AlertRuleConfig(
            name="task_failure_rate_high",
            description="Task failure rate exceeds threshold",
            rule_type=RuleType.THRESHOLD,
            metric_name="task_failure_rate",
            severity=AlertSeverity.WARNING,
            threshold=0.1,  # 10%
            operator=ComparisonOperator.GT,
            duration=300,
            cooldown=600,
            labels={"category": "task"},
            annotations={"runbook": "Check task logs for errors"}
        ),

        AlertRuleConfig(
            name="task_failure_rate_critical",
            description="Task failure rate is critically high",
            rule_type=RuleType.THRESHOLD,
            metric_name="task_failure_rate",
            severity=AlertSeverity.CRITICAL,
            threshold=0.3,  # 30%
            operator=ComparisonOperator.GT,
            duration=180,
            cooldown=300,
            labels={"category": "task"},
            annotations={"runbook": "Immediate investigation required"}
        ),

        # GPU温度告警
        AlertRuleConfig(
            name="gpu_temperature_high",
            description="GPU temperature exceeds safe threshold",
            rule_type=RuleType.THRESHOLD,
            metric_name="gpu_temperature_max",
            severity=AlertSeverity.WARNING,
            threshold=80.0,  # 80°C
            operator=ComparisonOperator.GT,
            duration=60,
            cooldown=300,
            labels={"category": "gpu"},
            annotations={"runbook": "Check GPU cooling and workload"}
        ),

        AlertRuleConfig(
            name="gpu_temperature_critical",
            description="GPU temperature is critically high",
            rule_type=RuleType.THRESHOLD,
            metric_name="gpu_temperature_max",
            severity=AlertSeverity.CRITICAL,
            threshold=90.0,  # 90°C
            operator=ComparisonOperator.GT,
            duration=30,
            cooldown=120,
            labels={"category": "gpu"},
            annotations={"runbook": "Reduce GPU workload immediately"}
        ),

        # GPU利用率告警
        AlertRuleConfig(
            name="gpu_utilization_high",
            description="GPU utilization is consistently high",
            rule_type=RuleType.THRESHOLD,
            metric_name="gpu_utilization_avg",
            severity=AlertSeverity.INFO,
            threshold=95.0,  # 95%
            operator=ComparisonOperator.GT,
            duration=600,
            cooldown=1800,
            labels={"category": "gpu"},
            annotations={"runbook": "Consider scaling GPU resources"}
        ),

        # GPU内存告警
        AlertRuleConfig(
            name="gpu_memory_high",
            description="GPU memory usage is high",
            rule_type=RuleType.THRESHOLD,
            metric_name="gpu_memory_usage_percent",
            severity=AlertSeverity.WARNING,
            threshold=90.0,  # 90%
            operator=ComparisonOperator.GT,
            duration=120,
            cooldown=600,
            labels={"category": "gpu"},
            annotations={"runbook": "Check for memory leaks or reduce batch sizes"}
        ),

        # 磁盘使用告警
        AlertRuleConfig(
            name="disk_usage_high",
            description="Disk usage exceeds threshold",
            rule_type=RuleType.THRESHOLD,
            metric_name="disk_usage_percent",
            severity=AlertSeverity.WARNING,
            threshold=80.0,  # 80%
            operator=ComparisonOperator.GT,
            duration=300,
            cooldown=1800,
            labels={"category": "storage"},
            annotations={"runbook": "Clean up old files or expand storage"}
        ),

        AlertRuleConfig(
            name="disk_usage_critical",
            description="Disk usage is critically high",
            rule_type=RuleType.THRESHOLD,
            metric_name="disk_usage_percent",
            severity=AlertSeverity.CRITICAL,
            threshold=95.0,  # 95%
            operator=ComparisonOperator.GT,
            duration=60,
            cooldown=600,
            labels={"category": "storage"},
            annotations={"runbook": "Immediate cleanup required"}
        ),

        # Celery队列长度告警
        AlertRuleConfig(
            name="celery_queue_backlog",
            description="Celery queue has significant backlog",
            rule_type=RuleType.THRESHOLD,
            metric_name="celery_queue_length",
            severity=AlertSeverity.WARNING,
            threshold=100,
            operator=ComparisonOperator.GT,
            duration=300,
            cooldown=600,
            labels={"category": "celery"},
            annotations={"runbook": "Scale workers or investigate slow tasks"}
        ),

        AlertRuleConfig(
            name="celery_queue_critical",
            description="Celery queue backlog is critical",
            rule_type=RuleType.THRESHOLD,
            metric_name="celery_queue_length",
            severity=AlertSeverity.CRITICAL,
            threshold=500,
            operator=ComparisonOperator.GT,
            duration=120,
            cooldown=300,
            labels={"category": "celery"},
            annotations={"runbook": "Immediate scaling required"}
        ),

        # API响应时间告警
        AlertRuleConfig(
            name="api_latency_high",
            description="API response time is high",
            rule_type=RuleType.THRESHOLD,
            metric_name="api_latency_p95",
            severity=AlertSeverity.WARNING,
            threshold=1.0,  # 1秒
            operator=ComparisonOperator.GT,
            duration=180,
            cooldown=600,
            labels={"category": "api"},
            annotations={"runbook": "Check database queries and external services"}
        ),

        # 数据库连接池告警
        AlertRuleConfig(
            name="db_connections_high",
            description="Database connection pool usage is high",
            rule_type=RuleType.THRESHOLD,
            metric_name="db_pool_usage_percent",
            severity=AlertSeverity.WARNING,
            threshold=80.0,  # 80%
            operator=ComparisonOperator.GT,
            duration=120,
            cooldown=600,
            labels={"category": "database"},
            annotations={"runbook": "Check for connection leaks or increase pool size"}
        ),

        # Redis内存告警
        AlertRuleConfig(
            name="redis_memory_high",
            description="Redis memory usage is high",
            rule_type=RuleType.THRESHOLD,
            metric_name="redis_memory_usage_percent",
            severity=AlertSeverity.WARNING,
            threshold=80.0,  # 80%
            operator=ComparisonOperator.GT,
            duration=300,
            cooldown=1800,
            labels={"category": "redis"},
            annotations={"runbook": "Review cache policies and eviction settings"}
        ),

        # 错误率告警
        AlertRuleConfig(
            name="error_rate_high",
            description="HTTP error rate exceeds threshold",
            rule_type=RuleType.THRESHOLD,
            metric_name="http_error_rate",
            severity=AlertSeverity.WARNING,
            threshold=0.05,  # 5%
            operator=ComparisonOperator.GT,
            duration=180,
            cooldown=600,
            labels={"category": "api"},
            annotations={"runbook": "Check application logs for errors"}
        ),
    ]


# 告警规则检查函数（用于 Celery 定时任务）
async def check_task_failure_rate() -> float:
    """检查任务失败率

    Returns:
        float: 失败率 (0-1)
    """
    from app.database.session import async_session_factory
    from app.models.tasks import Task, TaskStatus
    from sqlalchemy import select, func
    from datetime import timedelta

    async with async_session_factory() as session:
        # 查询最近1小时的任务
        since = utcnow() - timedelta(hours=1)

        total_query = select(func.count(Task.id)).where(
            Task.created_at >= since
        )
        total_result = await session.execute(total_query)
        total = total_result.scalar() or 0

        if total == 0:
            return 0.0

        failed_query = select(func.count(Task.id)).where(
            Task.created_at >= since,
            Task.status == TaskStatus.FAILURE.value
        )
        failed_result = await session.execute(failed_query)
        failed = failed_result.scalar() or 0

        return failed / total


async def check_gpu_temperature() -> float:
    """检查GPU最高温度

    Returns:
        float: 最高温度
    """
    from app.gpu.detector import get_gpu_detector

    detector = get_gpu_detector()
    stats = await detector.get_gpu_stats()

    if not stats:
        return 0.0

    return max(s.temperature for s in stats)


async def check_disk_usage() -> float:
    """检查磁盘使用率

    Returns:
        float: 使用率百分比
    """
    import shutil

    try:
        total, used, free = shutil.disk_usage("/")
        return (used / total) * 100
    except Exception:
        return 0.0


async def check_celery_queue_length() -> int:
    """检查Celery队列长度

    Returns:
        int: 队列长度
    """
    from app.cache.factory import get_cache

    cache = get_cache()
    try:
        # 尝试从Redis获取队列长度
        length = await cache.get("celery:queue:default:length")
        return int(length) if length else 0
    except Exception:
        return 0


# 全局规则引擎实例
_rule_engine: Optional[AlertRuleEngine] = None


def get_rule_engine() -> AlertRuleEngine:
    """获取告警规则引擎单例

    Returns:
        AlertRuleEngine: 规则引擎实例
    """
    global _rule_engine
    if _rule_engine is None:
        _rule_engine = AlertRuleEngine(alert_manager=get_alert_manager())

        # 注册默认规则
        for rule in create_default_rules():
            _rule_engine.register_rule(rule)

        # 注册指标提供者
        _rule_engine.register_metric_provider("task_failure_rate", check_task_failure_rate)
        _rule_engine.register_metric_provider("gpu_temperature_max", check_gpu_temperature)
        _rule_engine.register_metric_provider("disk_usage_percent", check_disk_usage)
        _rule_engine.register_metric_provider("celery_queue_length", check_celery_queue_length)

    return _rule_engine


async def run_alert_checks() -> List[Dict[str, Any]]:
    """运行所有告警检查

    Returns:
        List[Dict]: 触发的告警列表
    """
    engine = get_rule_engine()
    return await engine.check_all_rules()
