"""AI 响应解析工具函数。

从 AI 返回的文本中解析 JSON、提取 DimensionFinding 列表。
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

from review_agent.service.ai.types import BatchReviewEntry
from review_agent.service.chunking import CodeChunk, adjust_line_number
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.types.enums import FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)

_SEVERITY_MAP = {
    "critical": FindingSeverity.CRITICAL,
    "warning": FindingSeverity.WARNING,
    "info": FindingSeverity.INFO,
}


def try_parse_json(text: str) -> list[dict[str, Any]] | None:
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


def parse_response(content: str, chunk: CodeChunk) -> list[DimensionFinding]:
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
            raw_findings = try_parse_json(inner.group(0))

    # 尝试 2: 提取第一个 [ 和最后一个 ]
    if raw_findings is None:
        start = content.find("[")
        end = content.rfind("]")
        if start != -1 and end > start:
            raw_findings = try_parse_json(content[start : end + 1])

    # 尝试 3: 直接解析全文
    if raw_findings is None:
        raw_findings = try_parse_json(content.strip())

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


def adjust_batch_line(entry: BatchReviewEntry, line: int | None) -> int | None:
    """调整 BatchReviewEntry 的行号（同 adjust_line_number 逻辑）。"""
    if line is None:
        return None
    return entry.start_line + line - 1


def parse_batch_response(
    content: str,
    entries: list[BatchReviewEntry],
) -> list[list[DimensionFinding]]:
    """解析批量 AI 响应，按 function_index 映射回每个 entry。"""
    raw = try_parse_json(content)
    if raw is None:
        logger.warning("Failed to parse batch AI response as JSON")
        return [[] for _ in entries]

    result: list[list[DimensionFinding]] = [[] for _ in entries]
    for item in raw:
        if not isinstance(item, dict):
            continue
        idx = item.get("function_index")
        if not isinstance(idx, int) or idx < 0 or idx >= len(entries):
            continue
        findings_raw = item.get("findings", [])
        entry = entries[idx]
        for f_item in findings_raw:
            if not isinstance(f_item, dict):
                continue
            severity_str = f_item.get("severity", "info")
            result[idx].append(
                DimensionFinding(
                    category=FindingCategory.BUG,
                    severity=_SEVERITY_MAP.get(severity_str, FindingSeverity.INFO),
                    title=f_item.get("title", "未命名问题"),
                    description=f_item.get("description", ""),
                    suggestion=f_item.get("suggestion", ""),
                    file_path=entry.file_path,
                    line_start=adjust_batch_line(entry, f_item.get("line")),
                )
            )

    return result
