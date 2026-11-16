"""甲方统一身份认证（IAM）客户端。

对接《统一身份认证与管理系统-统一认证接口规范 v1》4.1「WEB 非网关模式」：

    authorize(浏览器)  ->  code  ->  getToken(服务端)  ->  getUserInfo(服务端)

本模块只负责**和对方说话**：拼地址、发请求、把对方的结果码翻译成异常。谁开户、
发什么 Cookie、登录页长什么样，都属于 ``app.api.v1.auth_sso`` 与前端的事情。

几条不写在签名里的规矩
----------------------
* **clientSecret 只出现在服务端之间的 POST body 里**。它绝不进 URL（会进对方与
  中间的访问日志）、不进日志、不进异常消息；日志里只记路径与结果码。
* **对方的 ``message`` 是不可信外部文本**：进 logger、异常消息或响应之前，一律先走
  ``_safe_snippet(..., secrets=_request_secrets(data))``——控制字符转义、按本次请求
  的密钥脱敏、截断到 ``_MESSAGE_LIMIT``。异常里只保留这一段脱敏片段，绝不保留原文。
* **对方用 HTTP 200 承载业务失败**：成功码是字符串 ``"9001"``。业务码的含义只有
  四类（真源是下面的 ``IAM_RESULT_CODES``，判定顺序见
  ``iam_session._classify_iam_error``）：``2002``/``1025``/``1014`` 是票据失效
  （判死）；``1001``/``1005``/``1008``/``1009``/``1010``/``1012``/``1024``/
  ``2001``/``2006`` 是我方请求或配置错误（记 ERROR，按不可用处理：走宽限、
  不续期）；``3002`` 只属于 GLO、不参与在线会话判定；``9001`` 是成功；表外码只在
  HTTP 200 上 fail-closed 判死。
* **状态码能压过业务码**：HTTP 5xx/408/429 一律按不可用处理——``500 + {"code":
  "1025"}`` 也走宽限，不判死；只有 HTTP 4xx 才按状态码分流，此时表内码优先
  （``400 + {"code":"1025"}`` 判死）。别把「表内码优先于状态码」当成无条件规则。
* **一次调用一个短连接**：``httpx.AsyncClient`` 在 ``async with`` 里建立和关闭。
  登录是低频操作，不值得为它维护全局连接池与生命周期；换来的是配置热改后立刻生效。
* **``redirctToUrl`` 是对方文档里的拼写**（少一个 ``e``），照抄。改成
  ``redirectToUrl`` 对方会当成缺少必填参数，返回 3002。
"""

from __future__ import annotations

import logging
import re
from enum import Enum
from types import MappingProxyType
from typing import Any, Dict, List, Mapping, NamedTuple, Optional
from urllib.parse import urlencode

import httpx
from pydantic import BaseModel, Field, ValidationError

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

#: 4xx/5xx 响应体只在这个字节数内才解析并记片段。再大就不是业务码，而是网关/代理
#: 的 HTML 错误页：解析它只会拖慢故障现场，且可能把整页塞进日志。
_ERROR_BODY_LIMIT = 4096

#: 日志里不留换行/控制字符（口径同 ``auth_sso._log_safe``，防止对方用 message
#: 拼出假日志行）。
_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")

#: 会参与「这名用户的会话还能不能继续」判定的接口。``GLO`` 是注销专用，不在其中：
#: 只出现在注销接口的结果码不能拿来结束在线会话。
_SESSION_ENDPOINTS = frozenset(
    {GET_TOKEN_PATH, REFRESH_TOKEN_PATH, GET_USER_INFO_PATH, CHECK_ACCESS_TOKEN_PATH}
)


class IamResultCategory(str, Enum):
    """结果码在**会话判定**里的归属。

    只有四类，且刻意不提供 ``logout_only``：``3002`` 这类「已知但与会话无关」的码
    统一放进 ``OTHER``，由判定方按「接口集合是否与会话接口相交」处理，避免分类值
    跟着接口数一起膨胀。
    """

    #: 票据本身失效：可以结束平台会话，要求重新登录。
    TICKET_INVALID = "ticket_invalid"
    #: 我方请求/配置错误（缺参、参数非法）：记 ERROR、按不可用处理（走宽限、
    #: 不续期）；与用户票据无关，绝不能判死。
    REQUEST_INVALID = "request_invalid"
    #: 规范里的成功码（``9001``）。
    SUCCESS = "success"
    #: 已知、但与会话无关的码（当前只有 ``3002``，GLO 专用）。
    OTHER = "other"


