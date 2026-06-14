"""统一的 AI 代码评审服务。

封装 AI 评审的 prompt 构造、模型调用、响应解析逻辑，
供 CommitReviewService（非 LangGraph 路径）和 LangGraph 路径共同使用。
"""

from __future__ import annotations

import contextlib
import json
import logging
import re
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import AICompletionRequest, AIMessage
from review_agent.service.chunking import CodeChunk, adjust_line_number
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.service.error_logger import log_error
from review_agent.service.standards import load_standards
from review_agent.types.enums import FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)

_AI_REVIEW_BASE_PROMPT = (
    "以 JSON 数组格式返回结果，不要包含其他内容：\n"
    "```json\n"
    "[\n"
    "  {\n"
    '    "severity": "critical|warning|info",\n'
    '    "title": "简短标题",\n'
    '    "description": "问题详细描述",\n'
    '    "suggestion": "修复建议",\n'
    '    "line": <行号或 null>\n'
    "  }\n"
    "]\n"
    "```\n"
    "如果没有发现问题，返回空数组 []。"
)

_SEVERITY_MAP = {
    "critical": FindingSeverity.CRITICAL,
    "warning": FindingSeverity.WARNING,
    "info": FindingSeverity.INFO,
}


class AIReviewer:
    """AI 代码评审器。

    负责构造 AI 评审 prompt（含语言特定规范 + 企业自定义规则）、
    调用 AI 模型、解析 JSON 响应为 DimensionFinding 列表。
    """

    def __init__(self, ai_provider: AIProvider | None = None) -> None:
        self._ai = ai_provider
        self._settings = get_settings()

    async def review_chunk(
        self,
        chunk: CodeChunk,
        patch: str | None = None,
        matched_rules: list[dict[str, Any]] | None = None,
    ) -> list[DimensionFinding]:
        """评审单个代码块，返回 findings。

        Args:
            chunk: 待评审代码块。
            patch: 文件 diff（可选），用于提供变更上下文。
            matched_rules: 知识库匹配的企业自定义规则（可选）。

        Returns:
            评审发现的问题列表。
        """
        if self._ai is None:
            return []

        # 构建 system prompt
        lang_standards = load_standards(chunk.file_path)
        system_parts: list[str] = []
        if lang_standards:
            system_parts.append(f"## 语言特定代码评审规范\n\n{lang_standards}")

        if matched_rules:
            rules_block = "## 企业自定义审查规则\n\n"
            for r in matched_rules:
                sev = r.get("severity", "info").upper()
                name = r.get("name", "")
                content = r.get("content", "")
                rule_id = r.get("id", "")
                rules_block += (
                    f"- [{sev}] **{name}**: {content}"
                    f"{'  (rule_id: ' + rule_id + ')' if rule_id else ''}\n"
                )
            rules_block += (
                "\nAI 评审时请优先参照以上企业规则。命中规则的 finding 需标注对应的 rule_id。\n"
            )
            system_parts.append(rules_block)

        system_parts.append(
            "你是一位资深代码评审专家。请严格参照上述规范审查下方的代码变更，"
            "找出其中的违规项、正确性缺陷、安全风险、错误处理遗漏和逻辑错误。"
        )
        system_parts.append(_AI_REVIEW_BASE_PROMPT)
        system_prompt = "\n\n".join(system_parts)

        # 构建 user prompt
        user_parts = [
            f"## 函数源码（{chunk.file_path}）\n```\n{chunk.source_code}\n```",
        ]
        if patch:
            user_parts.append(f"## Diff\n```diff\n{patch}\n```")
        user_prompt = "\n\n".join(user_parts)

        request = AICompletionRequest(
            model=self._settings.ai_model_name,
            messages=[
                AIMessage(role="system", content=system_prompt),
                AIMessage(role="user", content=user_prompt),
            ],
            temperature=0.1,
            max_tokens=self._settings.ai_review_max_tokens,
            timeout_seconds=self._settings.ai_request_timeout,
        )

        try:
            response = await self._ai.complete(request)
            return self._parse_response(response.content, chunk)
        except Exception as exc:
            logger.warning(
                "AI review failed for %s/%s: %s",
                chunk.file_path,
                chunk.function_name,
                exc,
            )
            await log_error(
                error_type="ai_call_failed",
                error_message=(
                    f"AI review failed for {chunk.file_path}:{chunk.function_name}: {exc}"
                ),
            )
            return []

    @staticmethod
    def _parse_response(content: str, chunk: CodeChunk) -> list[DimensionFinding]:
        """从 AI 响应中解析 findings。

        支持三种格式，按优先级尝试：
        1. 被 ```json ... ``` markdown 包裹的 JSON
        2. 从内容中提取第一个 `[...]` 数组（找到第一个 `[` 和最后一个 `]`）
        3. 直接解析整个内容
        """
        raw_findings: list[dict[str, Any]] | None = None

        # 尝试 1: markdown 代码块包裹
        json_match = re.search(r"```(?:json)?\s*\[[\s\S]*?\]\s*```", content)
        if json_match:
            block = json_match.group(0)
            inner = re.search(r"\[[\s\S]*\]", block)
            if inner:
                with contextlib.suppress(json.JSONDecodeError):
                    raw_findings = json.loads(inner.group(0))

        # 尝试 2: 提取第一个 [ 和最后一个 ]
        if raw_findings is None:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                with contextlib.suppress(json.JSONDecodeError):
                    raw_findings = json.loads(content[start : end + 1])

        # 尝试 3: 直接解析全文
        if raw_findings is None:
            with contextlib.suppress(json.JSONDecodeError):
                raw_findings = json.loads(content.strip())

        if raw_findings is None:
            preview = (content[:300] + "...") if content else "<empty response>"
            logger.warning(
                "Failed to parse AI response as JSON for %s: %s",
                chunk.file_path,
                preview,
            )
            return []

        if not isinstance(raw_findings, list):
            logger.warning(
                "AI response for %s is not a list (type=%s): %.200s",
                chunk.file_path,
                type(raw_findings).__name__,
                content[:200],
            )
            return []

        findings: list[DimensionFinding] = []
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            severity_str = item.get("severity", "info")
            findings.append(
                DimensionFinding(
                    category=FindingCategory.BUG,
                    severity=_SEVERITY_MAP.get(severity_str, FindingSeverity.INFO),
                    title=item.get("title", "未命名问题"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    file_path=chunk.file_path,
                    line_start=adjust_line_number(chunk, item.get("line")),
                )
            )

        return findings
