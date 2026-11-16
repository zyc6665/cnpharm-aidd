"""统一认证结果码真源与会话判定的验收矩阵。

本文件是「结果码单一真源 + 错误分类顺序」改造的回归锚点，对应任务单 §6：

* ``T1``–``T10``：纯函数（码表、派生集合、``iam_result_category``、``_classify_iam_error``）；
* ``T11``–``T19``：出网原语（``httpx.MockTransport``，不发真实请求）；
* ``T20``–``T24``：会话判定（本地 stub client，不走 HTTP）。

约定：

* 只用 ``.example`` 域名，离线环境可跑；
* 同步测试 + ``asyncio.run``，不引入 ``pytest-asyncio``；
* 旧代码里两个「非规范码」的字面量**只允许出现在本文件**：``T3`` 断言它们已从
  ``backend/app/services`` 下消失，出现即回归。手写它们是为了让断言可执行，不是
  为了保留兼容。
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pytest

from app.config import Settings
from app.services import iam_session
from app.services.iam_client import (
    _SESSION_ENDPOINTS,
    IAM_RESULT_CODES,
    SUCCESS_CODE,
    IamClient,
    IamError,
    IamResultCategory,
    IamToken,
    _MESSAGE_LIMIT,
    _safe_snippet,
    codes_of_category,
    iam_result_category,
)
from app.services.iam_session import (
    IamSessionStatus,
    IamTickets,
    _classify_iam_error,
    validate_iam_session,
)

BASE_URL = "https://iam.example"
REDIRECT_URI = "https://platform.example/api/v1/auth/sso/callback"
CLIENT_SECRET = "unit-test-only-client-secret"

EXPECTED_CODES = {
    "1001",
    "1005",
    "1008",
    "1009",
    "1010",
    "1012",
    "1014",
    "1024",
    "1025",
    "2001",
    "2002",
    "2006",
    "3002",
    "9001",
}
REQUEST_INVALID_EXPECTED = {
    "1001",
    "1005",
    "1008",
    "1009",
    "1010",
    "1012",
    "1024",
    "2001",
    "2006",
}
TICKET_INVALID_EXPECTED = {"2002", "1025", "1014"}

SERVICES_DIR = Path(__file__).resolve().parents[1] / "backend/app/services"
NOW = datetime(2026, 1, 1, 12, 0, 0)


def _settings(**overrides: object) -> Settings:
    params: dict[str, object] = {
        "ENVIRONMENT": "development",
        "SSO_ENABLED": True,
        "SSO_BASE_URL": BASE_URL,
        "SSO_APP_ID": "cnpharm-aidd",
        "SSO_CLIENT_SECRET": CLIENT_SECRET,
        "SSO_REDIRECT_URI": REDIRECT_URI,
    }
    params.update(overrides)
    return Settings(**params)


def _client(handler) -> IamClient:
    return IamClient(_settings(), transport=httpx.MockTransport(handler))


def _json(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _run(coro):
    return asyncio.run(coro)


# --------------------------------------------------------------- 纯函数 T1–T10
def test_t1_result_code_table_has_exactly_the_spec_codes():
    """A1：14 行，键集合精确等于规范里出现过的码，一个不多一个不少。"""
    assert len(IAM_RESULT_CODES) == 14
    assert set(IAM_RESULT_CODES) == EXPECTED_CODES


def test_t2_every_row_is_complete():
    """A2：每行都有语义、规范出处、适用接口与合法分类。"""
    categories = set(IamResultCategory)
    for code, row in IAM_RESULT_CODES.items():
        assert row.semantics.strip(), code
        assert row.spec_ref.startswith("4.1."), (code, row.spec_ref)
        assert row.category in categories, code
        assert row.endpoints, code
        assert all(path.startswith("/auth/api/") for path in row.endpoints), code


def test_t3_retired_non_spec_codes_and_old_sets_are_gone(caplog):
    """B1/B7：两个非规范码与两个手写集合都已从运行代码里消失。"""
    assert "9002" not in IAM_RESULT_CODES
    assert "9100" not in IAM_RESULT_CODES

    for name in ("iam_client.py", "iam_session.py"):
        source = (SERVICES_DIR / name).read_text(encoding="utf-8")
        for retired in ("9002", "9100"):
            assert retired not in source, f"{name} 仍出现非规范码 {retired}"
    session_source = (SERVICES_DIR / "iam_session.py").read_text(encoding="utf-8")
    assert "_SYSTEM_ERROR_CODES" not in session_source
    # 续期缺 refreshToken 已由客户端抛错，会话侧不得再沿用旧票。
    assert "or tickets.refresh_token" not in session_source


def test_t4_derived_sets_match_the_decision_table():
    """A3/B1：派生集合精确等于 9 个 request_invalid + 3 个 ticket_invalid。"""
    assert codes_of_category(IamResultCategory.REQUEST_INVALID) == REQUEST_INVALID_EXPECTED
    assert codes_of_category(IamResultCategory.TICKET_INVALID) == TICKET_INVALID_EXPECTED
    assert iam_session._REQUEST_INVALID_CODES == REQUEST_INVALID_EXPECTED
    assert iam_session._TICKET_INVALID_CODES == TICKET_INVALID_EXPECTED
    assert not (REQUEST_INVALID_EXPECTED & TICKET_INVALID_EXPECTED)
    assert len(REQUEST_INVALID_EXPECTED | TICKET_INVALID_EXPECTED) == 12


def test_t5_semantics_spec_ref_and_logout_only_rows_are_pinned():
    """A2/B3：历史上写错位的三条语义逐字锁定；3002 只属于注销接口。"""
    assert IAM_RESULT_CODES["1009"].semantics == "缺少参数 code"
    assert IAM_RESULT_CODES["1010"].semantics == "缺少参数 grant_type"
    assert IAM_RESULT_CODES["1012"].semantics == "参数 client_secret 非法"
    assert IAM_RESULT_CODES["1009"].spec_ref == "4.1.3.2"
    assert IAM_RESULT_CODES["1025"].spec_ref == "4.1.4.5"
    assert IAM_RESULT_CODES["2002"].spec_ref == "4.1.5.5"
    assert IAM_RESULT_CODES["3002"].category is IamResultCategory.OTHER
    assert IAM_RESULT_CODES["3002"].endpoints.isdisjoint(_SESSION_ENDPOINTS) is True
    assert IAM_RESULT_CODES[SUCCESS_CODE].category is IamResultCategory.SUCCESS


def test_t6_result_code_table_is_read_only():
    """A4：``MappingProxyType`` 生效，误改真源必须在导入期就炸。"""
    with pytest.raises(TypeError):
        IAM_RESULT_CODES["9999"] = IAM_RESULT_CODES[SUCCESS_CODE]  # type: ignore[index]


def test_t7_iam_result_category_normalizes_and_rejects_unknown():
    """A5：``str``/``int``/带空白都能归一；非规范码与非标量一律 ``None``。"""
    assert iam_result_category(SUCCESS_CODE) is IamResultCategory.SUCCESS
    assert iam_result_category(9001) is IamResultCategory.SUCCESS
    assert iam_result_category(" 9001 ") is IamResultCategory.SUCCESS
    assert iam_result_category("2002") is IamResultCategory.TICKET_INVALID
    for unknown in ("9002", "9100", "9999", "", None, True, {"code": "2002"}, ["2002"]):
        assert iam_result_category(unknown) is None, unknown


def test_t8_iam_error_transport_flag_has_two_axes():
    """A6：``code`` 与 ``malformed`` 是两个正交轴，都不能当成「没拿到答复」。"""
    assert IamError("x").is_transport_error is True
    assert IamError("x", code="1014").is_transport_error is False
    assert IamError("x", malformed=True).is_transport_error is False
    # 有状态码但没业务码：仍是「没拿到可信答复」，由分类函数按状态码分流。
    assert IamError("x", http_status=503).is_transport_error is True


def test_t9_request_invalid_codes_go_to_grace_not_death(caplog):
    """B2：9 个 request_invalid 全部 UNAVAILABLE，且必须打 ERROR 带码。"""
    for code in sorted(REQUEST_INVALID_EXPECTED):
        caplog.clear()
        with caplog.at_level("ERROR"):
            result = _classify_iam_error(IamError("boom", code=code), "refresh")
        assert result.status is IamSessionStatus.UNAVAILABLE, code
        assert code in result.reason
        assert any(
            record.levelno >= logging.ERROR and code in record.getMessage()
            for record in caplog.records
        ), code


def test_t10_ticket_invalid_codes_kill_session_with_code_in_reason():
    """B2：2002/1025/1014 在任何阶段都判死，``reason`` 带码便于排障。"""
    for code in sorted(TICKET_INVALID_EXPECTED):
        for phase in ("check", "refresh"):
            result = _classify_iam_error(IamError("boom", code=code), phase)
            assert result.status is IamSessionStatus.DEAD, (code, phase)
            assert code in result.reason


# ----------------------------------------------------------- 出网原语 T11–T19
def test_t11_http_400_with_ticket_code_is_dead_not_grace():
    """A7/完成定义 3：400 + {"code":"1025"} 必须同时带 code 与状态码，判死。"""
    client = _client(
        lambda request: httpx.Response(
            400, json={"code": "1025", "message": "refresh_token 不正确或过期"}
        )
    )

    with pytest.raises(IamError) as excinfo:
        _run(client.refresh("rt-old"))

    assert excinfo.value.code == "1025"
    assert excinfo.value.http_status == 400
    assert _classify_iam_error(excinfo.value, "refresh").status is IamSessionStatus.DEAD


def test_t12_http_503_without_business_code_is_unavailable():
    """A7：非 JSON 的 5xx 拿不到业务码，只带状态码，按不可达处理。"""
    client = _client(lambda request: httpx.Response(503, text="<html>busy</html>"))

    with pytest.raises(IamError) as excinfo:
        _run(client.refresh("rt-old"))

    assert excinfo.value.code is None
    assert excinfo.value.http_status == 503
    result = _classify_iam_error(excinfo.value, "refresh")
    assert result.status is IamSessionStatus.UNAVAILABLE
    # reason 也锁住：5xx 必须在「表外码/状态码」之前分流，否则这条断言会变。
    assert result.reason == "refresh_unavailable"


def test_t13_server_error_wins_over_unlisted_body_code():
    """B2：表外码 + 5xx 先走「服务端故障」，不因陌生码 fail-closed。"""
    client = _client(lambda request: httpx.Response(503, json={"code": "500"}))

    with pytest.raises(IamError) as excinfo:
        _run(client.exchange_code("code-1"))

    assert excinfo.value.http_status == 503
    result = _classify_iam_error(excinfo.value, "check")
    assert result.status is IamSessionStatus.UNAVAILABLE
    # 体里那个陌生码不能把 503 拉回 fail-closed，也不能走 ③ 的「非预期状态」。
    assert result.reason == "check_unavailable"


def test_t14_rate_limit_and_timeout_status_are_unavailable():
    """B2：408/429 是暂时性故障，不能判死。"""
    for status in (408, 429):
        client = _client(lambda request, status=status: httpx.Response(status, text="busy"))
        with pytest.raises(IamError) as excinfo:
            _run(client.exchange_code("code-1"))
        result = _classify_iam_error(excinfo.value, "check")
        assert result.status is IamSessionStatus.UNAVAILABLE, status
        assert result.reason == "check_unavailable", status


def test_t15_refresh_without_refresh_token_raises_transport_like_error(caplog):
    """完成定义 4：续期缺 refreshToken → ``IamError(code=None)`` + ERROR，不沿用旧票。"""
    client = _client(
        lambda request: _json({"code": "9001", "data": {"accessToken": "at-2"}})
    )

    with caplog.at_level("ERROR"):
        with pytest.raises(IamError) as excinfo:
            _run(client.refresh("rt-old"))

    assert excinfo.value.code is None
    assert excinfo.value.http_status is None
    assert (
        _classify_iam_error(excinfo.value, "refresh").status
        is IamSessionStatus.UNAVAILABLE
    )
    assert any(
        record.levelno >= logging.ERROR and "refreshToken" in record.getMessage()
        for record in caplog.records
    )


def test_t16_unexpected_success_code_is_unavailable_with_error_log(caplog):
    """D1：``9001`` 出现在异常路径 → UNAVAILABLE + ``unexpected_success`` + ERROR。"""
    client = _client(lambda request: httpx.Response(400, json={"code": "9001"}))

    with caplog.at_level("ERROR"):
        with pytest.raises(IamError) as excinfo:
            _run(client.refresh("rt-old"))

    result = _classify_iam_error(excinfo.value, "refresh")
    assert result.status is IamSessionStatus.UNAVAILABLE
    assert "unexpected_success" in result.reason
    assert any(record.levelno >= logging.ERROR for record in caplog.records)


def test_t17_check_access_token_only_false_on_ticket_invalid():
    """A8：只有 ticket_invalid 返回 False；请求类码与传输错误都必须抛。"""
    assert (
        _run(_client(lambda request: _json({"code": "2002"})).check_access_token("at-1"))
        is False
    )
    assert (
        _run(_client(lambda request: _json({"code": "9001"})).check_access_token("at-1"))
        is True
    )
    for code in ("1001", "2001", "2006"):
        client = _client(lambda request, code=code: _json({"code": code}))
        with pytest.raises(IamError) as excinfo:
            _run(client.check_access_token("at-1"))
        assert excinfo.value.code == code

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    with pytest.raises(IamError) as excinfo:
        _run(_client(boom).check_access_token("at-1"))
    assert excinfo.value.is_transport_error is True


def test_t18_get_user_info_filters_non_dict_orgs():
    """A10：``orgs:[null]`` 不能让 pydantic 抛到回调层打成 500。"""
    mixed = {
        "code": "9001",
        "userInfo": {"userId": "u-1", "orgs": [None, {"unitCode": "U01"}]},
    }
    user = _run(_client(lambda request: _json(mixed)).get_user_info("at-1"))
    assert [item["unitCode"] for item in user.orgs] == ["U01"]

    empty = {"code": "9001", "userInfo": {"userId": "u-1", "orgs": [None, None]}}
    assert _run(_client(lambda request: _json(empty)).get_user_info("at-1")).orgs == []

    malformed = _client(lambda request: _json({"code": "9001", "userInfo": "not-a-dict"}))
    with pytest.raises(IamError) as excinfo:
        _run(malformed.get_user_info("at-1"))
    assert excinfo.value.malformed is True
    assert excinfo.value.is_transport_error is False


def test_t19_error_body_snippet_is_redacted_and_truncated(caplog):
    """A11：4xx 响应体回显 clientSecret 时，日志与异常里都只能是 ``***`` 且片段 <=200。"""
    body = '{"code":"1012","message":"' + CLIENT_SECRET + "x" * 800 + '"}'
    client = _client(
        lambda request: httpx.Response(
            400, text=body, headers={"content-type": "application/json"}
        )
    )

    with caplog.at_level("DEBUG"):
        with pytest.raises(IamError) as excinfo:
            _run(client.exchange_code("code-1"))

    assert CLIENT_SECRET not in caplog.text
    assert "***" in caplog.text
    snippet = _safe_snippet(body, secrets=(CLIENT_SECRET,))
    assert len(snippet) <= 200
    assert CLIENT_SECRET not in snippet
    # 日志脱敏还不够：``str(exc)`` 可能被上层写进日志或响应体，同样不能有明文。
    assert CLIENT_SECRET not in str(excinfo.value)
    assert len(str(excinfo.value)) <= _MESSAGE_LIMIT


def test_t26_http_400_message_is_redacted_in_log_and_exception(caplog):
    """完成定义 2(a)：400 + 1012 的 message 回显 clientSecret，日志与异常都不得泄漏。

    ``"client_secret=<真值>"`` 是甲方最常见的回显形态，也是旧实现
    ``_error_body_identity(response)`` 漏传 secrets 时把明文塞进 ``IamError`` 的
    那条路径。
    """
    body = f"bad request: client_secret={CLIENT_SECRET} for appId cnpharm-aidd"
    client = _client(
        lambda request: httpx.Response(400, json={"code": "1012", "message": body})
    )

    with caplog.at_level("DEBUG"):
        with pytest.raises(IamError) as excinfo:
            _run(client.exchange_code("code-1"))

    assert excinfo.value.code == "1012"
    assert excinfo.value.http_status == 400
    assert CLIENT_SECRET not in caplog.text
    assert CLIENT_SECRET not in str(excinfo.value)
    # 只留脱敏片段：前缀还能排障，密钥已被抹掉，整体不超过上限。
    assert "client_secret=***" in str(excinfo.value)
    assert len(str(excinfo.value)) <= _MESSAGE_LIMIT


def test_t27_http_200_business_failure_message_is_redacted_in_log_and_exception(caplog):
    """完成定义 2(b)：200 + 1012 走 ``_ensure_success``，同样只留脱敏片段。"""
    body = f"参数 client_secret={CLIENT_SECRET} 非法" + "x" * 500
    client = _client(lambda request: _json({"code": "1012", "message": body}))

    with caplog.at_level("DEBUG"):
        with pytest.raises(IamError) as excinfo:
            _run(client.exchange_code("code-1"))

    assert excinfo.value.code == "1012"
    assert excinfo.value.http_status is None
    assert CLIENT_SECRET not in caplog.text
    assert CLIENT_SECRET not in str(excinfo.value)
    assert "client_secret=***" in str(excinfo.value)
    assert len(str(excinfo.value)) <= _MESSAGE_LIMIT


# ----------------------------------------------------------- 会话判定 T20–T24
class _StubClient:
    """只实现 ``validate_iam_session`` 用到的两个方法，并记录调用顺序。"""

    def __init__(
        self,
        *,
        check: bool = True,
        check_error: IamError | None = None,
        refresh: IamToken | None = None,
        refresh_error: IamError | None = None,
    ) -> None:
        self.calls: list[str] = []
        self._check = check
        self._check_error = check_error
        self._refresh = refresh
        self._refresh_error = refresh_error

    async def check_access_token(self, access_token: str) -> bool:
        self.calls.append("checkAccessToken")
        if self._check_error is not None:
            raise self._check_error
        return self._check

    async def refresh(self, refresh_token: str) -> IamToken:
        self.calls.append("refreshToken")
        if self._refresh_error is not None:
            raise self._refresh_error
        assert self._refresh is not None
        return self._refresh


def _tickets(
    *,
    access_token: str | None = "at-1",
    refresh_token: str | None = None,
    expires_in: int = 3600,
) -> IamTickets:
    return IamTickets(
        access_token=access_token,
        refresh_token=refresh_token,
        access_expires_at=NOW + timedelta(seconds=expires_in),
        checked_at=None,
    )


def test_t20_check_401_without_refresh_token_goes_to_grace():
    """B4：没有 refreshToken 时 check 被 401 拒绝 → 不可达（吃宽限），不判死。"""
    client = _StubClient(check_error=IamError("rejected", http_status=401))

    result = _run(validate_iam_session(client, _tickets(), now=NOW))

    assert result.status is IamSessionStatus.UNAVAILABLE
    assert result.reason == "check_auth_rejected"
    assert client.calls == ["checkAccessToken"]


def test_t21_check_false_without_refresh_token_kills_session():
    """B4：明确业务码 2002（check 返回 False）且无 refreshToken → DEAD。"""
    client = _StubClient(check=False)

    result = _run(validate_iam_session(client, _tickets(), now=NOW))

    assert result.status is IamSessionStatus.DEAD
    assert result.reason == "check_ticket_invalid"
    assert client.calls == ["checkAccessToken"]


def test_t22_locally_expired_without_refresh_token_is_dead_without_network():
    """B4：本地已知 access 过期且无 refreshToken → DEAD 且零出网。"""
    client = _StubClient()

    result = _run(
        validate_iam_session(client, _tickets(expires_in=-10), now=NOW)
    )

    assert result.status is IamSessionStatus.DEAD
    assert result.reason == "access_expired"
    assert client.calls == []


def test_t23_refresh_success_replaces_tickets():
    """B4：有 refreshToken 时先续期自愈，新票据必须是对方返回的那一份。"""
    renewed = IamToken(
        access_token="at-2", refresh_token="rt-2", expires_in=3600, uid="u-1"
    )
    client = _StubClient(check=False, refresh=renewed)

    result = _run(
        validate_iam_session(client, _tickets(refresh_token="rt-1"), now=NOW)
    )

    assert result.status is IamSessionStatus.REFRESHED
    assert result.tickets is not None
    assert result.tickets.access_token == "at-2"
    assert result.tickets.refresh_token == "rt-2"
    assert client.calls == ["checkAccessToken", "refreshToken"]


def test_t24_check_5xx_and_transport_failures_do_not_kill_session():
    """B4/B5：check 5xx 不烧 refreshToken；续期传输失败 → 不可达（宽限）。"""
    busy = _StubClient(
        check_error=IamError("busy", code=None, http_status=503)
    )
    result = _run(
        validate_iam_session(busy, _tickets(refresh_token="rt-1"), now=NOW)
    )
    assert result.status is IamSessionStatus.UNAVAILABLE
    assert result.reason == "check_unavailable"
    assert busy.calls == ["checkAccessToken"]

    unreachable = _StubClient(refresh_error=IamError("unreachable", code=None))
    result = _run(
        validate_iam_session(
            unreachable, _tickets(expires_in=-10, refresh_token="rt-1"), now=NOW
        )
    )
    assert result.status is IamSessionStatus.UNAVAILABLE
    assert result.reason == "refresh_unavailable"
    assert unreachable.calls == ["refreshToken"]


def test_t25_unlisted_code_fails_closed_with_error_log(caplog):
    """B1/完成定义 2：表外业务码必须 DEAD（fail-closed），并用 ERROR 把新码暴露出来。

    这里把两个已退出规范码表的旧码也当成「表外码」跑一遍：删掉它们之后行为必须
    与其它陌生码一致（判死 + ERROR），而不是悄悄滑回宽限。
    """
    for code in ("9999", "9002", "9100"):
        caplog.clear()
        with caplog.at_level("ERROR"):
            result = _classify_iam_error(IamError("boom", code=code), "check")
        assert result.status is IamSessionStatus.DEAD, code
        assert result.reason == f"check_code_{code}", code
        assert any(
            record.levelno >= logging.ERROR and code in record.getMessage()
            for record in caplog.records
        ), code


def test_t26_total_budget_caps_check_plus_refresh():
    """总预算：check 与 refresh 串行不能把一次 /refresh 拖过前端 handoff 等待。

    前端并发刷新的落败方最多等 ``REFRESH_HANDOFF_MAX_WAIT_MS``（6000ms）；后端若让
    「check 5s + refresh 5s」真的跑满 10s，落败方会先超时、拿旧 access 重放、被 401
    踢回登录页。这里用一个永远不返回的 check 证明：超预算按「不可达」收口（吃宽限），
    而不是继续等第二次 IAM 调用。
    """
    import asyncio as _asyncio

    class _HangingClient(_StubClient):
        async def check_access_token(self, access_token: str) -> bool:
            self.calls.append("checkAccessToken")
            await _asyncio.sleep(30)
            return True

    client = _HangingClient()

    async def _run_with_budget():
        return await validate_iam_session(
            client, _tickets(), now=NOW, budget_seconds=0.05
        )

    result = _asyncio.run(_run_with_budget())

    assert result.status is IamSessionStatus.UNAVAILABLE
    assert result.reason == "budget_exceeded"
    assert client.calls == ["checkAccessToken"]
