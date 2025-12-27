# backend/app/services/email/templates.py
"""邮件模板"""

from app.config import settings


class EmailTemplates:
    """邮件模板管理"""

    @staticmethod
    def get_verification_code_html(
        code: str,
        purpose: str,
        expires_minutes: int
    ) -> str:
        """
        生成验证码邮件 HTML 内容

        Args:
            code: 验证码
            purpose: 用途 (register/reset_password)
            expires_minutes: 有效期（分钟）

        Returns:
            HTML 字符串
        """
        purpose_text = {
            "register": "注册账户",
            "reset_password": "重置密码"
        }.get(purpose, "验证")

        return f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>验证码</title>
</head>
<body style="margin: 0; padding: 0; font-family: 'Microsoft YaHei', 'Helvetica Neue', Arial, sans-serif; background-color: #f5f5f5;">
    <table role="presentation" style="width: 100%; border-collapse: collapse;">
        <tr>
            <td align="center" style="padding: 40px 0;">
                <table role="presentation" style="width: 600px; border-collapse: collapse; background-color: #ffffff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1);">
                    <!-- 头部 -->
                    <tr>
                        <td style="padding: 40px 40px 20px 40px; text-align: center; border-bottom: 1px solid #eee;">
                            <h1 style="margin: 0; color: #333; font-size: 24px; font-weight: 600;">
                                {settings.APP_NAME}
                            </h1>
                        </td>
                    </tr>

                    <!-- 内容 -->
                    <tr>
                        <td style="padding: 40px;">
                            <p style="margin: 0 0 20px 0; color: #666; font-size: 16px; line-height: 1.6;">
                                您好！
                            </p>
                            <p style="margin: 0 0 20px 0; color: #666; font-size: 16px; line-height: 1.6;">
                                您正在进行<strong style="color: #333;">{purpose_text}</strong>操作，请使用以下验证码完成验证：
                            </p>

                            <!-- 验证码 -->
                            <div style="text-align: center; margin: 30px 0;">
                                <div style="display: inline-block; padding: 20px 40px; background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); border-radius: 8px;">
                                    <span style="font-size: 36px; font-weight: bold; color: #ffffff; letter-spacing: 8px;">
                                        {code}
                                    </span>
                                </div>
                            </div>

                            <p style="margin: 20px 0 0 0; color: #999; font-size: 14px; line-height: 1.6;">
                                ⏰ 验证码有效期为 <strong>{expires_minutes} 分钟</strong>，请尽快使用。
                            </p>
                            <p style="margin: 10px 0 0 0; color: #999; font-size: 14px; line-height: 1.6;">
                                🔒 如果这不是您本人的操作，请忽略此邮件。
                            </p>
                        </td>
                    </tr>

                    <!-- 底部 -->
                    <tr>
                        <td style="padding: 20px 40px; background-color: #f9f9f9; border-top: 1px solid #eee; border-radius: 0 0 8px 8px;">
                            <p style="margin: 0; color: #999; font-size: 12px; text-align: center;">
                                此邮件由系统自动发送，请勿直接回复。
                            </p>
                            <p style="margin: 10px 0 0 0; color: #999; font-size: 12px; text-align: center;">
                                © {settings.APP_NAME}
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>
"""

    @staticmethod
    def get_verification_code_text(
        code: str,
        purpose: str,
        expires_minutes: int
    ) -> str:
        """
        生成验证码邮件纯文本内容

        Args:
            code: 验证码
            purpose: 用途
            expires_minutes: 有效期（分钟）

        Returns:
            纯文本字符串
        """
        purpose_text = {
            "register": "注册账户",
            "reset_password": "重置密码"
        }.get(purpose, "验证")

        return f"""
{settings.APP_NAME}

您好！

您正在进行"{purpose_text}"操作，请使用以下验证码完成验证：

验证码：{code}

验证码有效期为 {expires_minutes} 分钟，请尽快使用。

如果这不是您本人的操作，请忽略此邮件。

---
此邮件由系统自动发送，请勿直接回复。
"""

    @staticmethod
    def get_subject(purpose: str) -> str:
        """
        获取邮件主题

        Args:
            purpose: 用途

        Returns:
            邮件主题
        """
        subjects = {
            "register": f"【{settings.APP_NAME}】注册验证码",
            "reset_password": f"【{settings.APP_NAME}】密码重置验证码"
        }
        return subjects.get(purpose, f"【{settings.APP_NAME}】验证码")
