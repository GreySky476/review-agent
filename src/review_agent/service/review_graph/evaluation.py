"""LangGraph 评审流水线的评估 Node 函数。

包含五个维度的规则检查、AI 评审、结构评审等评审评估节点。
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
from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import (
    DimensionFinding,
    review_bug_risk,
    review_code_style,
    review_dependency,
    review_performance,
    review_security,
)
from review_agent.service.dimensions.structure import review_structure
from review_agent.service.review_graph.state import ReviewState
from review_agent.service.standards import load_standards
from review_agent.types.enums import FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)


# ─── 第 3 步：五个维度规则检查（各是一个独立 node） ────────


async def run_security_rules(state: ReviewState) -> dict[str, Any]:
    """安全维度规则检查。"""
    chunks = state.get("chunks", [])
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_security(chunk))
    logger.info("run_security_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_bug_rules(state: ReviewState) -> dict[str, Any]:
    """Bug 风险维度规则检查。"""
    chunks = state.get("chunks", [])
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_bug_risk(chunk))
    logger.info("run_bug_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_performance_rules(state: ReviewState) -> dict[str, Any]:
    """性能维度规则检查。"""
    chunks = state.get("chunks", [])
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_performance(chunk))
    logger.info("run_performance_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_style_rules(state: ReviewState) -> dict[str, Any]:
    """代码规范维度规则检查。"""
    chunks = state.get("chunks", [])
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_code_style(chunk))
    logger.info("run_style_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_dependency_rules(state: ReviewState) -> dict[str, Any]:
    """依赖安全维度规则检查。"""
    chunks = state.get("chunks", [])
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_dependency(chunk))
    logger.info("run_dependency_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


# ─── 第 4 步：按 chunk 类型分流评审 ────────────────────────


async def ai_review_chunk(
    state: ReviewState,
    ai_provider: AIProvider | None = None,
) -> dict[str, Any]:
    """对单个 chunk 进行 AI 评审。

    由 route_chunks edge 通过 Send("ai_review", {"pending_chunk": chunk})
    触发。每个 Send 分支看到一个独立的 pending_chunk。
    """
    chunk = state.get("pending_chunk")
    if chunk is None:
        return {"ai_findings": []}
    if ai_provider is None:
        logger.debug(
            "ai_review: no AI provider, skipping %s/%s",
            chunk.file_path,
            chunk.function_name,
        )
        return {"ai_findings": []}

    # 查找该 chunk 对应文件的 patch（用于 diff 上下文）
    patch: str | None = None
    for f in state["files"]:
        if f.filename == chunk.file_path:
            patch = f.patch
            break

    logger.info(
        "ai_review: starting %s/%s (tokens=%d, patch=%s)",
        chunk.file_path,
        chunk.function_name or "?",
        chunk.estimated_tokens,
        "yes" if patch else "no",
    )
    findings = await _ai_review(chunk, patch, ai_provider)
    logger.info(
        "ai_review: %s/%s → %d findings",
        chunk.file_path,
        chunk.function_name or "?",
        len(findings),
    )
    return {"ai_findings": findings}


async def structural_review_chunk(state: ReviewState) -> dict[str, Any]:
    """对单个 chunk 进行结构评审。

    由 route_chunks edge 通过 Send("structural_review", {"pending_chunk": chunk})
    触发。适用超大块或边界块。
    """
    chunk = state.get("pending_chunk")
    if chunk is None:
        return {"structural_findings": []}

    findings = await review_structure(chunk)
    logger.info(
        "structural_review: %s/%s (tokens=%d) → %d findings",
        chunk.file_path,
        chunk.function_name or "?",
        chunk.estimated_tokens,
        len(findings),
    )
    return {"structural_findings": findings}


# ─── AI 评审内部逻辑（移植自 CommitReviewService） ────────


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


async def _ai_review(
    chunk: CodeChunk,
    patch: str | None,
    ai: AIProvider,
) -> list[DimensionFinding]:
    """调用 AI 模型评审单个代码块。"""
    settings = get_settings()

    # 注入语言特定规范
    lang_standards = load_standards(chunk.file_path)
    system_parts: list[str] = []
    if lang_standards:
        system_parts.append(f"## 语言特定代码评审规范\n\n{lang_standards}")
    system_parts.append(
        "你是一位资深代码评审专家。请严格参照上述规范审查下方的代码变更，"
        "找出其中的违规项、正确性缺陷、安全风险、错误处理遗漏和逻辑错误。"
    )
    system_parts.append(_AI_REVIEW_BASE_PROMPT)
    system_prompt = "\n\n".join(system_parts)

    user_parts = [
        f"## 函数源码（{chunk.file_path}）\n```\n{chunk.source_code}\n```",
    ]
    if patch:
        user_parts.append(f"## Diff\n```diff\n{patch}\n```")
    user_prompt = "\n\n".join(user_parts)

    request = AICompletionRequest(
        model=settings.ai_model_name,
        messages=[
            AIMessage(role="system", content=system_prompt),
            AIMessage(role="user", content=user_prompt),
        ],
        temperature=0.1,
        max_tokens=settings.ai_review_max_tokens,
        timeout_seconds=settings.ai_request_timeout,
    )

    try:
        response = await ai.complete(request)
        return _parse_ai_response(response.content, chunk)
    except Exception as exc:
        logger.warning("AI review failed for %s/%s: %s", chunk.file_path, chunk.function_name, exc)
        return []


def _parse_ai_response(content: str, chunk: CodeChunk) -> list[DimensionFinding]:
    """从 AI 响应中解析 findings。

    支持三种格式：
    1. 被 ```json ... ``` 包裹的 JSON
    2. 提取首个 `[...]` 数组
    3. 直接解析全文
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

    if raw_findings is None or not isinstance(raw_findings, list):
        return []

    findings: list[DimensionFinding] = []
    severity_map = {
        "critical": FindingSeverity.CRITICAL,
        "warning": FindingSeverity.WARNING,
        "info": FindingSeverity.INFO,
    }

    for item in raw_findings:
        if not isinstance(item, dict):
            continue
        severity_str = item.get("severity", "info")
        findings.append(
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=severity_map.get(severity_str, FindingSeverity.INFO),
                title=item.get("title", "未命名问题"),
                description=item.get("description", ""),
                suggestion=item.get("suggestion", ""),
                file_path=chunk.file_path,
                line_start=item.get("line"),
            )
        )
    return findings
