# backend/app/services/email/sender.py
"""邮件发送服务"""

import logging
from typing import Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import aiosmtplib

from app.config import settings
from app.services.email.templates import EmailTemplates

logger = logging.getLogger(__name__)


class EmailService:
    """
    邮件发送服务

    使用 aiosmtplib 异步发送邮件。
    """

    def __init__(
        self,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        from_email: Optional[str] = None,
        from_name: Optional[str] = None,
        use_tls: Optional[bool] = None
    ):
        """
        初始化邮件服务

        Args:
            host: SMTP 服务器地址
            port: SMTP 端口
            username: SMTP 用户名
            password: SMTP 密码
            from_email: 发件人邮箱
            from_name: 发件人名称
            use_tls: 是否使用 TLS
        """
        self.host = host or settings.SMTP_HOST
        self.port = port or settings.SMTP_PORT
        self.username = username or settings.SMTP_USER
        self.password = password or settings.SMTP_PASSWORD
        self.from_email = from_email or settings.SMTP_FROM_EMAIL
        self.from_name = from_name or settings.SMTP_FROM_NAME
        self.use_tls = use_tls if use_tls is not None else settings.SMTP_USE_TLS

    def _is_configured(self) -> bool:
        """检查 SMTP 是否已配置"""
        return bool(
            self.host and
            self.host != "smtp.example.com" and
            self.username and
            self.password and
            self.from_email
        )

    async def send_email(
        self,
        to: str,
        subject: str,
        text_body: str,
        html_body: Optional[str] = None
    ) -> bool:
        """
        发送邮件

        Args:
            to: 收件人邮箱
            subject: 邮件主题
            text_body: 纯文本内容
            html_body: HTML 内容（可选）

        Returns:
            是否发送成功
        """
        if not self._is_configured():
            logger.warning(
                f"SMTP 未配置，验证码将仅记录到日志。"
                f"收件人: {to}, 主题: {subject}"
            )
            logger.info(f"邮件内容:\n{text_body}")
            return True  # 返回成功，允许开发环境继续运行

        try:
            # 创建邮件
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = f"{self.from_name} <{self.from_email}>"
            message["To"] = to

            # 添加纯文本内容
            text_part = MIMEText(text_body, "plain", "utf-8")
            message.attach(text_part)

            # 添加 HTML 内容（如果有）
            if html_body:
                html_part = MIMEText(html_body, "html", "utf-8")
                message.attach(html_part)

            # 发送邮件
            # QQ邮箱 465 端口需要使用 SSL，587 端口使用 STARTTLS
            if self.port == 465:
                await aiosmtplib.send(
                    message,
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    use_tls=True  # 465 端口使用直接 SSL 连接
                )
            else:
                await aiosmtplib.send(
                    message,
                    hostname=self.host,
                    port=self.port,
                    username=self.username,
                    password=self.password,
                    start_tls=self.use_tls  # 587 端口使用 STARTTLS
                )

            logger.info(f"邮件发送成功: {to}")
            return True

        except aiosmtplib.SMTPException as e:
            logger.error(f"SMTP 错误: {e}")
            return False
        except Exception as e:
            logger.error(f"邮件发送失败: {e}")
            return False

    async def send_verification_code(
        self,
        email: str,
        code: str,
        purpose: str
    ) -> bool:
        """
        发送验证码邮件

        Args:
            email: 收件人邮箱
            code: 验证码
            purpose: 用途 (register/reset_password)

        Returns:
            是否发送成功
        """
        expires_minutes = settings.VERIFICATION_CODE_EXPIRE_MINUTES

        subject = EmailTemplates.get_subject(purpose)
        text_body = EmailTemplates.get_verification_code_text(
            code, purpose, expires_minutes
        )
        html_body = EmailTemplates.get_verification_code_html(
            code, purpose, expires_minutes
        )

        return await self.send_email(
            to=email,
            subject=subject,
            text_body=text_body,
            html_body=html_body
        )


# 全局单例
_email_service: Optional[EmailService] = None


def get_email_service() -> EmailService:
    """获取邮件服务单例"""
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service