class IamResultCode(NamedTuple):
    """结果码表的一行：语义、分类、规范出处、适用接口。"""

    #: 规范原文的语义描述，逐字照抄，便于和甲方文本对照。
    semantics: str
    category: IamResultCategory
    #: 规范章节号（《统一认证接口规范 v1》4.1.x.y），新增码必须能指到原文。
    spec_ref: str
    #: 该码可能出现的接口路径集合；用于判断「这个码是否与会话有关」。
    endpoints: frozenset[str]


#: 甲方结果码的**唯一真源**（规范 v1 §4.1.3 ~ §4.1.7）。
#:
#: 收录口径：规范正文里明确列出的码，一个不多一个不少。特别地：
#:
#: * 旧代码曾把两个不在规范里的码当作系统错误码（其中一个其实只是示例 ``userId``
#:   的子串，被误读成了错误码）。它们已从码表删除，遇到时按「表外未知码」处理；
#:   本模块与会话模块里不再出现这两个字面量，回归断言见
#:   ``test/test_iam_result_codes.py``。
#: * ``1012``（client_secret 非法）与 ``1014``（code 非法）都在 getToken 上返回，
#:   但归类相反：``1012`` 是我方配置错误 → ``request_invalid``（不可用、不判死）；
#:   ``1014`` 说明这张一次性授权码已经不能再用 → ``ticket_invalid``（判死）。
#:   ``1025`` 是 refreshToken 的票据失效码。三者不能凭码段相近就归成一类。
IAM_RESULT_CODES: Mapping[str, IamResultCode] = MappingProxyType(
    {
        "1001": IamResultCode(
            "缺少参数 client_id",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.1",
            frozenset({GET_TOKEN_PATH, REFRESH_TOKEN_PATH, GET_USER_INFO_PATH}),
        ),
        "1005": IamResultCode(
            "参数 client_id 非法",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.5",
            frozenset({GET_TOKEN_PATH, REFRESH_TOKEN_PATH, GET_USER_INFO_PATH}),
        ),
        "1008": IamResultCode(
            "缺少参数 client_secret",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.4",
            frozenset({GET_TOKEN_PATH, REFRESH_TOKEN_PATH}),
        ),
        "1009": IamResultCode(
            "缺少参数 code",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.2",
            frozenset({GET_TOKEN_PATH}),
        ),
        "1010": IamResultCode(
            "缺少参数 grant_type",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.3",
            frozenset({GET_TOKEN_PATH}),
        ),
        "1012": IamResultCode(
            "参数 client_secret 非法",
            IamResultCategory.REQUEST_INVALID,
            "4.1.3.7",
            frozenset({GET_TOKEN_PATH}),
        ),
        "1014": IamResultCode(
            "参数 code 非法",
            IamResultCategory.TICKET_INVALID,
            "4.1.3.6",
            frozenset({GET_TOKEN_PATH}),
        ),
        "1024": IamResultCode(
            "缺少参数 refresh_token，值不能为空",
            IamResultCategory.REQUEST_INVALID,
            "4.1.4.2",
            frozenset({REFRESH_TOKEN_PATH}),
        ),
        "1025": IamResultCode(
            "参数 refresh_token 不正确或过期",
            IamResultCategory.TICKET_INVALID,
            "4.1.4.5",
            frozenset({REFRESH_TOKEN_PATH}),
        ),
        "2001": IamResultCode(
            "缺少参数 access_token",
            IamResultCategory.REQUEST_INVALID,
            "4.1.5.2",
            frozenset({GET_USER_INFO_PATH, CHECK_ACCESS_TOKEN_PATH}),
        ),
        "2002": IamResultCode(
            "参数 access_token 不正确或过期",
            IamResultCategory.TICKET_INVALID,
            "4.1.5.5",
            frozenset({GET_USER_INFO_PATH, CHECK_ACCESS_TOKEN_PATH}),
        ),
        "2006": IamResultCode(
            "缺少参数 uid",
            IamResultCategory.REQUEST_INVALID,
            "4.1.5.3",
            frozenset({GET_USER_INFO_PATH}),
        ),
        "3002": IamResultCode(
            # GLO 专用：注销地址缺 url 参数。永远不参与在线会话判定。
            "缺少参数 url",
            IamResultCategory.OTHER,
            "4.1.7.2",
            frozenset({GLO_PATH}),
        ),
        "9001": IamResultCode(
            "成功",
            IamResultCategory.SUCCESS,
            "4.1.3.8",
            _SESSION_ENDPOINTS | frozenset({GLO_PATH}),
        ),
    }
)


