"""AI Provider 的数据模型。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class AIMessage:
    """AI 对话消息。"""

    role: str  # "system" | "user" | "assistant"
    content: str


@dataclass
class AICompletionRequest:
    """AI 补全请求参数。"""

    model: str
    messages: list[AIMessage]
    temperature: float = 0.1
    max_tokens: int = 4096
    timeout_seconds: int = 30


@dataclass
class AICompletionResponse:
    """AI 补全响应。"""

    content: str
    model: str
    usage: dict[str, int] | None = None
    raw: dict[str, Any] | None = None


@dataclass
class BatchReviewEntry:
    """批量评审中的单个 chunk 上下文。"""

    file_path: str
    function_name: str | None
    source_code: str
    start_line: int
    end_line: int
    estimated_tokens: int
    patch: str | None = None
    matched_rules: list[dict[str, Any]] | None = None
