"""ReviewState — 贯穿 LangGraph 评审流水线的共享状态。"""

from __future__ import annotations

from typing import Annotated, Any, TypedDict

from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.service.git.base import PRFile
from review_agent.types.enums import ReviewStatus

_T = Any


def _merge_lists(
    existing: list[_T] | None,
    updates: list[_T] | None,
) -> list[_T]:
    """Reducer: Send() 多并行分支通过此 reducer 安全合并到同一 key。

    LangGraph 的 Annotated[list[T], reducer] 模式允许在多个并行 node
    同时写入同一 state key 时自动合并，不会覆盖。
    """
    if existing is None:
        return updates or []
    if updates is None:
        return existing
    return existing + updates


class ReviewState(TypedDict):
    """贯穿 LangGraph 评审流水线的共享状态。

    TypedDict 保证类型安全，配合 Annotated reducer 支持 Send() 并行写入。
    """

    # ── 输入（一次写入，永不改变） ──
    repo_name: str
    sha: str
    files: list[PRFile]
    pr_number: int | None  # PR 评审时设置，push 为 None

    # ── 处理中状态（逐步填充） ──
    target_files: list[PRFile]
    chunks: list[CodeChunk]
    source_codes: dict[str, str]
    previous_review_id: str | None   # 上次评审的 review ID（增量用）
    last_reviewed_sha: str | None    # 上次评到的 SHA（增量用）
    previous_file_paths: list[str]   # 上次评审已覆盖的 file_path 列表（增量去重用）
    new_chunks: list[CodeChunk]      # 本次新增的 chunk，fanout/route 基于此

    # ── 挂起的 chunk（由 Send 设置，节点读取后用 reducer 合并 findings） ──
    pending_chunk: CodeChunk | None

    # ── Findings（Annotated reducer 累加，Send 并发安全） ──
    rule_findings: Annotated[list[DimensionFinding], _merge_lists]
    ai_findings: Annotated[list[DimensionFinding], _merge_lists]
    structural_findings: Annotated[list[DimensionFinding], _merge_lists]

    # ── 错误追踪（Send 并行安全，使用 Annotated reducer） ──
    unreviewed_files: Annotated[list[str], _merge_lists]
    error_messages: Annotated[list[str], _merge_lists]

    # ── 输出 ──
    all_findings: list[DimensionFinding]
    deduped_findings: list[DimensionFinding]
    score: int
    summary_markdown: str
    error: str | None
    status: ReviewStatus
