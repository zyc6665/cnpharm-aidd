# backend/app/main.py
"""FastAPI 主应用入口"""

from contextlib import asynccontextmanager
import asyncio
import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware

from app.auth.cookies import clear_auth_cookies
from app.config import settings, use_direct_task_execution
from app.cache import get_cache
from app.database.session import init_db
from app.api.v1 import api_router
from app.artifact_standards.registry import StandardArtifactRegistryError
from app.common.exceptions import AppException
from app.common.responses import error_response
from app.common.time import isoformat_utc, utcnow
from app.common.trace import TRACE_ID_HEADER, get_trace_id
from app.middleware import RateLimitMiddleware
from app.middleware.trace import TraceIdMiddleware
from app.monitoring.prometheus_metrics import PrometheusMiddleware, metrics_endpoint
from app.services.audit_sink import configure_audit_db_writer
from app.tasks.direct_recovery import direct_task_recovery_loop
from app.tasks.direct_runner import direct_task_runner
from app.services.workflow_reconciliation import workflow_reconcile_loop
from app.services.upload_maintenance import upload_sweep_loop
from app.services.artifact_gc import artifact_gc_loop
from app.services.idempotency_maintenance import idempotency_sweep_loop
from app.services.queue_timeout import queue_timeout_sweep_loop
from app.services.quota_maintenance import quota_settlement_loop
from app.services.runtime_log_sync import runtime_log_sync_loop
from app.services.platform_tool_seeding import seed_platform_tools_on_startup
from app.storage.lifecycle import ensure_lifecycle_on_startup
from app.worker.celery_app import configure_managed_execution_runtime

logger = logging.getLogger(__name__)


def _trace_id_from_scope(request: Request) -> str | None:
    """从 ``request.scope["state"]`` 取 trace 中间件写入的 traceId。

    contextvar 只在中间件栈内部有效；``ServerErrorMiddleware`` 的异常处理器在
    contextvar 复位之后才被调用，必须回落到 scope 上那份副本。

    用 ``getattr`` 而不是 ``request.scope``：既有单测
    （``test/test_main_logging.py``）把 request 传成只带 ``method`` / ``url`` 的
    ``SimpleNamespace`` 桩对象，直接点属性会 AttributeError 把 500 变成崩溃。
    """
    scope = getattr(request, "scope", None)
    if not isinstance(scope, dict):
        return None
    state = scope.get("state")
    if isinstance(state, dict):
        return state.get("trace_id")
    return None


def configure_direct_managed_execution_runtime():
    """Register managed execution adapters for the direct task runner only."""
    if not use_direct_task_execution():
        return None
    return configure_managed_execution_runtime()


