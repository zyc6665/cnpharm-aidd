# backend/app/logging/categorized.py
"""分类日志记录器

提供按类别分类的日志记录功能，支持：
- 访问日志
- 审计日志
- 错误日志
"""

from datetime import datetime
from typing import Any, Dict, Optional
import logging


class CategorizedLogger:
    """分类日志记录器

    提供结构化的日志记录方法，便于日志分析和审计。
    """

    def __init__(self, name: str = "sciminer"):
        """初始化分类日志器

        Args:
            name: 日志器名称
        """
        self.access_logger = logging.getLogger(f"{name}.access")
        self.audit_logger = logging.getLogger(f"{name}.audit")
        self.error_logger = logging.getLogger(f"{name}.error")
        self.security_logger = logging.getLogger(f"{name}.security")

    def log_access(
        self,
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        user_agent: Optional[str] = None,
        request_id: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录访问日志

        Args:
            method: HTTP方法
            path: 请求路径
            status_code: 响应状态码
            duration_ms: 请求时长（毫秒）
            user_id: 用户ID
            client_ip: 客户端IP
            user_agent: User-Agent
            request_id: 请求ID
            extra: 额外信息
        """
        log_data = {
            "category": "access",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": duration_ms,
            "user_id": user_id,
            "client_ip": client_ip,
            "user_agent": user_agent[:100] if user_agent else None,
            "request_id": request_id,
            "timestamp": datetime.utcnow().isoformat()
        }

        if extra:
            log_data.update(extra)

        # 根据状态码选择日志级别
        if status_code >= 500:
            self.access_logger.error(
                f"{method} {path} {status_code} {duration_ms:.2f}ms",
                extra=log_data
            )
        elif status_code >= 400:
            self.access_logger.warning(
                f"{method} {path} {status_code} {duration_ms:.2f}ms",
                extra=log_data
            )
        else:
            self.access_logger.info(
                f"{method} {path} {status_code} {duration_ms:.2f}ms",
                extra=log_data
            )

    def log_audit(
        self,
        action: str,
        resource_type: str,
        resource_id: str,
        user_id: str,
        changes: Optional[Dict[str, Any]] = None,
        result: str = "success",
        reason: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录审计日志

        Args:
            action: 操作类型（create, update, delete, read）
            resource_type: 资源类型
            resource_id: 资源ID
            user_id: 操作用户ID
            changes: 变更内容
            result: 操作结果（success, failure）
            reason: 失败原因
            extra: 额外信息
        """
        log_data = {
            "category": "audit",
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "user_id": user_id,
            "changes": changes,
            "result": result,
            "reason": reason,
            "timestamp": datetime.utcnow().isoformat()
        }

        if extra:
            log_data.update(extra)

        message = f"AUDIT: {action} {resource_type}/{resource_id} by {user_id} - {result}"

        if result == "success":
            self.audit_logger.info(message, extra=log_data)
        else:
            self.audit_logger.warning(message, extra=log_data)

    def log_error(
        self,
        error_type: str,
        message: str,
        stack_trace: Optional[str] = None,
        user_id: Optional[str] = None,
        request_id: Optional[str] = None,
        context: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录错误日志

        Args:
            error_type: 错误类型
            message: 错误消息
            stack_trace: 堆栈跟踪
            user_id: 用户ID
            request_id: 请求ID
            context: 上下文信息
            extra: 额外信息
        """
        log_data = {
            "category": "error",
            "error_type": error_type,
            "user_id": user_id,
            "request_id": request_id,
            "context": context,
            "stack_trace": stack_trace,
            "timestamp": datetime.utcnow().isoformat()
        }

        if extra:
            log_data.update(extra)

        self.error_logger.error(
            f"ERROR [{error_type}]: {message}",
            extra=log_data,
            exc_info=stack_trace is None  # 如果没有提供堆栈，自动捕获
        )

    def log_security(
        self,
        event: str,
        severity: str,
        user_id: Optional[str] = None,
        client_ip: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录安全日志

        Args:
            event: 安全事件类型
            severity: 严重程度（low, medium, high, critical）
            user_id: 用户ID
            client_ip: 客户端IP
            details: 详细信息
            extra: 额外信息
        """
        log_data = {
            "category": "security",
            "event": event,
            "severity": severity,
            "user_id": user_id,
            "client_ip": client_ip,
            "details": details,
            "timestamp": datetime.utcnow().isoformat()
        }

        if extra:
            log_data.update(extra)

        message = f"SECURITY [{severity.upper()}]: {event}"

        if severity in ("high", "critical"):
            self.security_logger.error(message, extra=log_data)
        elif severity == "medium":
            self.security_logger.warning(message, extra=log_data)
        else:
            self.security_logger.info(message, extra=log_data)

    def log_user_action(
        self,
        action: str,
        user_id: str,
        target: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录用户操作"""
        self.log_audit(
            action=action,
            resource_type="user_action",
            resource_id=target or "N/A",
            user_id=user_id,
            changes=details
        )

    def log_data_access(
        self,
        resource_type: str,
        resource_id: str,
        user_id: str,
        access_type: str = "read"
    ) -> None:
        """记录数据访问"""
        self.log_audit(
            action=access_type,
            resource_type=resource_type,
            resource_id=resource_id,
            user_id=user_id
        )

    def log_admin_operation(
        self,
        operation: str,
        admin_id: str,
        target_type: str,
        target_id: str,
        changes: Optional[Dict[str, Any]] = None
    ) -> None:
        """记录管理员操作"""
        self.log_audit(
            action=f"admin:{operation}",
            resource_type=target_type,
            resource_id=target_id,
            user_id=admin_id,
            changes=changes
        )


# 全局日志器实例
_categorized_logger: Optional[CategorizedLogger] = None


def get_logger(name: str = "sciminer") -> CategorizedLogger:
    """获取分类日志器

    Args:
        name: 日志器名称

    Returns:
        CategorizedLogger: 分类日志器
    """
    global _categorized_logger
    if _categorized_logger is None:
        _categorized_logger = CategorizedLogger(name)
    return _categorized_logger


# 便捷函数
def log_access(**kwargs) -> None:
    """记录访问日志"""
    get_logger().log_access(**kwargs)


def log_audit(**kwargs) -> None:
    """记录审计日志"""
    get_logger().log_audit(**kwargs)


def log_error(**kwargs) -> None:
    """记录错误日志"""
    get_logger().log_error(**kwargs)


def log_security(**kwargs) -> None:
    """记录安全日志"""
    get_logger().log_security(**kwargs)
