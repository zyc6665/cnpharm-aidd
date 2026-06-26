# backend/app/exceptions/external_api.py
"""外部API异常处理

根据详细设计说明书 8.1 节实现。
负责处理外部API调用的各类异常和重试逻辑。
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional, TypeVar, Union
import asyncio
import logging
import random
from app.common.exceptions import AppException
from app.common.time import utcnow

logger = logging.getLogger(__name__)

T = TypeVar("T")


class ExternalAPIException(AppException):
    """外部API异常基类"""

    def __init__(
        self,
        message: str,
        api_name: Optional[str] = None,
        status_code: Optional[int] = None,
        response_body: Optional[str] = None
    ):
        super().__init__(message, code=status_code or 500, detail=response_body)
        self.api_name = api_name
        self.status_code = status_code
        self.response_body = response_body

    def to_dict(self) -> Dict[str, Any]:
        return {
            "error_type": self.__class__.__name__,
            "message": self.message,
            "api_name": self.api_name,
            "status_code": self.status_code
        }


class APITimeoutException(ExternalAPIException):
    """API超时异常"""
    pass


class APIConnectionException(ExternalAPIException):
    """API连接异常"""
    pass


class APIRateLimitException(ExternalAPIException):
    """API限流异常"""

    def __init__(
        self,
        message: str,
        retry_after: Optional[int] = None,
        **kwargs
    ):
        super().__init__(message, **kwargs)
        self.retry_after = retry_after


class APIResponseException(ExternalAPIException):
    """API响应异常"""
    pass


class APIAuthException(ExternalAPIException):
    """API认证异常"""
    pass


@dataclass
class RetryConfig:
    """重试配置"""
    max_retries: int = 3
    base_delay: float = 1.0          # 基础延迟（秒）
    max_delay: float = 60.0          # 最大延迟（秒）
    exponential_base: float = 2.0    # 指数基数
    jitter: bool = True              # 是否添加抖动
    retry_on: tuple = (              # 可重试的异常类型
        APITimeoutException,
        APIConnectionException,
        APIRateLimitException
    )


class ExternalAPIHandler:
    """外部API调用处理器

    功能：
    1. 统一的API调用封装
    2. 自动重试机制
    3. 超时处理
    4. 限流检测
    5. 日志记录
    """

    DEFAULT_TIMEOUT = 30.0

    def __init__(
        self,
        api_name: str,
        retry_config: Optional[RetryConfig] = None,
        timeout: float = DEFAULT_TIMEOUT
    ):
        """初始化API处理器

        Args:
            api_name: API名称
            retry_config: 重试配置
            timeout: 默认超时时间
        """
        self.api_name = api_name
        self.retry_config = retry_config or RetryConfig()
        self.timeout = timeout

    async def call_with_retry(
        self,
        func: Callable[..., T],
        *args,
        timeout: Optional[float] = None,
        **kwargs
    ) -> T:
        """带重试的API调用

        Args:
            func: 异步函数
            *args: 位置参数
            timeout: 超时时间
            **kwargs: 关键字参数

        Returns:
            T: 函数返回值

        Raises:
            ExternalAPIException: API调用失败
        """
        timeout = timeout or self.timeout
        last_exception = None

        for attempt in range(self.retry_config.max_retries + 1):
            try:
                # 带超时的调用
                result = await asyncio.wait_for(
                    func(*args, **kwargs),
                    timeout=timeout
                )

                # 成功后记录
                if attempt > 0:
                    logger.info(
                        f"API call succeeded after {attempt} retries",
                        extra={"api_name": self.api_name, "attempt": attempt}
                    )

                return result

            except asyncio.TimeoutError:
                last_exception = APITimeoutException(
                    message=f"API call timed out after {timeout}s",
                    api_name=self.api_name
                )

            except APIRateLimitException as e:
                last_exception = e
                # 使用服务器返回的重试时间
                if e.retry_after:
                    delay = e.retry_after
                else:
                    delay = self._calculate_delay(attempt)

                logger.warning(
                    f"Rate limited, waiting {delay}s before retry",
                    extra={
                        "api_name": self.api_name,
                        "attempt": attempt,
                        "delay": delay
                    }
                )

                await asyncio.sleep(delay)
                continue

            except tuple(self.retry_config.retry_on) as e:
                last_exception = e

            except Exception as e:
                # 不可重试的异常直接抛出
                logger.error(
                    f"API call failed with non-retryable error: {e}",
                    extra={"api_name": self.api_name}
                )
                raise ExternalAPIException(
                    message=str(e),
                    api_name=self.api_name
                ) from e

            # 计算重试延迟
            if attempt < self.retry_config.max_retries:
                delay = self._calculate_delay(attempt)
                logger.warning(
                    f"API call failed, retrying in {delay}s (attempt {attempt + 1}/{self.retry_config.max_retries})",
                    extra={
                        "api_name": self.api_name,
                        "attempt": attempt,
                        "delay": delay,
                        "error": str(last_exception)
                    }
                )
                await asyncio.sleep(delay)

        # 所有重试失败
        logger.error(
            f"API call failed after {self.retry_config.max_retries} retries",
            extra={"api_name": self.api_name, "error": str(last_exception)}
        )
        raise last_exception

    def _calculate_delay(self, attempt: int) -> float:
        """计算重试延迟

        使用指数退避算法。

        Args:
            attempt: 当前尝试次数

        Returns:
            float: 延迟时间（秒）
        """
        delay = self.retry_config.base_delay * (
            self.retry_config.exponential_base ** attempt
        )

        # 添加抖动
        if self.retry_config.jitter:
            delay = delay * (0.5 + random.random())

        # 限制最大延迟
        return min(delay, self.retry_config.max_delay)

    async def health_check(self, check_func: Callable) -> Dict[str, Any]:
        """API健康检查

        Args:
            check_func: 健康检查函数

        Returns:
            Dict[str, Any]: 健康检查结果
        """
        try:
            start = utcnow()
            await asyncio.wait_for(check_func(), timeout=10.0)
            latency = (utcnow() - start).total_seconds() * 1000

            return {
                "api_name": self.api_name,
                "healthy": True,
                "latency_ms": latency
            }

        except Exception as e:
            return {
                "api_name": self.api_name,
                "healthy": False,
                "error": str(e)
            }


class APIFallbackHandler:
    """API降级处理器

    当主API不可用时，提供降级策略。
    """

    def __init__(self):
        """初始化降级处理器"""
        self._fallback_results: Dict[str, Any] = {}

    def register_fallback(
        self,
        api_name: str,
        fallback_value: Any
    ) -> None:
        """注册降级返回值

        Args:
            api_name: API名称
            fallback_value: 降级返回值
        """
        self._fallback_results[api_name] = fallback_value

    async def handle_tool_api_failure(
        self,
        tool_slug: str,
        error: ExternalAPIException,
        task_id: str
    ) -> Dict[str, Any]:
        """处理工具API调用失败

        Args:
            tool_slug: 工具标识
            error: 异常对象
            task_id: 任务ID

        Returns:
            Dict[str, Any]: 降级响应
        """
        logger.error(
            f"Tool API failed: {tool_slug}",
            extra={
                "tool_slug": tool_slug,
                "task_id": task_id,
                "error": error.to_dict()
            }
        )

        # 检查是否有注册的降级值
        fallback_key = f"tool:{tool_slug}"
        if fallback_key in self._fallback_results:
            return {
                "status": "degraded",
                "message": f"Using fallback result due to API failure: {error.message}",
                "result": self._fallback_results[fallback_key]
            }

        # 默认降级响应
        return {
            "status": "failed",
            "message": f"API call failed: {error.message}",
            "error_type": error.__class__.__name__,
            "retryable": isinstance(error, (APITimeoutException, APIConnectionException))
        }

    async def should_circuit_break(
        self,
        api_name: str,
        error_count: int,
        window_seconds: int = 60,
        threshold: int = 5
    ) -> bool:
        """判断是否应该熔断

        Args:
            api_name: API名称
            error_count: 错误计数
            window_seconds: 统计窗口
            threshold: 熔断阈值

        Returns:
            bool: 是否应该熔断
        """
        return error_count >= threshold


# 便捷函数
async def call_external_api(
    api_name: str,
    func: Callable[..., T],
    *args,
    timeout: float = 30.0,
    max_retries: int = 3,
    **kwargs
) -> T:
    """调用外部API的便捷函数

    Args:
        api_name: API名称
        func: 异步函数
        *args: 位置参数
        timeout: 超时时间
        max_retries: 最大重试次数
        **kwargs: 关键字参数

    Returns:
        T: 函数返回值
    """
    handler = ExternalAPIHandler(
        api_name=api_name,
        retry_config=RetryConfig(max_retries=max_retries),
        timeout=timeout
    )
    return await handler.call_with_retry(func, *args, **kwargs)