async def _warm_worker_probe() -> None:
    """后台预热一次 Celery Worker 探测（#112），把 celery 生态的 import 开销挪出请求路径。"""
    try:
        from app.worker.health import probe_workers

        await probe_workers()
    except Exception:  # noqa: BLE001 - 预热失败只影响首次探测的速度，不能影响启动
        logger.debug("启动期 Celery 探测预热失败（忽略）", exc_info=True)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动时初始化数据库
    await init_db()
    # 启动期幂等补齐平台必备工具：历史种子迁移在「无 admin」时会静默空转，这里兜底。
    # 全程 try/except：seeding 失败只记异常日志，绝不能阻断应用启动。
    try:
        await seed_platform_tools_on_startup()
    except Exception:  # noqa: BLE001 - 启动兜底，任何异常都不应拖垮应用
        logger.exception("启动期平台工具 seeding 异常（启动继续）")
    managed_runtime = configure_direct_managed_execution_runtime()
    workflow_reconcile_loop.start()
    if use_direct_task_execution():
        direct_task_recovery_loop.start()
    # Celery Worker 探测预热（#112）：第一次 `inspect().ping()` 要在探测线程里 import
    # celery/kombu/redis 生态（实测 1.7s），放在请求路径上会把首次 `/health` 拖过预算、
    # 误报 degraded。这里后台跑一次把 import 开销挪走；失败无所谓，`_check_celery` 会再探。
    app.state.worker_probe_warmup = asyncio.create_task(_warm_worker_probe())
    # 审计事件落库（步骤 7）：文件轨迹仍开启，数据库是查询入口。
    audit_writer = configure_audit_db_writer()
    audit_writer.start()
    # 过期分片上传会话清理：只在三个业务入口之外兜底，避免僵尸会话长期占存储。
    if upload_sweep_loop is not None:
        upload_sweep_loop.start()
    # 无引用 File 回收（计划 §5.6）：版本/项目删除后的对象存储孤儿兜底。
    if artifact_gc_loop is not None:
        artifact_gc_loop.start()
    # 过期幂等记录清理：24h 保留期到点即删，避免带响应快照的行无限增长。
    if idempotency_sweep_loop is not None:
        idempotency_sweep_loop.start()
    # 排队超时兜底（docs/18 §6.4 B-2b）：队列一旦停止消费，任务会永远挂 QUEUED，
    # 页面显示「排队中」而实际永远不会开始——必须有与用户行为无关的上限。
    if queue_timeout_sweep_loop is not None:
        queue_timeout_sweep_loop.start()
    # 配额漏核销兜底（docs/04 §5.3）：主路径是状态机终态核销，这里只补历史数据与
    # 绕过状态机的改库；开关关闭时 `quota_settlement_loop` 为 None。
    if quota_settlement_loop is not None:
        quota_settlement_loop.start()
    # 运行期日志与进度（docs/26 H-2、H-3）：容器日志只在终态归档的话，几小时的
    # MD 任务在页面上只有「运行中」三个字。这里按间隔增量拉日志、解析
    # `__DRP_PROGRESS__` 写回 task.progress，SSE 的 log/progress 帧随之生效。
    if runtime_log_sync_loop is not None:
        runtime_log_sync_loop.start()
    # 对象存储生命周期规则（docs/04 §5.8、docs/15 §3.2）：默认关闭。改桶配置属于
    # 运维动作（它会真的删 30 天前的暂存对象），应由部署脚本显式调用
    # `python -m app.cli.storage_lifecycle --apply` 并留痕，而不是每次重启都动一次生产存储。
    await ensure_lifecycle_on_startup()
    logger.info("数据库初始化完成")
    yield
    # 关闭时清理资源
    warmup = getattr(app.state, "worker_probe_warmup", None)
    if warmup is not None and not warmup.done():
        warmup.cancel()
    if runtime_log_sync_loop is not None:
        await runtime_log_sync_loop.stop()
    if quota_settlement_loop is not None:
        await quota_settlement_loop.stop()
    if queue_timeout_sweep_loop is not None:
        await queue_timeout_sweep_loop.stop()
    if idempotency_sweep_loop is not None:
        await idempotency_sweep_loop.stop()
    if artifact_gc_loop is not None:
        await artifact_gc_loop.stop()
    if upload_sweep_loop is not None:
        await upload_sweep_loop.stop()
    await audit_writer.stop()
    await workflow_reconcile_loop.stop()
    if use_direct_task_execution():
        await direct_task_recovery_loop.stop()
        await direct_task_runner.shutdown()
    if managed_runtime is not None:
        await managed_runtime.close()
    logger.info("应用关闭")


# 全局异常处理器
async def app_exception_handler(request: Request, exc: AppException):
    """处理应用异常"""
    # ``BusinessException`` 携带独立 ``http_status``（信封业务码与 HTTP 状态可不同）；
    # 其余 AppException 仍以 code 作为 HTTP 状态。
    status_code = getattr(exc, "http_status", None) or exc.code
    response = JSONResponse(
        status_code=status_code,
        content={
            "code": exc.code,
            "message": exc.message,
            "data": None,
            "detail": exc.detail,
            # docs/05 §1.2：失败信封与成功信封字段一致，只是 code 非 0。
            "requestId": get_trace_id(),
            "timestamp": isoformat_utc(utcnow()),
        }
    )
    # 刷新失败（含 40103 统一认证会话失效）必须顺手清掉三个认证 Cookie：
    # 端点里的 set/delete_cookie 写在依赖注入的 Response 上，一旦抛异常 FastAPI 会
    # 改用这个新 response 走异常处理器，原来那些 Set-Cookie 头全部丢失。不在这里清，
    # 前端就还攥着可用的 refresh Cookie，会形成「刷新→401→再刷新」的死循环。
    path = getattr(getattr(request, "url", None), "path", "") or ""
    if status_code == 401 and path.rstrip("/").endswith("/auth/refresh"):
        clear_auth_cookies(response)
    return response


