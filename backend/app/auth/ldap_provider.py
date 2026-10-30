# backend/app/auth/ldap_provider.py
"""企业内网 LDAP 认证适配器。

设计见 ``docs/superpowers/specs/2026-10-30-enterprise-ldap-auth-design.md`` §6.2/6.3：

* 登录标识是 username，认证源由 ``User.auth_source`` 决定；
* LDAP 用户不保存本地口令（``password_hash`` 为 None），每次登录都回目录校验；
* 先以服务账号（若配置）在 ``LDAP_BASE_DN`` 下按 ``LDAP_USER_FILTER`` 搜唯一条目，
  再以该条目 DN + 用户口令做一次 bind 验证；
* 任何异常（连接失败/超时/多条/无条目/口令为空）都返回 ``None`` 并 WARNING，
  **绝不记录用户口令**。

``ldap3`` 的 import 放在方法内部：未启用 LDAP 或未安装该库时，模块本身仍可安全导入。
"""

from __future__ import annotations

import logging
from typing import List, Optional, Protocol, runtime_checkable

from pydantic import BaseModel

from app.config import Settings, settings as global_settings

logger = logging.getLogger(__name__)


class LdapAuthResult(BaseModel):
    """一次成功的 LDAP 校验结果。"""

    dn: str
    username: str
    email: Optional[str] = None
    display_name: Optional[str] = None


@runtime_checkable
class LdapAuthenticator(Protocol):
    """LDAP 认证器协议；测试可用内存 Fake 覆盖此依赖。"""

    def authenticate(self, username: str, password: str) -> Optional[LdapAuthResult]:
        ...


class Ldap3Authenticator:
    """基于 ``ldap3`` 的实现。"""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    # --------------------------- ldap3 延迟导入 --------------------------- #
    @staticmethod
    def _ldap3():
        from ldap3 import Connection, Server, SUBTREE, Tls
        from ldap3.utils.conv import escape_filter_chars

        return Connection, Server, SUBTREE, Tls, escape_filter_chars

    def _build_server(self, Server, Tls):
        s = self.settings
        need_tls = (
            s.LDAP_START_TLS
            or s.LDAP_SERVER_URI.lower().startswith("ldaps://")
            or bool(s.LDAP_CA_CERT_FILE)
            or not s.LDAP_TLS_VALIDATE
        )
        tls = None
        if need_tls:
            tls = Tls(
                ca_certs_file=s.LDAP_CA_CERT_FILE or None,
                validate=s.LDAP_TLS_VALIDATE,
            )
        return Server(
            s.LDAP_SERVER_URI,
            use_ssl=s.LDAP_SERVER_URI.lower().startswith("ldaps://"),
            connect_timeout=s.LDAP_TIMEOUT_SECONDS,
            tls=tls,
            get_info=None,
        )

    def _open_and_bind(self, Connection, server, user: Optional[str], password: Optional[str]):
        """打开连接并 bind；失败返回 None（不抛出、不记录口令）。"""
        s = self.settings
        conn = Connection(
            server,
            user=user,
            password=password,
            auto_bind=False,
            receive_timeout=s.LDAP_TIMEOUT_SECONDS,
            read_only=True,
            raise_exceptions=False,
        )
        try:
            conn.open()
            if s.LDAP_START_TLS and not conn.start_tls():
                conn.unbind()
                return None
            if not conn.bind():
                conn.unbind()
                return None
            return conn
        except Exception:
            try:
                conn.unbind()
            except Exception:
                pass
            return None

    @staticmethod
    def _entry_attribute(entry, name: str) -> Optional[str]:
        try:
            attribute = entry[name]
        except Exception:
            return None
        value = getattr(attribute, "value", attribute)
        if isinstance(value, (list, tuple)):
            value = value[0] if value else None
        if value is None:
            return None
        return str(value)

    def authenticate(self, username: str, password: str) -> Optional[LdapAuthResult]:
        s = self.settings
        if not username or not password:
            logger.warning("LDAP 认证拒绝：用户名或口令为空 username=%r", username)
            return None

        try:
            Connection, Server, SUBTREE, Tls, escape_filter_chars = self._ldap3()
        except Exception as exc:  # pragma: no cover - 依赖缺失时的防御
            logger.warning("LDAP 依赖不可用：%s", exc.__class__.__name__)
            return None

        try:
            server = self._build_server(Server, Tls)
            bind_dn = s.LDAP_BIND_DN or None
            bind_password = s.LDAP_BIND_PASSWORD or None

            service = self._open_and_bind(Connection, server, bind_dn, bind_password)
            if service is None:
                logger.warning("LDAP 服务账号 bind 失败，无法检索用户 username=%r", username)
                return None

            try:
                search_filter = s.LDAP_USER_FILTER.format(
                    username=escape_filter_chars(username)
                )
                found = service.search(
                    search_base=s.LDAP_BASE_DN,
                    search_filter=search_filter,
                    search_scope=SUBTREE,
                    attributes=[
                        s.LDAP_ATTR_UID,
                        s.LDAP_ATTR_MAIL,
                        s.LDAP_ATTR_DISPLAY_NAME,
                    ],
                    size_limit=2,
                )
                entries: List = list(getattr(service, "entries", []) or [])
            finally:
                try:
                    service.unbind()
                except Exception:
                    pass

            if not found or len(entries) != 1:
                logger.warning(
                    "LDAP 用户检索异常：期望唯一结果，实际 %d 条 username=%r",
                    len(entries),
                    username,
                )
                return None

            entry = entries[0]
            entry_dn = getattr(entry, "entry_dn", None)
            if not entry_dn:
                logger.warning("LDAP 条目缺少 DN username=%r", username)
                return None

            email = self._entry_attribute(entry, s.LDAP_ATTR_MAIL)
            display_name = self._entry_attribute(entry, s.LDAP_ATTR_DISPLAY_NAME)

            user_conn = self._open_and_bind(Connection, server, entry_dn, password)
            if user_conn is None:
                logger.warning("LDAP 用户口令校验失败 username=%r", username)
                return None
            try:
                user_conn.unbind()
            except Exception:
                pass

            return LdapAuthResult(
                dn=entry_dn,
                username=username,
                email=email,
                display_name=display_name,
            )
        except Exception as exc:
            # 只记录异常类型，绝不把 password 写进日志。
            logger.warning(
                "LDAP 认证异常 username=%r error=%s", username, exc.__class__.__name__
            )
            return None


def get_ldap_authenticator() -> Optional[LdapAuthenticator]:
    """返回当前配置下的 LDAP 认证器；``LDAP_ENABLED=False`` 时返回 None。

    作为 FastAPI 依赖暴露，便于测试通过 ``app.dependency_overrides`` 注入 Fake。
    """
    if not global_settings.LDAP_ENABLED:
        return None
    if not global_settings.LDAP_SERVER_URI:
        logger.warning("LDAP_ENABLED=True 但未配置 LDAP_SERVER_URI，LDAP 登录将失败")
        return None
    return Ldap3Authenticator(global_settings)
