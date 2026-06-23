"""统一的 AI 代码评审服务。

封装 AI 评审的 prompt 构造、模型调用、响应解析逻辑，
供 LangGraph 路径使用。
"""

from __future__ import annotations

import logging
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import AICompletionRequest, AIMessage, BatchReviewEntry
from review_agent.service.ai_resp_parser import parse_batch_response, parse_response
from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.service.error_logger import log_error
from review_agent.service.standards import load_standards

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

_AI_REVIEW_BASE_BATCH = (
    "你一次收到多个独立的代码块。请分别评审每个代码块，"
    "以 JSON 数组格式返回结果，不要包含其他内容：\n"
    "```json\n"
    "[\n"
    '  {"function_index": 0, "findings": [{\n'
    '    "severity": "critical|warning|info",\n'
    '    "title": "简短标题",\n'
    '    "description": "问题详细描述",\n'
    '    "suggestion": "修复建议",\n'
    '    "line": <行号或 null>\n'
    "  }]},\n"
    '  {"function_index": 1, "findings": []}\n'
    "]\n"
    "```\n"
    "如果没有发现任何问题，返回空数组 []。"
)


def _build_rules_block(rules: list[dict[str, Any]]) -> str:
    """构建企业自定义审查规则文本块。"""
    block = "## 企业自定义审查规则\n\n"
    for r in rules:
        sev = r.get("severity", "info").upper()
        name = r.get("name", "")
        content = r.get("content", "")
        rule_id = r.get("id", "")
        block += (
            f"- [{sev}] **{name}**: {content}"
            f"{'  (rule_id: ' + rule_id + ')' if rule_id else ''}\n"
        )
    block += (
        "\nAI 评审时请优先参照以上企业规则。命中规则的 finding 需标注对应的 rule_id。\n"
    )
    return block


def _merge_rules(entries: list[BatchReviewEntry]) -> list[dict[str, Any]]:
    """合并多条目的 matched_rules，按 rule id 去重。"""
    all_rules: list[dict[str, Any]] = []
    seen_rule_ids: set[str] = set()
    for entry in entries:
        if not entry.matched_rules:
            continue
        for r in entry.matched_rules:
            rid = r.get("id", "")
            if rid and rid not in seen_rule_ids:
                all_rules.append(r)
                seen_rule_ids.add(rid)
            elif not rid:
                all_rules.append(r)
    return all_rules


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

        system_parts: list[str] = self._build_system_parts(chunk.file_path, matched_rules)
        system_parts.append(_AI_REVIEW_BASE_PROMPT)
        system_prompt = "\n\n".join(system_parts)

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
            return parse_response(response.content, chunk)
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

    def _build_system_parts(
        self,
        file_path: str,
        matched_rules: list[dict[str, Any]] | None = None,
    ) -> list[str]:
        """构建 system prompt 的各个部分（不含结尾的输出格式说明）。"""
        parts: list[str] = []
        lang_standards = load_standards(file_path)
        if lang_standards:
            parts.append(f"## 语言特定代码评审规范\n\n{lang_standards}")

        if matched_rules:
            parts.append(_build_rules_block(matched_rules))

        parts.append(
            "你是一位资深代码评审专家。请严格参照上述规范审查下方的代码变更，"
            "找出其中的违规项、正确性缺陷、安全风险、错误处理遗漏和逻辑错误。"
        )
        return parts

    async def review_chunks(
        self,
        entries: list[BatchReviewEntry],
    ) -> list[list[DimensionFinding]]:
        """一次 LLM 调用评审多个代码块。

        Args:
            entries: 待评审的批量条目列表。

        Returns:
            与 entries 一一对应的 findings 列表。
        """
        if self._ai is None or not entries:
            return [[] for _ in entries]

        system_parts = self._build_system_parts(entries[0].file_path)
        merged_rules = _merge_rules(entries)
        if merged_rules:
            system_parts.append(_build_rules_block(merged_rules))
        system_parts.append(_AI_REVIEW_BASE_BATCH)
        system_prompt = "\n\n".join(system_parts)

        user_parts: list[str] = []
        for i, entry in enumerate(entries):
            header = f"## Function {i}: {entry.file_path}/{entry.function_name}"
            user_parts.append(f"{header}\n```\n{entry.source_code}\n```")
            if entry.patch:
                user_parts.append(f"### Diff for function {i}\n```diff\n{entry.patch}\n```")
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
            return parse_batch_response(response.content, entries)
        except Exception as exc:
            logger.warning(
                "Batch AI review failed for %d entries: %s",
                len(entries),
                exc,
            )
            await log_error(
                error_type="ai_call_failed",
                error_message=f"Batch AI review failed for {len(entries)} entries: {exc}",
            )
            return [[] for _ in entries]
