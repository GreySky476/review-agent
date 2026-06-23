"""LangGraph 评审流水线的评估 Node 函数。

包含五个维度的规则检查、AI 评审、结构评审等评审评估节点。
"""

from __future__ import annotations

import logging
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import BatchReviewEntry
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


# ─── 第 3 步：五维度规则检查（合并为一个 node，避免 Send reducer 问题） ────


async def run_all_rules(state: ReviewState) -> dict[str, Any]:
    """五维度规则检查：安全、Bug、性能、规范、依赖。

    合并为一个 node 内顺序执行，避免 LangGraph Send + reducer 的 findings 合并问题。
    """
    chunks = state.get("new_chunks", state.get("chunks", []))
    all_findings: list[DimensionFinding] = []

    findings = []
    for chunk in chunks:
        findings.extend(await review_security(chunk))
    logger.info("run_security_rules: %d chunks -> %d findings", len(chunks), len(findings))
    all_findings.extend(findings)

    findings = []
    for chunk in chunks:
        findings.extend(await review_bug_risk(chunk))
    logger.info("run_bug_rules: %d chunks -> %d findings", len(chunks), len(findings))
    all_findings.extend(findings)

    findings = []
    for chunk in chunks:
        findings.extend(await review_performance(chunk))
    logger.info("run_performance_rules: %d chunks -> %d findings", len(chunks), len(findings))
    all_findings.extend(findings)

    findings = []
    for chunk in chunks:
        findings.extend(await review_code_style(chunk))
    logger.info("run_style_rules: %d chunks -> %d findings", len(chunks), len(findings))
    all_findings.extend(findings)

    findings = []
    for chunk in chunks:
        findings.extend(await review_dependency(chunk))
    logger.info("run_dependency_rules: %d chunks -> %d findings", len(chunks), len(findings))
    all_findings.extend(findings)

    logger.info("run_all_rules: total %d findings from 5 dimensions", len(all_findings))
    return {"rule_findings": all_findings}


# ─── 第 4 步：按 chunk 类型分流评审 ────────────────────────


async def run_ai_batch(
    state: ReviewState,
    ai_provider: AIProvider | None = None,
    knowledge_base: Any = None,
) -> dict[str, Any]:
    """批量 AI 评审：将 chunks 按 token 预算分组后批量调用 LLM。

    由 route_chunks edge 通过 Send 触发。避免 per-chunk Send reducer 合并问题。
    """
    chunks = state.get("pending_ai_chunks", [])
    files = state.get("files", [])
    all_findings: list[DimensionFinding] = []

    if ai_provider is None or not chunks:
        return {"ai_findings": all_findings}

    # 构建 patch_map
    patch_map: dict[str, str | None] = {}
    for f in files:
        if hasattr(f, 'filename') and hasattr(f, 'patch'):
            patch_map[f.filename] = f.patch

    # RAG 规则检索（合并到 BatchReviewEntry）
    entries: list[BatchReviewEntry] = []
    for chunk in chunks:
        matched_rules: list[dict[str, Any]] = []
        if knowledge_base is not None:
            try:
                matched_rules = await knowledge_base.search(chunk, top_k=5)
            except Exception:
                logger.warning(
                    "Knowledge base search failed for %s/%s",
                    chunk.file_path, chunk.function_name or "?",
                )
        entries.append(BatchReviewEntry(
            file_path=chunk.file_path,
            function_name=chunk.function_name,
            source_code=chunk.source_code,
            start_line=chunk.start_line,
            end_line=chunk.end_line,
            estimated_tokens=chunk.estimated_tokens,
            patch=patch_map.get(chunk.file_path),
            matched_rules=matched_rules,
        ))

    settings = get_settings()
    max_batch_tokens = settings.ai_batch_max_input_tokens  # default 3000, 0=disable

    if max_batch_tokens > 0:
        # 按 token 预算分组
        batches: list[list[BatchReviewEntry]] = []
        current_batch: list[BatchReviewEntry] = []
        current_tokens = 0

        for entry in entries:
            entry_cost = entry.estimated_tokens + 100  # 100 token overhead per entry
            if current_tokens + entry_cost > max_batch_tokens and current_batch:
                batches.append(current_batch)
                current_batch = []
                current_tokens = 0
            current_batch.append(entry)
            current_tokens += entry_cost

        if current_batch:
            batches.append(current_batch)

        logger.info(
            "ai_batch: %d chunks -> %d batches (max_batch_tokens=%d)",
            len(entries), len(batches), max_batch_tokens,
        )
    else:
        # 禁用批量：每个 chunk 单独一组
        batches = [[e] for e in entries]
        logger.info(
            "ai_batch: %d chunks, batching disabled", len(entries)
        )

    reviewer = AIReviewer(ai_provider)
    for batch in batches:
        try:
            findings_list = await reviewer.review_chunks(batch)
            for findings in findings_list:
                all_findings.extend(findings)
        except Exception as exc:
            logger.warning("Batch AI review failed: %s", exc)

    logger.info("ai_batch: %d chunks -> %d total AI findings", len(chunks), len(all_findings))
    return {"ai_findings": all_findings}


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
