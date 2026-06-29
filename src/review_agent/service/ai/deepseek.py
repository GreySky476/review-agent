"""DeepSeek AI Provider 实现 — 含熔断器、429 重试、抖动退避。"""

from __future__ import annotations

import asyncio
import json
import logging
import random
from typing import Any

import httpx

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider, AIProviderCircuitBreaker
from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse
from review_agent.types.exceptions import AIProviderError

logger = logging.getLogger(__name__)


def _parse_completion_response(
    data: dict[str, Any], request: AICompletionRequest
) -> AICompletionResponse:
    """Parse raw API response dict into an AICompletionResponse.

    Args:
        data: Raw JSON response from the DeepSeek API.
        request: Original completion request (for fallback model name).

    Returns:
        Parsed completion response.

    Raises:
        AIProviderError: If the response format is unexpected.
    """
    try:
        content = data["choices"][0]["message"]["content"]
        usage = data.get("usage")
    except (KeyError, IndexError) as exc:
        msg = f"Unexpected DeepSeek response format: {json.dumps(data)}"
        raise AIProviderError(msg) from exc

    return AICompletionResponse(
        content=content,
        model=data.get("model", request.model),
        usage=usage,
        raw=data,
    )


class DeepSeekProvider(AIProvider):  # type: ignore[misc]
    """DeepSeek API 调用实现 — 含三态熔断器。

    支持 deepseek-v4-flash 和 deepseek-v4-pro 模型。
    内置 429 速率限制重试（遵循 Retry-After 头）和指数退避抖动。
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.ai_api_key
        self._base_url = base_url or settings.ai_base_url
        self._circuit_breaker = AIProviderCircuitBreaker(
            failure_threshold=settings.ai_cb_failure_threshold,
            recovery_timeout=float(settings.ai_cb_recovery_timeout),
        )

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """调用 DeepSeek 聊天补全 API（带熔断器保护）。

        Args:
            request: 补全请求。

        Returns:
            补全响应。

        Raises:
            AIProviderError: API 返回错误、网络异常或熔断器断开时抛出。
        """
        await self._circuit_breaker.before_call()
        try:
            result = await self._complete_impl(request)
        except AIProviderError:
            await self._circuit_breaker.on_failure()
            raise
        except Exception:
            await self._circuit_breaker.on_failure()
            raise
        else:
            await self._circuit_breaker.on_success()
        return result

    async def _complete_impl(self, request: AICompletionRequest) -> AICompletionResponse:
        """内部补全实现（含重试逻辑）。"""
        import time as time_module

        url = f"{self._base_url}/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        payload: dict[str, Any] = {
            "model": request.model,
            "messages": [{"role": m.role, "content": m.content} for m in request.messages],
            "temperature": request.temperature,
            "max_tokens": request.max_tokens,
        }

        settings = get_settings()
        timeout = httpx.Timeout(
            connect=settings.ai_connect_timeout,
            read=settings.ai_read_timeout,
            write=settings.ai_connect_timeout,
            pool=settings.ai_connect_timeout,
        )

        max_attempts = settings.ai_max_retries + 1
        last_exception: Exception | None = None

        for attempt in range(max_attempts):
            try:
                t0 = time_module.monotonic()
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                elapsed = time_module.monotonic() - t0
                result = _parse_completion_response(data, request)
                usage = data.get("usage", {})
                logger.info(
                    "ai_request: model=%s prompt_tok=%d completion_tok=%d total_tok=%d "
                    "elapsed=%.1fs",
                    data.get("model", request.model),
                    usage.get("prompt_tokens", 0),
                    usage.get("completion_tokens", 0),
                    usage.get("total_tokens", 0),
                    elapsed,
                )
                return result
            except httpx.TimeoutException:
                last_exception = AIProviderError("DeepSeek request timed out")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code == 429:
                    # 速率限制：提取 Retry-After 头并等待
                    retry_after_hdr = exc.response.headers.get("Retry-After", "5")
                    try:
                        retry_after = float(retry_after_hdr)
                    except ValueError:
                        retry_after = 5.0
                    jitter = random.uniform(0, max(retry_after * 0.1, 0.5))
                    wait = retry_after + jitter
                    logger.warning(
                        "DeepSeek rate limited (429). Retry-After=%.1fs, "
                        "waiting %.1fs (attempt %d/%d)",
                        retry_after,
                        wait,
                        attempt + 1,
                        max_attempts,
                    )
                    last_exception = AIProviderError(
                        f"DeepSeek rate limited: {exc.response.text[:200]}"
                    )
                    await asyncio.sleep(wait)
                    continue
                if exc.response.status_code >= 500:
                    msg = f"DeepSeek returned {exc.response.status_code}"
                    last_exception = AIProviderError(msg)
                else:
                    msg = f"DeepSeek returned {exc.response.status_code}: {exc.response.text[:200]}"
                    raise AIProviderError(msg) from exc
            except httpx.RequestError as exc:
                last_exception = AIProviderError(f"DeepSeek request failed: {exc}")

            if attempt < max_attempts - 1:
                # 指数退避 + 随机抖动：wait 在 50%-150% 之间波动
                base_wait = min(2**attempt * 5, 60)
                wait = base_wait * (0.5 + random.random())
                logger.debug(
                    "DeepSeek retry %d/%d after %.1fs",
                    attempt + 1,
                    max_attempts - 1,
                    wait,
                )
                await asyncio.sleep(wait)

        raise last_exception  # type: ignore[misc]

    async def count_tokens(self, text: str, model: str | None = None) -> int:
        """估算文本 Token 数。

        Args:
            text: 待估算文本。
            model: 模型名称（用于后续 tokenizer 选择）。

        Returns:
            预估的 Token 数。
        """
        _ = model  # reserved for tokenizer selection
        char_count = len(text)
        return max(1, char_count // 3)
