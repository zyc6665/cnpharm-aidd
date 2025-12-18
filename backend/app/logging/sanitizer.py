# backend/app/logging/sanitizer.py
"""日志脱敏模块

根据详细设计说明书 9.3 节实现。
负责对日志中的敏感信息进行脱敏处理。
"""

import logging
import re
from typing import Any, Dict, List, Pattern, Set, Union


class LogSanitizer:
    """日志脱敏器

    自动检测和脱敏日志中的敏感信息，包括：
    - 密码
    - API密钥
    - Token
    - 信用卡号
    - 身份证号
    - 手机号
    - 邮箱
    """

    # 敏感字段名（不区分大小写）
    SENSITIVE_FIELDS: Set[str] = {
        "password",
        "passwd",
        "pwd",
        "secret",
        "api_key",
        "apikey",
        "api_secret",
        "access_token",
        "refresh_token",
        "token",
        "authorization",
        "auth",
        "credential",
        "private_key",
        "privatekey",
        "secret_key",
        "secretkey",
        "session_id",
        "sessionid",
        "cookie",
        "credit_card",
        "creditcard",
        "card_number",
        "cardnumber",
        "cvv",
        "cvc",
        "ssn",
        "social_security",
        "id_card",
        "idcard",
        "identity",
    }

    # 敏感数据正则模式
    SENSITIVE_PATTERNS: List[tuple] = [
        # 信用卡号 (16位数字)
        (re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b"), "[CARD:***]"),
        # 邮箱
        (re.compile(r"\b[\w.+-]+@[\w.-]+\.\w{2,}\b"), "[EMAIL:***]"),
        # 手机号 (中国)
        (re.compile(r"\b1[3-9]\d{9}\b"), "[PHONE:***]"),
        # 身份证号 (中国)
        (re.compile(r"\b\d{17}[\dXx]\b"), "[ID:***]"),
        # JWT Token
        (re.compile(r"\beyJ[A-Za-z0-9_-]+\.eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\b"), "[JWT:***]"),
        # Bearer Token
        (re.compile(r"Bearer\s+[A-Za-z0-9_-]+"), "Bearer [TOKEN:***]"),
        # API Key (常见格式)
        (re.compile(r"\b[A-Za-z0-9]{32,64}\b"), None),  # None表示根据上下文判断
        # IP地址 (可选脱敏)
        # (re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"), "[IP:***]"),
    ]

    # 脱敏替换值
    MASK = "***"
    MASK_LONG = "******"

    def __init__(
        self,
        extra_fields: List[str] = None,
        extra_patterns: List[tuple] = None,
        mask_emails: bool = True,
        mask_phones: bool = True,
        mask_ips: bool = False
    ):
        """初始化脱敏器

        Args:
            extra_fields: 额外的敏感字段名
            extra_patterns: 额外的敏感模式
            mask_emails: 是否脱敏邮箱
            mask_phones: 是否脱敏手机号
            mask_ips: 是否脱敏IP地址
        """
        self.sensitive_fields = self.SENSITIVE_FIELDS.copy()
        if extra_fields:
            self.sensitive_fields.update(f.lower() for f in extra_fields)

        self.patterns = self.SENSITIVE_PATTERNS.copy()
        if extra_patterns:
            self.patterns.extend(extra_patterns)

        self.mask_emails = mask_emails
        self.mask_phones = mask_phones
        self.mask_ips = mask_ips

    def sanitize(self, data: Any) -> Any:
        """脱敏数据

        Args:
            data: 要脱敏的数据

        Returns:
            Any: 脱敏后的数据
        """
        if isinstance(data, str):
            return self._sanitize_string(data)
        elif isinstance(data, dict):
            return self._sanitize_dict(data)
        elif isinstance(data, (list, tuple)):
            return type(data)(self.sanitize(item) for item in data)
        else:
            return data

    def _sanitize_string(self, text: str) -> str:
        """脱敏字符串"""
        result = text

        for pattern, replacement in self.patterns:
            if replacement is None:
                continue  # 跳过需要上下文判断的模式

            result = pattern.sub(replacement, result)

        return result

    def _sanitize_dict(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """脱敏字典"""
        result = {}

        for key, value in data.items():
            lower_key = key.lower()

            # 检查是否为敏感字段
            if lower_key in self.sensitive_fields:
                if isinstance(value, str) and len(value) > 0:
                    # 保留部分信息用于调试
                    if len(value) > 4:
                        result[key] = value[:2] + self.MASK_LONG + value[-2:]
                    else:
                        result[key] = self.MASK
                else:
                    result[key] = self.MASK
            else:
                # 递归处理
                result[key] = self.sanitize(value)

        return result

    def is_sensitive_field(self, field_name: str) -> bool:
        """检查是否为敏感字段"""
        return field_name.lower() in self.sensitive_fields

    def mask_value(self, value: str, keep_prefix: int = 0, keep_suffix: int = 0) -> str:
        """脱敏值

        Args:
            value: 原始值
            keep_prefix: 保留前缀字符数
            keep_suffix: 保留后缀字符数

        Returns:
            str: 脱敏后的值
        """
        if not value:
            return self.MASK

        length = len(value)
        if length <= keep_prefix + keep_suffix:
            return self.MASK

        prefix = value[:keep_prefix] if keep_prefix > 0 else ""
        suffix = value[-keep_suffix:] if keep_suffix > 0 else ""
        mask_length = length - keep_prefix - keep_suffix

        return prefix + "*" * min(mask_length, 8) + suffix

    def mask_email(self, email: str) -> str:
        """脱敏邮箱"""
        if "@" not in email:
            return self.MASK

        local, domain = email.rsplit("@", 1)
        if len(local) <= 2:
            masked_local = self.MASK
        else:
            masked_local = local[0] + "***" + local[-1]

        return f"{masked_local}@{domain}"

    def mask_phone(self, phone: str) -> str:
        """脱敏手机号"""
        digits = re.sub(r"\D", "", phone)
        if len(digits) < 7:
            return self.MASK

        return digits[:3] + "****" + digits[-4:]


class SanitizingFilter(logging.Filter):
    """日志脱敏过滤器

    自动对日志记录中的敏感信息进行脱敏。
    """

    def __init__(self, sanitizer: LogSanitizer = None, name: str = ""):
        super().__init__(name)
        self.sanitizer = sanitizer or LogSanitizer()

    def filter(self, record: logging.LogRecord) -> bool:
        """过滤并脱敏日志记录"""
        # 脱敏消息
        if isinstance(record.msg, str):
            record.msg = self.sanitizer._sanitize_string(record.msg)

        # 脱敏参数
        if record.args:
            if isinstance(record.args, dict):
                record.args = self.sanitizer._sanitize_dict(record.args)
            elif isinstance(record.args, tuple):
                record.args = tuple(
                    self.sanitizer.sanitize(arg) for arg in record.args
                )

        # 脱敏额外字段
        for key in list(record.__dict__.keys()):
            if key.startswith("_"):
                continue
            if self.sanitizer.is_sensitive_field(key):
                value = getattr(record, key, None)
                if value is not None:
                    setattr(record, key, self.sanitizer.mask_value(str(value)))

        return True


def create_sanitizing_handler(
    handler: logging.Handler,
    extra_fields: List[str] = None
) -> logging.Handler:
    """创建带脱敏功能的处理器

    Args:
        handler: 原始处理器
        extra_fields: 额外的敏感字段

    Returns:
        logging.Handler: 带脱敏功能的处理器
    """
    sanitizer = LogSanitizer(extra_fields=extra_fields)
    handler.addFilter(SanitizingFilter(sanitizer))
    return handler
