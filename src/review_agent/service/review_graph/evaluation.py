"""LangGraph 评审流水线的评估 Node 函数。

包含五个维度的规则检查、AI 评审、结构评审等评审评估节点。
"""

from __future__ import annotations

import logging
from typing import Any

from review_agent.service.ai.base import AIProvider
from review_agent.service.ai_reviewer import AIReviewer
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

logger = logging.getLogger(__name__)


# ─── 第 3 步：五个维度规则检查（各是一个独立 node） ────────


async def run_security_rules(state: ReviewState) -> dict[str, Any]:
    """安全维度规则检查。"""
    chunks = state.get("new_chunks", state.get("chunks", []))
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_security(chunk))
    logger.info("run_security_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_bug_rules(state: ReviewState) -> dict[str, Any]:
    """Bug 风险维度规则检查。"""
    chunks = state.get("new_chunks", state.get("chunks", []))
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_bug_risk(chunk))
    logger.info("run_bug_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_performance_rules(state: ReviewState) -> dict[str, Any]:
    """性能维度规则检查。"""
    chunks = state.get("new_chunks", state.get("chunks", []))
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_performance(chunk))
    logger.info("run_performance_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_style_rules(state: ReviewState) -> dict[str, Any]:
    """代码规范维度规则检查。"""
    chunks = state.get("new_chunks", state.get("chunks", []))
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_code_style(chunk))
    logger.info("run_style_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


async def run_dependency_rules(state: ReviewState) -> dict[str, Any]:
    """依赖安全维度规则检查。"""
    chunks = state.get("new_chunks", state.get("chunks", []))
    findings: list[DimensionFinding] = []
    for chunk in chunks:
        findings.extend(await review_dependency(chunk))
    logger.info("run_dependency_rules: %d chunks → %d findings", len(chunks), len(findings))
    return {"rule_findings": findings}


# ─── 第 4 步：按 chunk 类型分流评审 ────────────────────────


async def ai_review_chunk(
    state: ReviewState,
    ai_provider: AIProvider | None = None,
    knowledge_base: Any = None,
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

    # RAG 规则检索
    matched_rules: list[dict[str, Any]] = []
    if knowledge_base is not None:
        try:
            matched_rules = await knowledge_base.search(chunk, top_k=5)
        except Exception:
            logger.warning(
                "Knowledge base search failed for %s/%s",
                chunk.file_path,
                chunk.function_name or "?",
            )

    logger.info(
        "ai_review: starting %s/%s (tokens=%d, patch=%s, rules=%d)",
        chunk.file_path,
        chunk.function_name or "?",
        chunk.estimated_tokens,
        "yes" if patch else "no",
        len(matched_rules),
    )

    reviewer = AIReviewer(ai_provider)
    findings = await reviewer.review_chunk(chunk, patch=patch, matched_rules=matched_rules)

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