async def http_exception_handler(request: Request, exc: StarletteHTTPException):
    """把 ``HTTPException`` 也纳入统一错误信封（计划 §3.3）。

    业务里散布着大量 ``raise HTTPException(status_code=..., detail=...)``；此前它们
    走 Starlette 默认处理器返回裸 ``{"detail": ...}``，与 ``AppException`` 的信封
    不一致。这里统一改写成 ``error_response``：

    * ``detail`` 是字符串时就是给用户看的 ``message``；
    * ``detail`` 是结构化对象时（如 ``{"currentVersion": 2}``）保留到 ``detail`` 字段，
      ``message`` 给一句通用文案，避免把 dict ``str()`` 成不可读的字符串。
    """
    detail = exc.detail
    if isinstance(detail, str):
        # 保留 ``detail`` 字段（既有调用方/测试仍读 ``response.json()["detail"]``），
        # 同时把同一段文案放进 ``message``，让统一信封对前端可用。
        content = error_response(message=detail, code=exc.status_code, detail=detail)
    else:
        content = error_response(
            message="请求失败", code=exc.status_code, detail=detail
        )
    headers = getattr(exc, "headers", None)
    return JSONResponse(
        status_code=exc.status_code, content=content, headers=headers
    )


async def validation_exception_handler(
    request: Request, exc: RequestValidationError
):
    """请求体/参数校验失败统一为 422 信封（计划 §3.3）。"""
    return JSONResponse(
        status_code=422,
        content=error_response(
            message="请求参数校验失败",
            code=422,
            detail=jsonable_encoder(exc.errors()),
        ),
    )


async def standard_artifact_registry_exception_handler(
    request: Request, exc: StandardArtifactRegistryError
):
    """标准 Artifact 注册表错误统一为 422 信封。

    放在全局而不是路由层：``standard_type``/``standard_version`` 的解析散落在
    Artifact 创建、任务输入校验等多条路径上，逐个路由 try/except 会漏掉未来新增
    的入口；这里把领域层的 ``ValueError`` 子类一次收口，保持 ``AppException`` 一样
    的 ``{code,message,data,detail}`` 形状。未知 ``standard_type`` 以前会冒泡到
    500，对调用方来说是「服务端坏了」，语义上是「参数不对」。
    """
    return JSONResponse(
        status_code=422,
        content=error_response(message=str(exc), code=422, detail=str(exc)),
    )


async def general_exception_handler(request: Request, exc: Exception):
    """处理未知异常

    这条路径上的 traceId 有两个坑，都必须显式处理：

    1. 本处理器由 Starlette 的 ``ServerErrorMiddleware`` 调用，它在中间件栈的**最外层**，
       trace 中间件已经把 contextvar 复位了 —— 所以不能只读 contextvar，要先从
       ``request.scope["state"]``（trace 中间件写进去的那份）取；
    2. 同一个原因，``ServerErrorMiddleware`` 用的是它自己拿到的 ``send``，绕过了 trace
       中间件的响应头注入 —— 所以这里必须自己回写 ``X-Request-Id``，否则 500 响应
       是唯一一个「有 requestId 却没有同名响应头」的响应。
    """
    trace_id = _trace_id_from_scope(request) or get_trace_id()
    logger.error(
        "Unhandled API exception: %s %s trace_id=%s",
        request.method,
        request.url.path,
        trace_id or "-",
        exc_info=exc,
    )
    return JSONResponse(
        status_code=500,
        headers={TRACE_ID_HEADER: trace_id} if trace_id else None,
        content={
            "code": 500,
            "message": "服务器内部错误",
            "data": None,
            "detail": str(exc) if settings.DEBUG else None,
            "requestId": trace_id,
            "timestamp": isoformat_utc(utcnow()),
        }
    )


