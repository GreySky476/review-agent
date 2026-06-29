"""LangGraph 评审流水线的流程编排 Node 函数。

包含文件过滤、源码拉取/分块、增量去重、结果聚合、摘要生成等流程控制节点。
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from review_agent.service.chunking import CodeChunk, chunk_file
from review_agent.service.diff_utils import chunk_overlaps, get_changed_lines_map
from review_agent.service.error_logger import log_error
from review_agent.service.git.base import GitProvider
from review_agent.service.publisher import Publisher
from review_agent.service.review_graph.state import ReviewState
from review_agent.service.utils import parse_skip_patterns, should_skip_file
from review_agent.types.enums import ReviewStatus

logger = logging.getLogger(__name__)


# ─── 第 1 步：文件过滤 ─────────────────────────────────────


async def filter_files(state: ReviewState) -> dict[str, Any]:
    """按路径模式过滤文件，产出 target_files。"""
    t0 = time.monotonic()
    skip_patterns = parse_skip_patterns()

    target = [f for f in state["files"] if not should_skip_file(f.filename, skip_patterns)]

    logger.info(
        "filter_files: %d total → %d target (%d skipped) elapsed=%.1fs",
        len(state["files"]),
        len(target),
        len(state["files"]) - len(target),
        time.monotonic() - t0,
    )
    return {"target_files": target}


# ─── 第 2 步：拉取源码 + 分块 ──────────────────────────────


async def fetch_and_chunk(
    state: ReviewState,
    git_provider: GitProvider | None = None,
) -> dict[str, Any]:
    """拉取变更文件源码，按函数分块。

    跳过已删除的文件，仅评审本次 commit 变更的文件。
    """
    t0 = time.monotonic()
    repo_name = state["repo_name"]
    sha = state["sha"]
    chunks: list[CodeChunk] = []
    sources: dict[str, str] = {}
    unreviewed: list[str] = []

    if git_provider is None:
        logger.warning("fetch_and_chunk: git_provider is None, returning empty")
        return {"chunks": chunks, "source_codes": sources, "unreviewed_files": unreviewed}

    for f in state["target_files"]:
        if f.status == "removed":
            logger.debug("fetch_and_chunk: skip removed file %s", f.filename)
            continue
        code = await git_provider.get_file_content(repo_name, f.filename, sha)
        if code is None:
            logger.warning("fetch_and_chunk: failed to fetch %s@%s:%s", repo_name, sha, f.filename)
            await log_error(
                error_type="git_file_fetch_failed",
                error_message=f"fetch_and_chunk: failed to fetch {repo_name}@{sha}:{f.filename}",
            )
            unreviewed.append(f.filename)
            continue
        sources[f.filename] = code
        file_chunks = await chunk_file(f.filename, code)
        chunks.extend(file_chunks)

    logger.info(
        "fetch_and_chunk: %d files → %d chunks, %d unreviewed elapsed=%.1fs",
        len(sources),
        len(chunks),
        len(unreviewed),
        time.monotonic() - t0,
    )
    return {"chunks": chunks, "source_codes": sources, "unreviewed_files": unreviewed}


# ─── 第 3 步：增量去重（严重级分级决策） ─────────────────────


async def resolve_incremental(state: ReviewState) -> dict[str, Any]:
    """函数级增量去重：基于函数行号与 diff 变更行重叠度 + 历史函数评审状态。

    决策规则：
    1. 读取 inter_commit_files（或当前 files）的 diff 变更行
    2. 对每个 chunk，检查函数行范围是否与变更行重叠
    3. 有重叠 → 需评审
    4. 无重叠且函数在 previous_reviewed_functions 中 → 跳过（已有评审记录）
    5. 无重叠且函数不在 previous_reviewed_functions 但文件在 previous_reviewed_files 中
       → 跳过（向后兼容）
    6. 无重叠且函数不在 previous_reviewed_functions 且文件不在 previous_reviewed_files 中
       → 新函数 → 评审
    7. 模块级变更检测：如果变更行落在所有函数边界之外，强制重评整个文件
    """
    t0 = time.monotonic()
    chunks = state.get("chunks", [])
    previous_reviewed_functions = state.get("previous_reviewed_functions", [])
    previous_reviewed_files = state.get("previous_reviewed_files", [])
    inter_commit_files = state.get("inter_commit_files") or state.get("files", [])
    skip_levels = state.get("skip_levels", "")
    skip_set = {s.strip() for s in skip_levels.split(",") if s.strip()} if skip_levels else set()

    if not chunks:
        logger.info("resolve_incremental: no chunks to resolve")
        return {"new_chunks": []}

    # 构建变更行映射
    changed_lines_map = get_changed_lines_map(inter_commit_files)

    # 构建历史函数索引：{(file_path, function_name): [entry, ...]}
    prev_func_index: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for entry in previous_reviewed_functions:
        fp = entry.get("file_path", "")
        fn = entry.get("function_name", "")
        if fp:
            prev_func_index[(fp, fn)].append(entry)

    # 构建历史文件索引（向后兼容）
    prev_file_sev: dict[str, str | None] = {}
    for entry in previous_reviewed_files:
        path = entry.get("path", "")
        if path:
            prev_file_sev[path] = entry.get("max_severity")

    # ── 模块级检测 ──────────────────────────────────
    # 对每个文件，检查是否有变更行落在所有函数边界之外
    file_chunks_map: dict[str, list[CodeChunk]] = defaultdict(list)
    for c in chunks:
        file_chunks_map[c.file_path].append(c)

    module_force_review_files: set[str] = set()
    for file_path, file_chunks in file_chunks_map.items():
        changed = changed_lines_map.get(file_path)
        if changed is not None and changed:
            # 有明确变更行：检查是否至少有一个函数覆盖
            has_function_overlap = any(
                chunk_overlaps(c.start_line, c.end_line, changed) for c in file_chunks
            )
            if not has_function_overlap:
                # 变更完全在函数边界外 → 模块级变更
                module_force_review_files.add(file_path)

    # ── 逐 chunk 决策 ──────────────────────────────
    new_chunks: list[CodeChunk] = []
    for c in chunks:
        # 模块级强制重评
        if c.file_path in module_force_review_files:
            new_chunks.append(c)
            continue

        changed = changed_lines_map.get(c.file_path)

        # 检查与变更行重叠
        if c.file_path in changed_lines_map and chunk_overlaps(c.start_line, c.end_line, changed):
            new_chunks.append(c)
            continue

        # 无重叠：检查历史函数评审记录
        func_key = (c.file_path, c.function_name)
        if func_key in prev_func_index:
            # 曾被评审过 → 跳过
            continue

        # 向后兼容：检查 previous_reviewed_files
        if c.file_path in prev_file_sev:
            prev_sev = prev_file_sev[c.file_path]
            # 如果未使用函数级数据且文件有严重问题，依据 skip_levels 决定
            if (
                not previous_reviewed_functions
                and prev_sev in ("critical", "warning")
                and prev_sev not in skip_set
            ):
                new_chunks.append(c)
                continue
            continue

        # 全新函数 → 评审
        new_chunks.append(c)

    skipped = len(chunks) - len(new_chunks)
    if skipped:
        logger.info(
            "resolve_incremental: %d/%d chunks new, %d skipped (function-level) elapsed=%.1fs",
            len(new_chunks),
            len(chunks),
            skipped,
            time.monotonic() - t0,
        )
    else:
        logger.info(
            "resolve_incremental: all %d chunks are new elapsed=%.1fs",
            len(chunks),
            time.monotonic() - t0,
        )

    return {"new_chunks": new_chunks}


# ─── 第 4 步：聚合 ─────────────────────────────────────────


async def aggregate_findings(state: ReviewState) -> dict[str, Any]:
    """合并所有维度的 findings，去重 + 打分。"""
    t0 = time.monotonic()
    rule_findings = state.get("rule_findings", [])
    ai_findings = state.get("ai_findings", [])
    structural_findings = state.get("structural_findings", [])
    all_findings = rule_findings + ai_findings + structural_findings
    publisher = Publisher()
    deduped, score = publisher.aggregate(all_findings)

    # 失败文件惩罚：按未评审比例扣分（增量场景基于 new_chunks 对应的文件数）
    unreviewed = state.get("unreviewed_files", [])
    new_chunks = state.get("new_chunks", [])
    reviewed_file_count = (
        len({c.file_path for c in new_chunks}) if new_chunks else len(state.get("target_files", []))
    )
    error_msgs: list[str] = []

    if unreviewed:
        fail_ratio = len(unreviewed) / max(reviewed_file_count, 1)
        penalty = int(fail_ratio * 40)
        score = max(0, score - penalty)

        error_msgs = [f"{len(unreviewed)} 个文件无法获取源码"]

    logger.info(
        "aggregate: rule=%d ai=%d struct=%d total=%d deduped=%d "
        "score=%d unreviewed=%d elapsed=%.1fs",
        len(rule_findings),
        len(ai_findings),
        len(structural_findings),
        len(all_findings),
        len(deduped),
        score,
        len(unreviewed),
        time.monotonic() - t0,
    )
    return {
        "all_findings": all_findings,
        "deduped_findings": deduped,
        "score": score,
        "error_messages": error_msgs,
    }


# ─── 第 6 步：生成摘要 ─────────────────────────────────────


async def generate_summary(state: ReviewState) -> dict[str, Any]:
    """生成 Markdown 格式的评审摘要。"""
    t0 = time.monotonic()
    deduped = state.get("deduped_findings", [])
    score = state.get("score", 100)
    unreviewed = state.get("unreviewed_files", [])
    error_msgs = state.get("error_messages", [])

    critical_count = sum(1 for f in deduped if f.severity == "critical")
    warning_count = sum(1 for f in deduped if f.severity == "warning")

    publisher = Publisher()
    summary = publisher.generate_summary(
        deduped,
        score,
        unreviewed_count=len(unreviewed),
    )

    # 根据是否有失败文件决定最终状态
    status = ReviewStatus.COMPLETED_WITH_ERRORS if unreviewed else ReviewStatus.COMPLETED

    logger.info(
        "generate_summary: score=%d findings=%d critical=%d warning=%d "
        "status=%s unreviewed=%d elapsed=%.1fs",
        score,
        len(deduped),
        critical_count,
        warning_count,
        status.value,
        len(unreviewed),
        time.monotonic() - t0,
    )
    return {
        "summary_markdown": summary,
        "status": status,
        "error_messages": error_msgs,
    }


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
            await log_error(
                error_type="publish_failed",
                error_message=(
                    f"publish_results: failed to publish for {state['repo_name']}@{state['sha']}"
                ),
            )

    return {"status": ReviewStatus.COMPLETED}
