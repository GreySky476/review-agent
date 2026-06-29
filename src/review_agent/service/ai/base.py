"""AI Provider 抽象基类 + 熔断器。"""

from __future__ import annotations

import asyncio
import logging
import time
from abc import ABC, abstractmethod

from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse
from review_agent.types.exceptions import AIProviderError

logger = logging.getLogger(__name__)


class AIProviderCircuitBreaker:
    """AI Provider 三态熔断器。

    保护下游 AI 服务免受过载请求冲击：
    - closed: 正常放行
    - open: 连续失败 N 次后断开，拒绝请求 60s
    - half-open: 60s 后允许 1 次探测请求
    """

    def __init__(
        self,
        failure_threshold: int = 3,
        recovery_timeout: float = 60.0,
    ) -> None:
        self._state: str = "closed"
        self._failure_count: int = 0
        self._last_failure_time: float = 0.0
        self._failure_threshold = failure_threshold
        self._recovery_timeout = recovery_timeout
        self._lock = asyncio.Lock()

    @property
    def state(self) -> str:
        """当前熔断器状态。"""
        return self._state

    async def before_call(self) -> None:
        """检查调用是否允许。open 状态时抛出 AIProviderError。"""
        async with self._lock:
            if self._state == "open":
                elapsed = time.monotonic() - self._last_failure_time
                if elapsed >= self._recovery_timeout:
                    self._state = "half_open"
                    logger.info("Circuit breaker: open → half_open (%.1fs elapsed)", elapsed)
                else:
                    remaining = self._recovery_timeout - elapsed
                    msg = f"Circuit breaker is OPEN — rejecting call. Retry in {remaining:.0f}s"
                    raise AIProviderError(msg)

    async def on_success(self) -> None:
        """调用成功时重置状态。"""
        async with self._lock:
            if self._state != "closed":
                logger.info("Circuit breaker: %s → closed (success)", self._state)
            self._state = "closed"
            self._failure_count = 0

    async def on_failure(self) -> None:
        """调用失败时记录并可能断开。"""
        async with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.monotonic()
            if self._failure_count >= self._failure_threshold:
                if self._state != "open":
                    logger.warning(
                        "Circuit breaker: %s → open (%d consecutive failures)",
                        self._state,
                        self._failure_count,
                    )
                self._state = "open"


class AIProvider(ABC):
    """AI 模型调用抽象。

    所有 AI 模型提供方（DeepSeek、Claude、OpenAI 等）需实现此接口。
    """

    @abstractmethod
    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """发送对话补全请求。

        Args:
            request: 补全请求参数。

        Returns:
            补全响应。

        Raises:
            AIProviderError: 调用失败时抛出（超时、鉴权、限流等）。
        """
        ...

    @abstractmethod
    async def count_tokens(self, text: str, model: str | None = None) -> int:
        """估算文本的 Token 数。

        Args:
            text: 待估算文本。
            model: 模型名称（不同模型 tokenizer 可能不同）。

        Returns:
            Token 数量。
        """
        ...
