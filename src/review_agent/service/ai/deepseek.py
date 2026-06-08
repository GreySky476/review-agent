"""DeepSeek AI Provider 实现。"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse
from review_agent.types.exceptions import AIProviderError

logger = logging.getLogger(__name__)


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

        try:
            async with httpx.AsyncClient(timeout=request.timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
                response.raise_for_status()
                data = response.json()
        except httpx.TimeoutException as exc:
            msg = f"DeepSeek request timed out after {request.timeout_seconds}s"
            raise AIProviderError(msg) from exc
        except httpx.HTTPStatusError as exc:
            msg = f"DeepSeek API returned {exc.response.status_code}: {exc.response.text}"
            raise AIProviderError(msg) from exc
        except httpx.RequestError as exc:
            msg = f"DeepSeek request failed: {exc}"
            raise AIProviderError(msg) from exc

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
