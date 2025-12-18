# backend/app/logging/audit.py
"""审计日志模块

根据详细设计说明书 9.3 节实现。
记录用户操作、数据访问和管理员操作的审计日志。
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from typing import Any, Dict, List, Optional
import json
import logging
import os
import uuid

from app.logging.rotation import (
    LogRotationConfig,
    TimeRotationConfig,
    TimeInterval,
    RotationType,
    create_rotating_handler
)
from app.logging.sanitizer import LogSanitizer

logger = logging.getLogger(__name__)


class AuditAction(str, Enum):
    """审计操作类型"""
    # 认证相关
    LOGIN = "login"
    LOGOUT = "logout"
    LOGIN_FAILED = "login_failed"
    PASSWORD_CHANGE = "password_change"
    TOKEN_REFRESH = "token_refresh"

    # 数据操作
    CREATE = "create"
    READ = "read"
    UPDATE = "update"
    DELETE = "delete"
    EXPORT = "export"
    IMPORT = "import"

    # 任务相关
    TASK_SUBMIT = "task_submit"
    TASK_CANCEL = "task_cancel"
    TASK_RETRY = "task_retry"

    # 文件相关
    FILE_UPLOAD = "file_upload"
    FILE_DOWNLOAD = "file_download"
    FILE_DELETE = "file_delete"

    # 管理员操作
    ADMIN_USER_CREATE = "admin_user_create"
    ADMIN_USER_UPDATE = "admin_user_update"
    ADMIN_USER_DELETE = "admin_user_delete"
    ADMIN_CONFIG_CHANGE = "admin_config_change"
    ADMIN_TOOL_CREATE = "admin_tool_create"
    ADMIN_TOOL_UPDATE = "admin_tool_update"

    # 系统操作
    SYSTEM_START = "system_start"
    SYSTEM_STOP = "system_stop"
    SYSTEM_CONFIG = "system_config"


class AuditResult(str, Enum):
    """审计结果"""
    SUCCESS = "success"
    FAILURE = "failure"
    DENIED = "denied"
    ERROR = "error"


class ResourceType(str, Enum):
    """资源类型"""
    USER = "user"
    TASK = "task"
    TOOL = "tool"
    FILE = "file"
    CONFIG = "config"
    SESSION = "session"
    SYSTEM = "system"


@dataclass
class AuditEvent:
    """审计事件"""
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=datetime.utcnow)
    action: AuditAction = AuditAction.READ
    result: AuditResult = AuditResult.SUCCESS
    user_id: Optional[str] = None
    user_email: Optional[str] = None
    user_role: Optional[str] = None
    resource_type: Optional[ResourceType] = None
    resource_id: Optional[str] = None
    resource_name: Optional[str] = None
    client_ip: Optional[str] = None
    user_agent: Optional[str] = None
    request_id: Optional[str] = None
    session_id: Optional[str] = None
    changes: Optional[Dict[str, Any]] = None
    reason: Optional[str] = None
    duration_ms: Optional[float] = None
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "id": self.id,
            "timestamp": self.timestamp.isoformat() + "Z",
            "action": self.action.value,
            "result": self.result.value,
            "user_id": self.user_id,
            "user_email": self.user_email,
            "user_role": self.user_role,
            "resource_type": self.resource_type.value if self.resource_type else None,
            "resource_id": self.resource_id,
            "resource_name": self.resource_name,
            "client_ip": self.client_ip,
            "user_agent": self.user_agent,
            "request_id": self.request_id,
            "session_id": self.session_id,
            "changes": self.changes,
            "reason": self.reason,
            "duration_ms": self.duration_ms,
            "extra": self.extra
        }


class AuditLogger:
    """审计日志记录器

    专门用于记录审计日志，支持：
    - 用户操作审计
    - 数据访问审计
    - 管理员操作审计
    - 安全事件审计
    """

    def __init__(
        self,
        log_dir: str = "logs/audit",
        enable_file_logging: bool = True,
        enable_db_logging: bool = False,
        sanitize: bool = True
    ):
        """初始化审计日志器

        Args:
            log_dir: 日志目录
            enable_file_logging: 是否启用文件日志
            enable_db_logging: 是否启用数据库日志
            sanitize: 是否对敏感数据脱敏
        """
        self.log_dir = log_dir
        self.enable_file_logging = enable_file_logging
        self.enable_db_logging = enable_db_logging
        self.sanitize = sanitize

        # 日志脱敏器
        self._sanitizer = LogSanitizer() if sanitize else None

        # 设置审计日志器
        self._logger = logging.getLogger("audit")
        self._logger.setLevel(logging.INFO)
        self._logger.propagate = False  # 不传播到父日志器

        if enable_file_logging:
            self._setup_file_handler()

    def _setup_file_handler(self) -> None:
        """设置文件处理器"""
        os.makedirs(self.log_dir, exist_ok=True)

        config = LogRotationConfig(
            rotation_type=RotationType.TIME,
            time_config=TimeRotationConfig(
                when=TimeInterval.MIDNIGHT,
                interval=1,
                backup_count=90  # 保留90天的审计日志
            ),
            compress=True,
            log_dir=self.log_dir,
            file_prefix="audit"
        )

        handler = create_rotating_handler(config, "log")

        # JSON格式化器
        class AuditFormatter(logging.Formatter):
            def format(self, record):
                if hasattr(record, "audit_data"):
                    return json.dumps(record.audit_data, ensure_ascii=False)
                return super().format(record)

        handler.setFormatter(AuditFormatter())
        self._logger.addHandler(handler)

    def _sanitize_event(self, event: AuditEvent) -> AuditEvent:
        """对审计事件进行脱敏

        Args:
            event: 原始事件

        Returns:
            AuditEvent: 脱敏后的事件
        """
        if not self._sanitizer:
            return event

        # 脱敏邮箱
        if event.user_email:
            event.user_email = self._sanitizer.mask_email(event.user_email)

        # 脱敏changes中的敏感字段
        if event.changes:
            event.changes = self._sanitizer.sanitize(event.changes)

        # 脱敏extra中的敏感字段
        if event.extra:
            event.extra = self._sanitizer.sanitize(event.extra)

        return event

    def log(self, event: AuditEvent) -> None:
        """记录审计事件

        Args:
            event: 审计事件
        """
        # 脱敏处理
        if self.sanitize:
            event = self._sanitize_event(event)

        # 写入文件日志
        if self.enable_file_logging:
            record = logging.LogRecord(
                name="audit",
                level=logging.INFO,
                pathname="",
                lineno=0,
                msg="",
                args=(),
                exc_info=None
            )
            record.audit_data = event.to_dict()
            self._logger.handle(record)

        # 写入数据库（如果启用）
        if self.enable_db_logging:
            self._log_to_db(event)

    def _log_to_db(self, event: AuditEvent) -> None:
        """写入数据库日志（异步）

        Args:
            event: 审计事件
        """
        # TODO: 实现数据库写入
        pass

    def log_user_action(
        self,
        action: AuditAction,
        user_id: str,
        result: AuditResult = AuditResult.SUCCESS,
        resource_type: Optional[ResourceType] = None,
        resource_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        changes: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        **extra
    ) -> None:
        """记录用户操作

        Args:
            action: 操作类型
            user_id: 用户ID
            result: 操作结果
            resource_type: 资源类型
            resource_id: 资源ID
            client_ip: 客户端IP
            user_agent: User-Agent
            changes: 变更内容
            reason: 原因/备注
            **extra: 额外字段
        """
        event = AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            client_ip=client_ip,
            user_agent=user_agent,
            changes=changes,
            reason=reason,
            extra=extra
        )
        self.log(event)

    def log_data_access(
        self,
        user_id: str,
        resource_type: ResourceType,
        resource_id: str,
        action: AuditAction = AuditAction.READ,
        result: AuditResult = AuditResult.SUCCESS,
        fields_accessed: Optional[List[str]] = None,
        client_ip: Optional[str] = None,
        **extra
    ) -> None:
        """记录数据访问

        Args:
            user_id: 用户ID
            resource_type: 资源类型
            resource_id: 资源ID
            action: 访问类型
            result: 访问结果
            fields_accessed: 访问的字段列表
            client_ip: 客户端IP
            **extra: 额外字段
        """
        extra_data = extra.copy()
        if fields_accessed:
            extra_data["fields_accessed"] = fields_accessed

        event = AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            resource_type=resource_type,
            resource_id=resource_id,
            client_ip=client_ip,
            extra=extra_data
        )
        self.log(event)

    def log_admin_operation(
        self,
        admin_id: str,
        action: AuditAction,
        target_type: ResourceType,
        target_id: str,
        result: AuditResult = AuditResult.SUCCESS,
        changes: Optional[Dict[str, Any]] = None,
        reason: Optional[str] = None,
        client_ip: Optional[str] = None,
        **extra
    ) -> None:
        """记录管理员操作

        Args:
            admin_id: 管理员ID
            action: 操作类型
            target_type: 目标类型
            target_id: 目标ID
            result: 操作结果
            changes: 变更内容
            reason: 操作原因
            client_ip: 客户端IP
            **extra: 额外字段
        """
        extra_data = extra.copy()
        extra_data["is_admin_action"] = True

        event = AuditEvent(
            action=action,
            result=result,
            user_id=admin_id,
            user_role="admin",
            resource_type=target_type,
            resource_id=target_id,
            changes=changes,
            reason=reason,
            client_ip=client_ip,
            extra=extra_data
        )
        self.log(event)

    def log_login(
        self,
        user_id: Optional[str],
        email: str,
        result: AuditResult,
        client_ip: str,
        user_agent: Optional[str] = None,
        reason: Optional[str] = None,
        **extra
    ) -> None:
        """记录登录事件

        Args:
            user_id: 用户ID（登录失败时可能为None）
            email: 用户邮箱
            result: 登录结果
            client_ip: 客户端IP
            user_agent: User-Agent
            reason: 失败原因
            **extra: 额外字段
        """
        action = AuditAction.LOGIN if result == AuditResult.SUCCESS else AuditAction.LOGIN_FAILED

        event = AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            user_email=email,
            client_ip=client_ip,
            user_agent=user_agent,
            reason=reason,
            extra=extra
        )
        self.log(event)

    def log_logout(
        self,
        user_id: str,
        session_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        **extra
    ) -> None:
        """记录登出事件

        Args:
            user_id: 用户ID
            session_id: 会话ID
            client_ip: 客户端IP
            **extra: 额外字段
        """
        event = AuditEvent(
            action=AuditAction.LOGOUT,
            result=AuditResult.SUCCESS,
            user_id=user_id,
            session_id=session_id,
            client_ip=client_ip,
            extra=extra
        )
        self.log(event)

    def log_file_operation(
        self,
        user_id: str,
        action: AuditAction,
        file_id: str,
        file_name: str,
        result: AuditResult = AuditResult.SUCCESS,
        file_size: Optional[int] = None,
        client_ip: Optional[str] = None,
        **extra
    ) -> None:
        """记录文件操作

        Args:
            user_id: 用户ID
            action: 操作类型
            file_id: 文件ID
            file_name: 文件名
            result: 操作结果
            file_size: 文件大小
            client_ip: 客户端IP
            **extra: 额外字段
        """
        extra_data = extra.copy()
        if file_size:
            extra_data["file_size"] = file_size

        event = AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            resource_type=ResourceType.FILE,
            resource_id=file_id,
            resource_name=file_name,
            client_ip=client_ip,
            extra=extra_data
        )
        self.log(event)

    def log_task_operation(
        self,
        user_id: str,
        action: AuditAction,
        task_id: str,
        tool_id: str,
        result: AuditResult = AuditResult.SUCCESS,
        client_ip: Optional[str] = None,
        **extra
    ) -> None:
        """记录任务操作

        Args:
            user_id: 用户ID
            action: 操作类型
            task_id: 任务ID
            tool_id: 工具ID
            result: 操作结果
            client_ip: 客户端IP
            **extra: 额外字段
        """
        extra_data = extra.copy()
        extra_data["tool_id"] = tool_id

        event = AuditEvent(
            action=action,
            result=result,
            user_id=user_id,
            resource_type=ResourceType.TASK,
            resource_id=task_id,
            client_ip=client_ip,
            extra=extra_data
        )
        self.log(event)


class AuditLogReader:
    """审计日志读取器

    用于查询和分析审计日志。
    """

    def __init__(self, log_dir: str = "logs/audit"):
        """初始化读取器

        Args:
            log_dir: 日志目录
        """
        self.log_dir = log_dir

    def query(
        self,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None,
        user_id: Optional[str] = None,
        action: Optional[AuditAction] = None,
        resource_type: Optional[ResourceType] = None,
        result: Optional[AuditResult] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """查询审计日志

        Args:
            start_time: 开始时间
            end_time: 结束时间
            user_id: 用户ID
            action: 操作类型
            resource_type: 资源类型
            result: 操作结果
            limit: 返回数量限制

        Returns:
            List[Dict]: 审计事件列表
        """
        events = []

        if not os.path.exists(self.log_dir):
            return events

        # 获取日志文件列表
        log_files = []
        for f in os.listdir(self.log_dir):
            if f.startswith("audit_") and (f.endswith(".log") or f.endswith(".log.gz")):
                log_files.append(os.path.join(self.log_dir, f))

        log_files.sort(reverse=True)  # 最新的在前

        for log_file in log_files:
            if len(events) >= limit:
                break

            file_events = self._read_log_file(log_file)

            for event in file_events:
                if len(events) >= limit:
                    break

                # 应用过滤条件
                if start_time and event.get("timestamp"):
                    event_time = datetime.fromisoformat(event["timestamp"].rstrip("Z"))
                    if event_time < start_time:
                        continue

                if end_time and event.get("timestamp"):
                    event_time = datetime.fromisoformat(event["timestamp"].rstrip("Z"))
                    if event_time > end_time:
                        continue

                if user_id and event.get("user_id") != user_id:
                    continue

                if action and event.get("action") != action.value:
                    continue

                if resource_type and event.get("resource_type") != resource_type.value:
                    continue

                if result and event.get("result") != result.value:
                    continue

                events.append(event)

        return events

    def _read_log_file(self, file_path: str) -> List[Dict[str, Any]]:
        """读取日志文件

        Args:
            file_path: 文件路径

        Returns:
            List[Dict]: 事件列表
        """
        import gzip

        events = []

        try:
            if file_path.endswith(".gz"):
                open_func = gzip.open
                mode = "rt"
            else:
                open_func = open
                mode = "r"

            with open_func(file_path, mode, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        try:
                            event = json.loads(line)
                            events.append(event)
                        except json.JSONDecodeError:
                            continue

        except Exception as e:
            logger.error(f"Failed to read audit log {file_path}: {e}")

        return events

    def get_user_activity(
        self,
        user_id: str,
        days: int = 7
    ) -> Dict[str, Any]:
        """获取用户活动统计

        Args:
            user_id: 用户ID
            days: 统计天数

        Returns:
            Dict: 活动统计
        """
        start_time = datetime.utcnow() - timedelta(days=days)
        events = self.query(
            start_time=start_time,
            user_id=user_id,
            limit=1000
        )

        action_counts = {}
        resource_counts = {}
        daily_counts = {}

        for event in events:
            # 按操作类型统计
            action = event.get("action", "unknown")
            action_counts[action] = action_counts.get(action, 0) + 1

            # 按资源类型统计
            resource = event.get("resource_type", "unknown")
            resource_counts[resource] = resource_counts.get(resource, 0) + 1

            # 按日期统计
            timestamp = event.get("timestamp", "")
            if timestamp:
                date = timestamp[:10]
                daily_counts[date] = daily_counts.get(date, 0) + 1

        return {
            "user_id": user_id,
            "period_days": days,
            "total_events": len(events),
            "by_action": action_counts,
            "by_resource": resource_counts,
            "by_date": daily_counts
        }


# 全局审计日志器
_audit_logger: Optional[AuditLogger] = None


def get_audit_logger() -> AuditLogger:
    """获取审计日志器单例

    Returns:
        AuditLogger: 审计日志器实例
    """
    global _audit_logger
    if _audit_logger is None:
        _audit_logger = AuditLogger()
    return _audit_logger