class ForwardedProtoHTTPSRedirectMiddleware(BaseHTTPMiddleware):
    """生产环境强制 HTTPS，并尊重反向代理写入的 ``X-Forwarded-Proto``。

    Starlette 自带的 ``HTTPSRedirectMiddleware`` 只看 ASGI scope 的 scheme；
    在 nginx/负载均衡终止 TLS 的部署里 scope 仍是 http，会把已经加密的请求
    反复重定向。这里优先读取代理头后再判断。
    """

    EXEMPT_PATHS = {"/health", "/api/v1/system/health"}

    async def dispatch(self, request: Request, call_next):
        if request.url.path in self.EXEMPT_PATHS:
            return await call_next(request)
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        scheme = (
            forwarded_proto.split(",", 1)[0].strip().lower()
            if forwarded_proto
            else request.url.scheme
        )
        if scheme == "https":
            return await call_next(request)
        return RedirectResponse(
            url=str(request.url.replace(scheme="https")), status_code=307
        )


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    """统一安全响应头；HSTS 只在生产且请求已经 HTTPS 时下发。"""

    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        forwarded_proto = request.headers.get("x-forwarded-proto", "")
        scheme = (
            forwarded_proto.split(",", 1)[0].strip().lower()
            if forwarded_proto
            else request.url.scheme
        )
        if settings.ENVIRONMENT == "production" and scheme == "https":
            response.headers.setdefault(
                "Strict-Transport-Security", "max-age=31536000; includeSubDomains"
            )
        return response


async def health_check():
    """进程级健康检查（保留模块级函数供既有调用方/测试使用）。"""
    return {
        "status": "healthy",
        "version": settings.APP_VERSION,
    }


def create_app() -> FastAPI:
    """按当前 ``settings`` 构建 FastAPI 应用。

    拆成工厂函数是为了让「生产关文档 / 开发开文档」的差异可被测试直接构造
    验证，而不是只能靠改环境变量后重启进程。
    """
    docs_enabled = settings.docs_enabled
    application = FastAPI(
        title=settings.APP_NAME,
        description="科学计算工具管理平台API",
        version=settings.APP_VERSION,
        docs_url="/docs" if docs_enabled else None,
        redoc_url="/redoc" if docs_enabled else None,
        openapi_url="/openapi.json" if docs_enabled else None,
        lifespan=lifespan,
    )

    # 先注册限流，再注册 CORS，确保限流响应仍带有 CORS 响应头。
    application.add_middleware(
        RateLimitMiddleware,
        cache_client=get_cache(),
        requests_per_minute=settings.REQUEST_RATE_LIMIT_PER_MINUTE,
        trust_proxy_headers=settings.RATE_LIMIT_TRUST_PROXY_HEADERS,
        backend=settings.resolved_rate_limit_backend,
        fail_mode=settings.RATE_LIMIT_FAIL_MODE,
    )

    # 配置 CORS
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Host 头白名单：生产必须显式配置（config 层已拒绝 "*" 与空值）。
    application.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=settings.ALLOWED_HOSTS,
    )

    if settings.https_redirect_enabled:
        application.add_middleware(ForwardedProtoHTTPSRedirectMiddleware)

    application.add_middleware(SecurityHeadersMiddleware)

    # Prometheus 指标：放在 trace 之外、限流之内，能记录到 429 与业务请求；
    # /metrics 是内部抓取端点，不进 OpenAPI。默认始终开启（内部部署）。
    if settings.METRICS_ENABLED:
        application.add_middleware(PrometheusMiddleware)

    # traceId 中间件必须**最后注册**，也就是最外层（Starlette 的 ``add_middleware`` 是
    # ``user_middleware.insert(0, ...)``，建栈时再 reverse 包一层）。这样请求路径是
    # TraceId → SecurityHeaders → HTTPS → TrustedHost → CORS → RateLimit → 路由：
    # 限流中间件拒掉的 429 也会经过本中间件回写 ``X-Request-Id``，CORS 仍然包在
    # 限流外面，不影响 429 的 CORS 头。
    application.add_middleware(TraceIdMiddleware)

    application.add_exception_handler(AppException, app_exception_handler)
    application.add_exception_handler(
        StarletteHTTPException, http_exception_handler
    )
    application.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    application.add_exception_handler(
        StandardArtifactRegistryError, standard_artifact_registry_exception_handler
    )
    application.add_exception_handler(Exception, general_exception_handler)

    # 注册API路由
    application.include_router(api_router, prefix="/api/v1")

    if settings.METRICS_ENABLED:
        application.add_api_route(
            "/metrics",
            metrics_endpoint,
            methods=["GET"],
            include_in_schema=False,
        )

    # 根路径
    @application.get("/")
    async def root():
        """根路径"""
        payload = {
            "name": settings.APP_NAME,
            "version": settings.APP_VERSION,
            "status": "running",
        }
        if settings.docs_enabled:
            payload["docs"] = "/docs"
        return payload

    # 健康检查
    @application.get("/health")
    async def health_check_endpoint():
        """健康检查"""
        return await health_check()

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.DEBUG
    )
