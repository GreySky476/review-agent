"""DeepSeek AI Provider 实现。"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
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
    """DeepSeek API 调用实现。

    支持 deepseek-v4-flash 和 deepseek-v4-pro 模型。
    """

    def __init__(self, api_key: str | None = None, base_url: str | None = None) -> None:
        settings = get_settings()
        self._api_key = api_key or settings.ai_api_key
        self._base_url = base_url or settings.ai_base_url

    async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
        """调用 DeepSeek 聊天补全 API。

        Args:
            request: 补全请求。

        Returns:
            补全响应。

        Raises:
            AIProviderError: API 返回错误或网络异常时抛出。
        """
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
                async with httpx.AsyncClient(timeout=timeout) as client:
                    resp = await client.post(url, headers=headers, json=payload)
                    resp.raise_for_status()
                    data = resp.json()
                return _parse_completion_response(data, request)
            except httpx.TimeoutException:
                last_exception = AIProviderError("DeepSeek request timed out")
            except httpx.HTTPStatusError as exc:
                if exc.response.status_code >= 500:
                    msg = f"DeepSeek returned {exc.response.status_code}"
                    last_exception = AIProviderError(msg)
                else:
                    msg = (
                        f"DeepSeek returned {exc.response.status_code}: "
                        f"{exc.response.text[:200]}"
                    )
                    raise AIProviderError(msg) from exc
            except httpx.RequestError as exc:
                last_exception = AIProviderError(f"DeepSeek request failed: {exc}")

            if attempt < max_attempts - 1:
                wait = min(2**attempt * 5, 60)
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
