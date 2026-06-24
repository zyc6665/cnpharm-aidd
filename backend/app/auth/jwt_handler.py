# backend/app/auth/jwt_handler.py
"""JWT Token管理"""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import uuid
from jose import jwt, JWTError
from app.common.time import utcnow
from app.config import settings


class JWTHandler:
    """JWT Token处理器"""

    def __init__(self):
        self.secret_key = settings.JWT_SECRET_KEY
        self.algorithm = settings.JWT_ALGORITHM
        self.access_token_expire_minutes = settings.ACCESS_TOKEN_EXPIRE_MINUTES
        self.refresh_token_expire_days = settings.REFRESH_TOKEN_EXPIRE_DAYS

    def create_access_token(
        self,
        user_id: str,
        email: str,
        role: str,
        extra_claims: Optional[Dict[str, Any]] = None
    ) -> str:
        """生成Access Token"""
        now = utcnow()
        expire = now + timedelta(minutes=self.access_token_expire_minutes)

        payload = {
            "sub": user_id,
            "email": email,
            "role": role,
            "exp": expire,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "type": "access"
        }

        if extra_claims:
            payload.update(extra_claims)

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def create_refresh_token(self, user_id: str) -> str:
        """生成Refresh Token"""
        now = utcnow()
        expire = now + timedelta(days=self.refresh_token_expire_days)

        payload = {
            "sub": user_id,
            "exp": expire,
            "iat": now,
            "jti": str(uuid.uuid4()),
            "type": "refresh"
        }

        return jwt.encode(payload, self.secret_key, algorithm=self.algorithm)

    def verify_token(self, token: str, token_type: str = "access") -> Dict[str, Any]:
        """验证Token"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm]
            )

            # 检查Token类型
            if payload.get("type") != token_type:
                raise JWTError("Invalid token type")

            return payload

        except JWTError as e:
            raise ValueError(f"Token验证失败: {str(e)}")

    def decode_token(self, token: str) -> Optional[Dict[str, Any]]:
        """解码Token（不验证过期）"""
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=[self.algorithm],
                options={"verify_exp": False}
            )
            return payload
        except JWTError:
            return None


# 全局实例
jwt_handler = JWTHandler()


def create_access_token(user_id: str, email: str, role: str) -> str:
    """创建Access Token的便捷函数"""
    return jwt_handler.create_access_token(user_id, email, role)


def create_refresh_token(user_id: str) -> str:
    """创建Refresh Token的便捷函数"""
    return jwt_handler.create_refresh_token(user_id)


def verify_token(token: str, token_type: str = "access") -> Dict[str, Any]:
    """验证Token的便捷函数"""
    return jwt_handler.verify_token(token, token_type)


def decode_token(token: str) -> Optional[Dict[str, Any]]:
    """解码Token的便捷函数（不验证过期）"""
    return jwt_handler.decode_token(token)
