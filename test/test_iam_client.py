"""统一身份认证客户端（``app.services.iam_client``）单元测试。

全部用例走 ``httpx.MockTransport``，不发真实网络请求：离线环境也能跑，且可以把
「对方返回 200 + 业务失败码」这种最容易踩的形态精确复现出来。
"""

from __future__ import annotations

import asyncio

import httpx
import pytest
from pydantic import ValidationError

from app.config import Settings
from app.services.iam_client import (
    GET_TOKEN_PATH,
    GET_USER_INFO_PATH,
    GLO_PATH,
    IamClient,
    IamError,
    build_iam_client,
)

REDIRECT_URI = "https://platform.example/api/v1/auth/sso/callback"
BASE_URL = "https://iam.example"


def _settings(**overrides: object) -> Settings:
    params: dict[str, object] = {
        "ENVIRONMENT": "development",
        "SSO_ENABLED": True,
        "SSO_BASE_URL": BASE_URL,
        "SSO_APP_ID": "cnpharm-aidd",
        "SSO_CLIENT_SECRET": "super-secret-value",
        "SSO_REDIRECT_URI": REDIRECT_URI,
    }
    params.update(overrides)
    return Settings(**params)


def _client(handler) -> IamClient:
    return IamClient(_settings(), transport=httpx.MockTransport(handler))


def _json(payload: dict, status: int = 200) -> httpx.Response:
    return httpx.Response(status, json=payload)


def _run(coro):
    """在同步测试里跑一个协程，避免为一个纯 HTTP 封装引入 pytest-asyncio 依赖。"""
    return asyncio.run(coro)


def test_authorize_url_carries_app_id_state_and_encoded_redirect_uri():
    client = IamClient(_settings())

    url = client.build_authorize_url("state-abc")

    assert url.startswith(f"{BASE_URL}/auth/api/user/webungateway/authorize?")
    assert "appId=cnpharm-aidd" in url
    assert "responseType=code" in url
    assert "state=state-abc" in url
    # redirectUri 必须编码：未编码时 "https://" 会被对方截断
    assert "redirectUri=https%3A%2F%2Fplatform.example%2Fapi%2Fv1%2Fauth%2Fsso%2Fcallback" in url


def test_logout_url_uses_documented_misspelled_parameter():
    client = IamClient(_settings())

    url = client.build_logout_url("https://platform.example/login")

    assert url.startswith(f"{BASE_URL}{GLO_PATH}?")
    # 对方文档写的是 redirctToUrl（少一个 e），写对反而会被当成缺参数
    assert "redirctToUrl=https%3A%2F%2Fplatform.example%2Flogin" in url
    assert "redirectToLogin=false" in url
    assert "appId=cnpharm-aidd" in url


def test_exchange_code_posts_form_and_parses_token():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return _json(
            {
                "code": "9001",
                "message": "操作成功",
                "data": {
                    "accessToken": "at-1",
                    "refreshToken": "rt-1",
                    "expiresIn": "3600",
                    "uid": "iam-001",
                },
            }
        )

    token = _run(_client(handler).exchange_code("code-1"))

    assert token.access_token == "at-1"
    assert token.refresh_token == "rt-1"
    assert token.expires_in == 3600
    assert token.uid == "iam-001"

    request = seen[0]
    assert request.method == "POST"
    assert request.url.path == GET_TOKEN_PATH
    # 密钥只能出现在 body 里，绝不能进 URL（URL 会进访问日志）
    assert "clientSecret" not in str(request.url)
    body = request.content.decode()
    assert "appId=cnpharm-aidd" in body
    assert "clientSecret=super-secret-value" in body
    assert "grantType=authorization_code" in body


def test_exchange_code_raises_with_remote_code_on_business_failure():
    client = _client(
        lambda request: _json({"code": "1014", "message": "code 非法"})
    )

    with pytest.raises(IamError) as excinfo:
        _run(client.exchange_code("used-code"))

    assert excinfo.value.code == "1014"
    assert excinfo.value.is_transport_error is False
    assert "code 非法" in str(excinfo.value)


def test_get_user_info_maps_fields_and_keeps_orgs():
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == GET_USER_INFO_PATH
        assert "accessToken=at-1" in request.content.decode()
        return _json(
            {
                "code": "9001",
                "message": "操作成功",
                "userInfo": {
                    "userId": "iam-001",
                    "userName": "zhangsan",
                    "fullname": "张三",
                    "employeeNo": "E10086",
                    "mobile": "13800000000",
                    "email": "zhangsan@example.com",
                    "gender": "1",
                    "changePasswordMust": "false",
                    "orgs": [
                        {
                            "unitCode": "U01",
                            "unitName": "中国医药",
                            "deptName": "信息中心",
                        }
                    ],
                },
            }
        )

    user = _run(_client(handler).get_user_info("at-1"))

    assert user.user_id == "iam-001"
    assert user.user_name == "zhangsan"
    assert user.fullname == "张三"
    assert user.email == "zhangsan@example.com"
    assert user.change_password_must is False
    assert user.orgs[0]["deptName"] == "信息中心"
    assert user.display_name() == "张三"


def test_get_user_info_without_user_id_fails_loudly():
    client = _client(lambda request: _json({"code": "9001", "userInfo": {}}))

    with pytest.raises(IamError):
        _run(client.get_user_info("at-1"))


def test_check_access_token_distinguishes_invalid_ticket_from_outage():
    def invalid(request: httpx.Request) -> httpx.Response:
        return _json({"code": "2002", "message": "access_token 不正确或过期"})

    assert _run(_client(invalid).check_access_token("at-1")) is False

    def valid(request: httpx.Request) -> httpx.Response:
        return _json({"code": "9001", "message": "操作成功"})

    assert _run(_client(valid).check_access_token("at-1")) is True

    def boom(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timed out")

    # 对方不可用时必须抛错：此时把用户踢下线等于把自己变成单点故障
    with pytest.raises(IamError) as excinfo:
        _run(_client(boom).check_access_token("at-1"))
    assert excinfo.value.is_transport_error is True


def test_non_json_body_raises_iam_error():
    client = _client(lambda request: httpx.Response(200, text="<html>502</html>"))

    with pytest.raises(IamError):
        _run(client.exchange_code("code-1"))


def test_http_error_status_raises_with_status():
    client = _client(lambda request: httpx.Response(503, text="busy"))

    with pytest.raises(IamError) as excinfo:
        _run(client.exchange_code("code-1"))

    assert excinfo.value.http_status == 503


def test_secret_never_appears_in_logs(caplog):
    client = _client(lambda request: _json({"code": "1005", "message": "appId 非法"}))

    with caplog.at_level("DEBUG"):
        with pytest.raises(IamError):
            _run(client.exchange_code("code-1"))

    assert "super-secret-value" not in caplog.text


def test_build_iam_client_returns_none_when_disabled():
    assert build_iam_client(_settings(SSO_ENABLED=False)) is None


def test_enabled_config_without_secret_is_rejected_at_startup():
    """配置校验在启动时就拦住半配置状态，不等到第一次登录才报错。"""
    with pytest.raises(ValidationError):
        _settings(SSO_CLIENT_SECRET="")
