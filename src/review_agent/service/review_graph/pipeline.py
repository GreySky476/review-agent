"""LangGraph 评审流水线的流程编排 Node 函数。

包含文件过滤、源码拉取/分块、结果聚合、摘要生成、发布等流程控制节点。
"""

from __future__ import annotations

import logging
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.chunking import CodeChunk, chunk_file
from review_agent.service.git.base import GitProvider
from review_agent.service.publisher import Publisher
from review_agent.service.review_graph.state import ReviewState
from review_agent.types.enums import ReviewStatus

logger = logging.getLogger(__name__)


# ─── 第 1 步：文件过滤 ─────────────────────────────────────


async def filter_files(state: ReviewState) -> dict[str, Any]:
    """按扩展名过滤文件，产出 target_files。"""
    settings = get_settings()
    skip_exts: set[str] = {
        ext.strip() for ext in settings.review_skip_extensions.split(",") if ext.strip()
    }

    target = [f for f in state["files"] if not _should_skip(f.filename, skip_exts)]

    logger.info(
        "filter_files: %d total → %d target (%d skipped by extension)",
        len(state["files"]),
        len(target),
        len(state["files"]) - len(target),
    )
    return {"target_files": target}


def _should_skip(filename: str, skip_exts: set[str]) -> bool:
    ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
    return f".{ext}" in skip_exts


# ─── 第 2 步：拉取源码 + 分块 ──────────────────────────────


async def fetch_and_chunk(
    state: ReviewState,
    git_provider: GitProvider | None = None,
) -> dict[str, Any]:
    """拉取变更文件源码，按函数分块。

    跳过已删除的文件，仅评审本次 commit 变更的文件。
    """
    repo_name = state["repo_name"]
    sha = state["sha"]
    chunks: list[CodeChunk] = []
    sources: dict[str, str] = {}

    if git_provider is None:
        logger.warning("fetch_and_chunk: git_provider is None, returning empty")
        return {"chunks": chunks, "source_codes": sources}

    for f in state["target_files"]:
        if f.status == "removed":
            logger.debug("fetch_and_chunk: skip removed file %s", f.filename)
            continue
        code = await git_provider.get_file_content(repo_name, f.filename, sha)
        if code is None:
            logger.warning("fetch_and_chunk: failed to fetch %s@%s:%s", repo_name, sha, f.filename)
            continue
        sources[f.filename] = code
        file_chunks = await chunk_file(f.filename, code)
        chunks.extend(file_chunks)

    logger.info("fetch_and_chunk: %d files → %d chunks", len(sources), len(chunks))
    return {"chunks": chunks, "source_codes": sources}


# ─── 第 5 步：聚合 ─────────────────────────────────────────


async def aggregate_findings(state: ReviewState) -> dict[str, Any]:
    """合并所有维度的 findings，去重 + 打分。"""
    all_findings = (
        state.get("rule_findings", [])
        + state.get("ai_findings", [])
        + state.get("structural_findings", [])
    )
    publisher = Publisher()
    deduped, score = publisher.aggregate(all_findings)

    logger.info(
        "aggregate: %d raw → %d deduped, score=%d",
        len(all_findings),
        len(deduped),
        score,
    )
    return {
        "all_findings": all_findings,
        "deduped_findings": deduped,
        "score": score,
    }


# ─── 第 6 步：生成摘要 ─────────────────────────────────────


async def generate_summary(state: ReviewState) -> dict[str, Any]:
    """生成 Markdown 格式的评审摘要。"""
    deduped = state.get("deduped_findings", [])
    score = state.get("score", 100)
    publisher = Publisher()
    summary = publisher.generate_summary(deduped, score)
    logger.info(
        "generate_summary: score=%d, findings=%d, summary_len=%d",
        score,
        len(deduped),
        len(summary),
    )
    return {"summary_markdown": summary, "status": ReviewStatus.COMPLETED}


# ─── 第 7 步：发布 ─────────────────────────────────────────


async def publish_results(
    state: ReviewState,
    git_provider: GitProvider | None = None,
) -> dict[str, Any]:
    """发布评审摘要评论到 GitHub Commit。

    发布失败不阻塞流程，只记录警告日志。
    """
    summary = state.get("summary_markdown", "")
    if summary and git_provider is not None:
        try:
            await git_provider.publish_commit_summary(
                state["repo_name"],
                state["sha"],
                summary,
            )
        except Exception:
            logger.warning(
                "publish_results: failed to publish for %s@%s",
                state["repo_name"],
                state["sha"],
            )

    return {"status": ReviewStatus.COMPLETED}
