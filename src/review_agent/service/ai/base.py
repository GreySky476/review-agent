"""AI Provider 抽象基类。"""

from __future__ import annotations

from abc import ABC, abstractmethod

from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse


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
