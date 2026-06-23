"""统一的 AI 代码评审服务。

封装 AI 评审的 prompt 构造、模型调用、响应解析逻辑，
供 CommitReviewService（非 LangGraph 路径）和 LangGraph 路径共同使用。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import AICompletionRequest, AIMessage, BatchReviewEntry
from review_agent.service.ai_resp_parser import parse_batch_response
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
    '    "category": "bug|security|performance",\n'
    '    "severity": "critical|warning",\n'
    '    "title": "简短标题",\n'
    '    "description": "问题详细描述，包含问题代码片段",\n'
    '    "suggestion": "具体的修改建议和代码示例",\n'
    '    "line": <行号>\n'
    "  }\n"
    "]\n"
    "```\n"
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
            "找出其中的正确性缺陷(Bug)、安全风险(Security)和性能问题(Performance)。"
            "对每个问题必须给出具体的修复建议和代码示例。"
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

        # 估算总 prompt tokens（含 system prompt）
        system_tokens = max(1, len(system_prompt) // 2)
        total_estimated = system_tokens + (chunk.estimated_tokens or 0)
        max_tokens = self._settings.ai_review_max_tokens
        if total_estimated > max_tokens * 0.9:
            logger.warning(
                "Estimated tokens %d (system=%d + chunk=%d) approaching limit %d "
                "for %s/%s, may cause timeout",
                total_estimated,
                system_tokens,
                chunk.estimated_tokens,
                max_tokens,
                chunk.file_path,
                chunk.function_name,
            )

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

    async def review_chunks(
        self,
        entries: list[BatchReviewEntry],
    ) -> list[list[DimensionFinding]]:
        """批量评审多个代码块，一次 AI 调用完成所有评审。

        适用于同一轮评审中多个代码块可合并为一次 AI 调用的场景，
        减少 API 调用次数。每个 entry 通过 function_index 映射回各自的 findings。

        Args:
            entries: 待评审的批量条目列表。

        Returns:
            每个 entry 对应的 DimensionFinding 列表（list[list]，
            与 entries 等长，未命中的 entry 返回空列表）。
        """
        if self._ai is None or not entries:
            return [[] for _ in entries]

        # 构建批量 prompt（使用 batch 专用格式，不继承 _AI_REVIEW_BASE_PROMPT）
        _batch_response_format = (
            "以 JSON 数组格式返回结果，不要包含其他内容：\n"
            "```json\n"
            "[\n"
            "  {\n"
            '    "function_index": 0,\n'
            '    "findings": [\n'
            "      {\n"
            '        "category": "bug|security|performance",\n'
            '        "severity": "critical|warning",\n'
            '        "title": "简短标题",\n'
            '        "description": "问题详细描述，包含问题代码片段",\n'
            '        "suggestion": "具体的修改建议和代码示例",\n'
            '        "line": <行号>\n'
            "      }\n"
            "    ]\n"
            "  },\n"
            "  ...\n"
            "]\n"
            "```\n"
            "function_index 对应下方代码块的编号。"
            "对没有发现问题的函数，返回 function_index 和空 findings 数组。"
        )
        system_parts: list[str] = [
            "你是一位资深代码评审专家，请对下方多个代码块逐一进行评审。"
            "只关注 Bug、安全缺陷和性能问题三类，忽略代码风格。"
            "对每个问题必须给出具体的修复建议和代码示例。",
            _batch_response_format,
        ]

        # 构建包含所有代码块的 user prompt
        total_entries = len(entries)
        user_parts: list[str] = [
            f"请评审以下 {total_entries} 个函数/方法，"
            "对每个函数按 function_index 编号输出 findings：\n",
        ]
        for idx, entry in enumerate(entries):
            block = (
                f"## 代码块 {idx}: {entry.file_path}\n"
                f"### 文件: {entry.file_path}\n"
                f"### 函数: {entry.function_name or '(anonymous)'}\n"
                f"```\n{entry.source_code}\n```"
            )
            if entry.patch:
                block += f"\n\n### Diff\n```diff\n{entry.patch}\n```"
            if entry.matched_rules:
                rules_block = "\n\n### 匹配的企业规则\n"
                for r in entry.matched_rules:
                    sev = r.get("severity", "info").upper()
                    name = r.get("name", "")
                    content = r.get("content", "")
                    rules_block += f"- [{sev}] **{name}**: {content}\n"
                block += rules_block
            user_parts.append(block)

        system_prompt = "\n\n".join(system_parts)
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
                "Batch AI review failed for %d chunks: %s",
                len(entries),
                exc,
            )
            await log_error(
                error_type="ai_call_failed",
                error_message=(f"Batch AI review failed for {len(entries)} entries: {exc}"),
            )
            return [[] for _ in entries]

    @staticmethod
    def _try_parse_json(text: str) -> list[dict[str, Any]] | None:
        """尝试多种方式解析 JSON，兼容 AI 生成的常见格式问题。"""
        # 方式 1: 标准解析
        try:
            result = json.loads(text)
            if isinstance(result, list):
                return result
            return None
        except json.JSONDecodeError:
            pass

        # 方式 2: 去掉控制字符后重试
        cleaned = re.sub(r"[\x00-\x1f]", "", text)
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
            return None
        except json.JSONDecodeError:
            pass

        # 方式 3: 修复常见 AI JSON 格式问题
        cleaned = re.sub(r",\s*([}\]])", r"\1", text)  # 移除尾部逗号
        # 将未转义的双引号内的单引号替换
        # 注：若描述中有单引号字符串，json.loads 本就能解析，此处只兜底
        cleaned = cleaned.replace("'", '"')
        try:
            result = json.loads(cleaned)
            if isinstance(result, list):
                return result
            return None
        except json.JSONDecodeError:
            pass

        # 方式 4: 提取最外层 [] 内的内容重试
        stack: list[int] = []
        brackets: list[tuple[int, int]] = []
        for i, ch in enumerate(text):
            if ch == "[":
                stack.append(i)
                continue
            if ch != "]" or not stack:
                continue
            start = stack.pop()
            if not stack:
                brackets.append((start, i))
        for s, e in brackets:
            try:
                result = json.loads(text[s : e + 1])
                if isinstance(result, list):
                    return result
            except json.JSONDecodeError:
                continue

        return None

    @staticmethod
    def _parse_response(content: str, chunk: CodeChunk) -> list[DimensionFinding]:
        """从 AI 响应中解析 findings。

        支持多种格式，按优先级尝试：
        1. 被 ```json ... ``` markdown 包裹的 JSON
        2. 从内容中提取第一个 `[...]` 数组（找到第一个 `[` 和最后一个 `]`）
        3. 直接解析整个内容
        4. 修复常见 AI JSON 格式问题后重试（尾部逗号、单引号等）
        """
        raw_findings: list[dict[str, Any]] | None = None

        # 尝试 1: markdown 代码块包裹
        json_match = re.search(r"```(?:json)?\s*\[[\s\S]*?\]\s*```", content)
        if json_match:
            block = json_match.group(0)
            inner = re.search(r"\[[\s\S]*\]", block)
            if inner:
                raw_findings = AIReviewer._try_parse_json(inner.group(0))

        # 尝试 2: 提取第一个 [ 和最后一个 ]
        if raw_findings is None:
            start = content.find("[")
            end = content.rfind("]")
            if start != -1 and end > start:
                raw_findings = AIReviewer._try_parse_json(content[start : end + 1])

        # 尝试 3: 直接解析全文
        if raw_findings is None:
            raw_findings = AIReviewer._try_parse_json(content.strip())

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

            severity_str = item.get("severity", "")
            if severity_str not in ("critical", "warning"):
                continue
            severity = _SEVERITY_MAP[severity_str]

            category_str = item.get("category", "")
            category_map = {
                "bug": FindingCategory.BUG,
                "security": FindingCategory.SECURITY,
                "performance": FindingCategory.PERFORMANCE,
            }
            category = category_map.get(category_str)
            if category is None:
                continue

            line_start = adjust_line_number(chunk, item.get("line"))

            code_snippet = None
            if line_start is not None:
                relative_line = line_start - chunk.start_line
                source_lines = chunk.source_code.split("\n")
                if 0 <= relative_line < len(source_lines):
                    snippet = source_lines[relative_line].strip()
                    if snippet:
                        code_snippet = snippet[:80]

            findings.append(
                DimensionFinding(
                    category=category,
                    severity=severity,
                    title=item.get("title", "未命名问题"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    file_path=chunk.file_path,
                    line_start=line_start,
                    code_snippet=code_snippet,
                )
            )

        return findings