def codes_of_category(category: IamResultCategory) -> frozenset[str]:
    """返回某一分类下的全部结果码（顺序无关，供会话模块派生集合使用）。"""
    return frozenset(
        code for code, row in IAM_RESULT_CODES.items() if row.category is category
    )


def iam_result_category(code: object) -> Optional[IamResultCategory]:
    """把对方的结果码（``str``/``int``，可能带空白）翻译成分类；表外码返回 ``None``。

    故意不把 ``bool`` 当码：``True`` 的 ``str()`` 是 ``"True"``，与 ``"1"`` 不是
    一回事，传进来只可能是调用方写错了参数，按「未知」处理更安全。
    """
    if code is None or isinstance(code, bool):
        return None
    if isinstance(code, (dict, list)):
        return None
    row = IAM_RESULT_CODES.get(str(code).strip())
    return row.category if row is not None else None


class IamError(RuntimeError):
    """统一认证调用失败。

    两个正交的轴，调用方需要分开看：

    * ``code``：对方的结果码（``9001`` 以外的字符串）。4xx/5xx 响应体里若能解析出
      业务码，同样会带上来，此时 ``http_status`` 与 ``code`` **同时**存在——甲方
      完全可能用 ``400 + {"code":"1025"}`` 表达 refreshToken 失效，只看状态码会把
      「票据已死」误判成「对方不可用」。
    * ``malformed``：拿到了 200 与可解析的 JSON，但字段结构不合规（例如 ``userInfo``
      不是对象、``orgs`` 元素不是对象）。它不是网络故障，重试没有意义；之所以不
      直接判死，是因为上层要按「没拿到可信答复」走宽限而不是清会话。

    ``is_transport_error`` 表示**根本没拿到可信答复**（``code is None`` 且不是
    ``malformed``）：超时/拒绝/DNS/证书/响应不是 JSON 都属于这一类。
    """

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        http_status: Optional[int] = None,
        malformed: bool = False,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.http_status = http_status
        self.malformed = malformed

    @property
    def is_transport_error(self) -> bool:
        """是否连对方都没连上（超时/拒绝/DNS/证书），或响应整体不可解析。"""
        return self.code is None and not self.malformed


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

        失败分三类：连不上（``IamError.code is None``、无状态码）、HTTP 非 2xx
        （带 ``http_status``；响应体里能解析出业务码时**同时**带 ``code``）、body
        不是 JSON。业务码的分类交给调用方判断。

        ``data`` 里的敏感值（clientSecret、两种票据与一次性 ``code``）只用于给响应
        片段脱敏：``message`` 是外部文本，可能把请求参数原样回显。
        """
        # 本次请求里不能落日志/进异常的明文，整个方法共用这一份。
        secrets = _request_secrets(data)
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
                _safe_snippet(str(exc), secrets=secrets, limit=_MESSAGE_LIMIT),
            )
            raise IamError("统一身份认证服务不可用") from exc

        if response.status_code >= 400:
            status = response.status_code
            content_type = _safe_snippet(
                str(response.headers.get("content-type") or "-"), limit=80
            )
            body_bytes = len(response.content)
            code: Optional[str] = None
            message: Optional[str] = None
            if body_bytes > _ERROR_BODY_LIMIT:
                # 超过上限多半是网关/代理的 HTML 错误页，不解析、不落片段。
                logger.warning(
                    "统一认证返回异常状态 path=%s status=%s code=None "
                    "content_type=%s body_bytes=%s",
                    path,
                    status,
                    content_type,
                    body_bytes,
                )
            else:
                # 4xx 上业务码优先于状态码：甲方可能用 400 + {"code":"1025"} 表达票据失效。
                # 5xx/408/429 不适用这条——会话层先按不可用处理，业务码不参与判定。
                # content-type 不作为门槛——4xx 上它经常缺失或被网关改写。
                code, message = _error_body_identity(response, secrets=secrets)
                logger.warning(
                    "统一认证返回异常状态 path=%s status=%s code=%s "
                    "content_type=%s snippet=%s",
                    path,
                    status,
                    code,
                    content_type,
                    _safe_snippet(response.text, secrets=secrets),
                )
            raise IamError(
                message or f"统一身份认证服务返回 {status}",
                code=code,
                http_status=status,
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
    def _ensure_success(
        payload: Dict[str, Any],
        path: str,
        *,
        secrets: tuple[str, ...],
    ) -> None:
        """校验业务码；失败时把``message``同时写进日志与异常。

        ``message`` 来自甲方，是外部不可信文本：必须先按 ``secrets``（本次请求的
        clientSecret / 票据 / 一次性 code）脱敏、转义控制字符并截断到
        ``_MESSAGE_LIMIT``，再落 logger 与 ``IamError``——否则 ``str(exc)`` 会把对方
        回显的 clientSecret 带出去，而日志未必拦得住上层。

        ``secrets`` 故意不给默认值：上一版就是「调用点漏传 → 默认空元组 → 不脱敏」，
        让漏传在调用点直接 ``TypeError`` 比让它静默泄漏要好。
        """
        code = payload.get("code")
        if str(code) == SUCCESS_CODE:
            return
        raw = payload.get("message")
        message = _safe_snippet(
            str(raw).strip() if raw is not None else "",
            secrets=secrets,
            limit=_MESSAGE_LIMIT,
        ) or "统一认证调用失败"
        logger.warning("统一认证业务失败 path=%s code=%s message=%s", path, code, message)
        raise IamError(message, code=str(code) if code is not None else None)

    # ------------------------------------------------------------ 接口封装
    async def exchange_code(self, code: str) -> IamToken:
        """用一次性授权码换统一票据（``getToken``）。"""
        data = {
            "appId": self.config.SSO_APP_ID,
            "clientSecret": self.config.SSO_CLIENT_SECRET,
            "code": code,
            "grantType": "authorization_code",
        }
        payload = await self._post_form(GET_TOKEN_PATH, data)
        self._ensure_success(payload, GET_TOKEN_PATH, secrets=_request_secrets(data))

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
        data = {
            "appId": self.config.SSO_APP_ID,
            "clientSecret": self.config.SSO_CLIENT_SECRET,
            "refreshToken": refresh_token,
        }
        payload = await self._post_form(REFRESH_TOKEN_PATH, data)
        self._ensure_success(payload, REFRESH_TOKEN_PATH, secrets=_request_secrets(data))

        data = payload.get("data") or {}
        access_token = data.get("accessToken")
        if not access_token:
            raise IamError("统一身份认证未返回 accessToken")
        renewed_refresh = data.get("refreshToken")
        if not renewed_refresh:
            # 规范 4.1.4.5：续期返回的 refreshToken 必填。缺失时不能沿用已消费的旧票
            # （下次必然 1025），按「没拿到可信答复」抛传输类错误，交给上层走宽限。
            logger.error("统一认证续期未返回 refreshToken，按不可达处理")
            raise IamError("统一身份认证续期未返回 refreshToken", code=None)
        return IamToken(
            access_token=str(access_token),
            refresh_token=str(renewed_refresh),
            expires_in=_as_int(data.get("expiresIn")),
            uid=data.get("uid") or None,
        )

    async def get_user_info(self, access_token: str) -> IamUser:
        """用统一票据取用户信息（``getUserInfo``）。"""
        data = {
            "appId": self.config.SSO_APP_ID,
            "accessToken": access_token,
        }
        payload = await self._post_form(GET_USER_INFO_PATH, data)
        self._ensure_success(payload, GET_USER_INFO_PATH, secrets=_request_secrets(data))

        raw = payload.get("userInfo") or {}
        if not isinstance(raw, dict):
            logger.error("统一认证返回的 userInfo 不是对象 type=%s", type(raw).__name__)
            raise IamError("统一身份认证用户信息格式非法", malformed=True)
        user_id = raw.get("userId")
        if not user_id:
            raise IamError("统一身份认证未返回 userId")

        orgs = raw.get("orgs")
        if isinstance(orgs, list):
            # 甲方可能返回 orgs:[null]：pydantic 会因此抛 ValidationError 打成 500，
            # 这里只保留对象元素，其余静默丢弃（平台对组织字段不做强校验）。
            orgs = [item for item in orgs if isinstance(item, dict)]
        else:
            orgs = []
        try:
            return IamUser(
                user_id=str(user_id),
                user_name=_as_str(raw.get("userName")),
                fullname=_as_str(raw.get("fullname")),
                employee_no=_as_str(raw.get("employeeNo")),
                mobile=_as_str(raw.get("mobile")),
                email=_as_str(raw.get("email")),
                gender=_as_str(raw.get("gender")),
                change_password_must=_as_bool(raw.get("changePasswordMust")),
                orgs=orgs,
            )
        except ValidationError as exc:
            logger.error("统一认证用户信息字段不合法 error=%s", type(exc).__name__)
            raise IamError("统一身份认证用户信息格式非法", malformed=True) from exc

    async def check_access_token(self, access_token: str) -> bool:
        """校验统一票据是否仍然有效。

        只有**对方明确回答票据失效**（``ticket_invalid``：``2002``/``1025``/``1014``）
        才返回 ``False``。其余失败一律向上抛 ``IamError``：

        * 连不上 / 没拿到可信答复（``code is None``）——对方不可用时不能踢人；
        * ``http_status`` 存在——状态码本身不是业务结论，交给上层按业务码分类；
        * ``1001``/``2001``/``2006`` 这类 ``request_invalid``——那是我方请求或配置
          错了，把它伪装成「票据无效」会让所有人被清会话。
        """
        try:
            data = {"accessToken": access_token}
            payload = await self._post_form(CHECK_ACCESS_TOKEN_PATH, data)
            self._ensure_success(
                payload, CHECK_ACCESS_TOKEN_PATH, secrets=_request_secrets(data)
            )
        except IamError as exc:
            if exc.http_status is not None or exc.code is None:
                raise
            if iam_result_category(exc.code) is IamResultCategory.TICKET_INVALID:
                return False
            raise
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


def _request_secrets(data: Dict[str, str]) -> tuple[str, ...]:
    """本次请求里不能进日志的明文：secret、两种票据与一次性授权码。

    4xx 响应体经常把请求参数原样回显，所以按「本次请求实际发了什么」来脱敏，
    而不是维护一份字段名黑名单。长串优先替换，避免短串是长串子串时留下残片。
    """
    secrets = set()
    for key in ("clientSecret", "refreshToken", "accessToken", "code"):
        value = data.get(key)
        if value:
            secrets.add(str(value))
    return tuple(sorted(secrets, key=len, reverse=True))


def _safe_snippet(raw: str, *, secrets: tuple[str, ...] = (), limit: int = 200) -> str:
    """把响应片段变成可以落日志的一行：去控制字符 -> 抹掉密钥 -> 截断。

    去控制字符的口径与 ``app.api.v1.auth_sso._log_safe`` 同源；这里额外承担
    「抹掉本次请求里的 secret」——日志里只能有结果码与长度，不能有票据。
    没有抽公共模块，是因为 ``app/common/`` 不在本次改动范围内。
    """
    text = _CONTROL_CHARS.sub("?", str(raw))
    for secret in secrets:
        if secret:
            text = text.replace(secret, "***")
    return text[:limit]


def _error_body_identity(
    response: httpx.Response,
    *,
    secrets: tuple[str, ...],
) -> tuple[Optional[str], Optional[str]]:
    """从 4xx/5xx 响应体里取 ``(业务码, 已脱敏的 message)``；取不到可信码时码为 ``None``。

    只认标量形态的 ``code``：``None``/``bool``/``dict``/``list``/空串一律不算，
    非 JSON 或非对象同样返回 ``None``。调用方据此退回「按状态码」的语义。

    ``message`` 是要放进 ``IamError`` 的外部文本，必须带上本次请求的 ``secrets``
    走 ``_safe_snippet``：4xx 体里经常原样回显 ``clientSecret``，不脱敏就等于把密钥
    写进 ``str(exc)``。返回的已经是转义、脱敏并截断到 ``_MESSAGE_LIMIT`` 的片段。
    ``secrets`` 不给默认值，理由同 ``IamClient._ensure_success``。
    """
    try:
        payload = response.json()
    except ValueError:
        return None, None
    if not isinstance(payload, dict):
        return None, None

    raw_code = payload.get("code")
    if raw_code is None or isinstance(raw_code, (bool, dict, list)):
        code: Optional[str] = None
    else:
        text = str(raw_code).strip()
        code = text or None

    raw_message = payload.get("message")
    message: Optional[str] = None
    if isinstance(raw_message, str):
        message = (
            _safe_snippet(raw_message, secrets=secrets, limit=_MESSAGE_LIMIT).strip()
            or None
        )
    return code, message


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
