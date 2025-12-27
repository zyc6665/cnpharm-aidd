# backend/app/services/email/__init__.py
"""邮件服务模块"""

from app.services.email.sender import EmailService
from app.services.email.templates import EmailTemplates

__all__ = [
    "EmailService",
    "EmailTemplates",
]
