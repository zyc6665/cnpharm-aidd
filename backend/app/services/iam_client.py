"""甲方统一身份认证（IAM）客户端。

对接《统一身份认证与管理系统-统一认证接口规范 v1》4.1「WEB 非网关模式」：

    authorize(浏览器)  ->  code  ->  getToken(服务端)  ->  getUserInfo(服务端)

本模块只负责**和对方说话**：拼地址、发请求、把对方的结果码翻译成异常。谁开户、
发什么 Cookie、登录页长什么样，都属于 ``app.api.v1.auth_sso`` 与前端的事情。

几条不写在签名里的规矩
----------------------
* **clientSecret 只出现在服务端之间的 POST body 里**。它绝不进 URL（会进对方与
  中间的访问日志）、不进日志、不进异常消息；日志里只记路径与结果码。
* **对方用 HTTP 200 承载业务失败**：成功码是字符串 ``"9001"``，失败码如 ``1005``
  （appId 非法）、``1014``（code 非法）、``2002``（accessToken 过期）。因此判断
  成功不能看状态码，必须看 body 里的 ``code``。
* **一次调用一个短连接**：``httpx.AsyncClient`` 在 ``async with`` 里建立和关闭。
  登录是低频操作，不值得为它维护全局连接池与生命周期；换来的是配置热改后立刻生效。
* **``redirctToUrl`` 是对方文档里的拼写**（少一个 ``e``），照抄。改成
  ``redirectToUrl`` 对方会当成缺少必填参数，返回 3002。
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field

from app.config import Settings, settings as global_settings

logger = logging.getLogger(__name__)

AUTHORIZE_PATH = "/auth/api/user/webungateway/authorize"
GET_TOKEN_PATH = "/auth/api/user/webungateway/getToken"
REFRESH_TOKEN_PATH = "/auth/api/user/webungateway/refreshToken"
GET_USER_INFO_PATH = "/auth/api/user/webungateway/getUserInfo"
CHECK_ACCESS_TOKEN_PATH = "/auth/api/user/webungateway/checkAccessToken"
GLO_PATH = "/auth/api/user/webungateway/GLO"

SUCCESS_CODE = "9001"

# 对方把它返回到 ``message`` 里，可能很长；截断后再落日志/异常，避免刷屏。
_MESSAGE_LIMIT = 200


class IamError(RuntimeError):
    """统一认证调用失败。

    ``code`` 是对方的结果码（``9001`` 以外的字符串）；网络层失败时为 ``None``，
    调用方据此区分「票据无效」（可以清会话）与「对方不可用」（不该清会话）。
    ``http_status`` 仅在 HTTP 层失败时存在。
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status

    @property
    def is_transport_error(self) -> bool:
        """是否连对方都没连上（超时/拒绝/DNS/证书）。"""
        return self.code is None


class IamToken(BaseModel):
    """``getToken`` / ``refreshToken`` 的 ``data`` 段。"""

    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int = 0
    uid: Optional[str] = None


class IamUser(BaseModel):
    """``getUserInfo`` 的 ``userInfo`` 段。

    只列出平台真正会用的字段；``orgs`` 保留原始结构（``unitCode``/``deptName``/
    ``jobName`` 等），因为不同应用申请到的字段不一样，平台不做强校验。
    """

    user_id: str
    user_name: Optional[str] = None
    fullname: Optional[str] = None
    employee_no: Optional[str] = None
    mobile: Optional[str] = None
    email: Optional[str] = None
    gender: Optional[str] = None
    change_password_must: Optional[bool] = None
    orgs: List[Dict[str, Any]] = Field(default_factory=list)

    def display_name(self) -> Optional[str]:
        """展示名优先级：中文姓名 -> userName -> 员工号。"""
        for candidate in (self.fullname, self.user_name, self.employee_no):
            if candidate and candidate.strip():
                return candidate.strip()
        return None


class IamClient:
    """统一认证客户端的全部出网动作。"""

    def __init__(
        self,
        config: Settings,
        *,
        transport: Optional[httpx.AsyncBaseTransport] = None,
    ) -> None:
        self.config = config
        # 测试注入 ``httpx.MockTransport``；生产保持 None，走真实网络。
        self._transport = transport

    # ------------------------------------------------------------------ URL
    def _url(self, path: str) -> str:
        return f"{self.config.SSO_BASE_URL.rstrip('/')}{path}"

    def build_authorize_url(self, state: str) -> str:
        """拼授权跳转地址，供浏览器 ``window.location.href`` 使用。

        ``urlencode`` 会把 ``redirectUri`` 的 ``:``、``/`` 一并百分号编码，这正是
        文档要求的「uri 编码」；对方按解码后的值匹配应用配置里的地址。
        """
        params = {
            "appId": self.config.SSO_APP_ID,
            "redirectUri": self.config.SSO_REDIRECT_URI,
            "responseType": "code",
            "state": state,
        }
        return f"{self._url(AUTHORIZE_PATH)}?{urlencode(params)}"

    def build_logout_url(self, redirect_to: str, *, redirect_to_login: bool = False) -> str:
        """拼统一认证注销（GLO）地址。

        注销后落在 ``redirect_to``（通常是平台的登录页）。``redirect_to_login=False``
        表示不要被对方再送回它的登录页——用户是我们主动登出的，不该立刻被要求
        重新登录；如果他随后点了「统一认证登录」，那时再跳授权接口。
        """
        params = {
            "redirctToUrl": redirect_to,
            "redirectToLogin": "true" if redirect_to_login else "false",
            "appId": self.config.SSO_APP_ID,
        }
        return f"{self._url(GLO_PATH)}?{urlencode(params)}"

    # -------------------------------------------------------------- 出网原语
    async def _post_form(self, path: str, data: Dict[str, str]) -> Dict[str, Any]:
        """POST 表单并返回解析后的 JSON（不校验 ``code``）。

        失败分三类：连不上（``IamError.code is None``）、HTTP 非 2xx（带
        ``http_status``）、body 不是 JSON。业务码交给调用方判断。
        """
        try:
            async with httpx.AsyncClient(
                timeout=self.config.SSO_TIMEOUT_SECONDS,
                verify=self.config.SSO_TLS_VALIDATE,
                transport=self._transport,
                follow_redirects=False,
                headers={"Accept": "application/json"},
            ) as client:
                response = await client.post(self._url(path), data=data)
        except httpx.HTTPError as exc:  # 超时 / 连接失败 / TLS 失败
            logger.warning(
                "统一认证请求失败 path=%s error=%s detail=%s",
                path,
                exc.__class__.__name__,
                str(exc)[:_MESSAGE_LIMIT],
            )
            raise IamError("统一身份认证服务不可用") from exc

        if response.status_code >= 400:
            logger.warning(
                "统一认证返回异常状态 path=%s status=%s", path, response.status_code
            )
            raise IamError(
                f"统一身份认证服务返回 {response.status_code}",
                http_status=response.status_code,
            )

        try:
            payload = response.json()
        except ValueError as exc:
            logger.warning("统一认证返回非 JSON path=%s", path)
            raise IamError("统一身份认证返回格式无法解析") from exc

        if not isinstance(payload, dict):
            raise IamError("统一身份认证返回格式无法解析")
        return payload

    @staticmethod
    def _ensure_success(payload: Dict[str, Any], path: str) -> None:
        code = payload.get("code")
        if str(code) == SUCCESS_CODE:
            return
        message = str(payload.get("message") or "统一认证调用失败")[:_MESSAGE_LIMIT]
        logger.warning("统一认证业务失败 path=%s code=%s message=%s", path, code, message)
        raise IamError(message, code=str(code) if code is not None else None)

    # ------------------------------------------------------------ 接口封装
    async def exchange_code(self, code: str) -> IamToken:
        """用一次性授权码换统一票据（``getToken``）。"""
        payload = await self._post_form(
            GET_TOKEN_PATH,
            {
                "appId": self.config.SSO_APP_ID,
                "clientSecret": self.config.SSO_CLIENT_SECRET,
                "code": code,
                "grantType": "authorization_code",
            },
        )
        self._ensure_success(payload, GET_TOKEN_PATH)

        data = payload.get("data") or {}
        access_token = data.get("accessToken")
        if not access_token:
            raise IamError("统一身份认证未返回 accessToken")
        return IamToken(
            access_token=str(access_token),
            refresh_token=data.get("refreshToken") or None,
            expires_in=_as_int(data.get("expiresIn")),
            uid=data.get("uid") or None,
        )

    async def refresh(self, refresh_token: str) -> IamToken:
        """续期统一票据。注意对方的 refreshToken 刷新一次即作废。"""
        payload = await self._post_form(
            REFRESH_TOKEN_PATH,
            {
                "appId": self.config.SSO_APP_ID,
                "clientSecret": self.config.SSO_CLIENT_SECRET,
                "refreshToken": refresh_token,
            },
        )
        self._ensure_success(payload, REFRESH_TOKEN_PATH)

        data = payload.get("data") or {}
        access_token = data.get("accessToken")
        if not access_token:
            raise IamError("统一身份认证未返回 accessToken")
        return IamToken(
            access_token=str(access_token),
            refresh_token=data.get("refreshToken") or refresh_token,
            expires_in=_as_int(data.get("expiresIn")),
            uid=data.get("uid") or None,
        )

    async def get_user_info(self, access_token: str) -> IamUser:
        """用统一票据取用户信息（``getUserInfo``）。"""
        payload = await self._post_form(
            GET_USER_INFO_PATH,
            {
                "appId": self.config.SSO_APP_ID,
                "accessToken": access_token,
            },
        )
        self._ensure_success(payload, GET_USER_INFO_PATH)

        raw = payload.get("userInfo") or {}
        user_id = raw.get("userId")
        if not user_id:
            raise IamError("统一身份认证未返回 userId")

        orgs = raw.get("orgs")
        return IamUser(
            user_id=str(user_id),
            user_name=_as_str(raw.get("userName")),
            fullname=_as_str(raw.get("fullname")),
            employee_no=_as_str(raw.get("employeeNo")),
            mobile=_as_str(raw.get("mobile")),
            email=_as_str(raw.get("email")),
            gender=_as_str(raw.get("gender")),
            change_password_must=_as_bool(raw.get("changePasswordMust")),
            orgs=orgs if isinstance(orgs, list) else [],
        )

    async def check_access_token(self, access_token: str) -> bool:
        """校验统一票据是否仍然有效。

        只有**对方明确回答票据无效**（业务码非 9001）才返回 False。网络异常会向上
        抛 ``IamError``：对方不可用时不能把用户踢下线，那是把自己变成了单点故障。
        """
        try:
            payload = await self._post_form(
                CHECK_ACCESS_TOKEN_PATH, {"accessToken": access_token}
            )
            self._ensure_success(payload, CHECK_ACCESS_TOKEN_PATH)
        except IamError as exc:
            if exc.is_transport_error or exc.http_status is not None:
                raise
            return False
        return True


def _as_str(value: Any) -> Optional[str]:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _as_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def _as_bool(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "1", "yes"}:
            return True
        if lowered in {"false", "0", "no"}:
            return False
    return None


def build_iam_client(config: Settings = global_settings) -> Optional[IamClient]:
    """按当前配置构造客户端；未启用或配置不全时返回 ``None``。"""
    if not config.SSO_ENABLED:
        return None
    if not (config.SSO_BASE_URL and config.SSO_APP_ID and config.SSO_CLIENT_SECRET):
        logger.warning("SSO_ENABLED=True 但统一认证配置不完整，单点登录不可用")
        return None
    return IamClient(config)


def get_iam_client() -> Optional[IamClient]:
    """FastAPI 依赖：返回当前配置下的客户端，``SSO_ENABLED=False`` 时返回 ``None``。

    与 ``get_ldap_authenticator`` 一致地暴露成依赖，测试里用
    ``app.dependency_overrides[get_iam_client]`` 注入假客户端。
    """
    return build_iam_client()
