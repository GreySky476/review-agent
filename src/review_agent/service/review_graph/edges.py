"""LangGraph 评审流水线的条件路由 Edge 函数。

edges 是纯函数，接收 state 返回下一步节点名。所有 findings
产出均在单 node 内完成，不依赖 Send + reducer。
"""

from __future__ import annotations

import logging

from review_agent.service.review_graph.state import ReviewState
from review_agent.types.enums import ChunkPath

logger = logging.getLogger(__name__)


def route_to_dispatch(state: ReviewState) -> str:  # noqa: ARG001
    """resolve_incremental 完成后，进入 run_all_rules（后续汇聚到 dispatch_chunks）。"""
    return "run_all_rules"


def route_chunks(state: ReviewState) -> str:
    """dispatch_chunks 完成后，按 chunk 类型路由到不同评审节点。

    - DETAILED_REVIEW 的 chunk → ai_batch（批量 AI 评审）
    - STRUCTURAL_REVIEW 的 chunk → structural_batch（批量结构评审）
    - 无 chunk → 直接 aggregate
    """
    chunks = state.get("new_chunks") or state.get("chunks", [])
    if not chunks:
        logger.info("route_chunks: no chunks to review, routing directly to aggregate")
        return "aggregate"

    ai_chunks = [c for c in chunks if c.path == ChunkPath.DETAILED_REVIEW]
    struct_chunks = [c for c in chunks if c.path != ChunkPath.DETAILED_REVIEW]

    # 将待处理的 chunks 写入 state 供后续节点读取
    # route_chunks 是 edge 函数，通过返回特殊指令来触发 state 更新
    # 使用两个 Send 分别传递给 ai_batch 和 structural_batch
    from langgraph.types import Send

    sends: list[Send] = []
    if ai_chunks:
        sends.append(Send("ai_batch", {"pending_ai_chunks": ai_chunks}))
    if struct_chunks:
        sends.append(Send("structural_batch", {"pending_structural_chunks": struct_chunks}))

    logger.info(
        "route_chunks: %d chunks → %d ai_batch, %d structural_batch",
        len(chunks),
        len(ai_chunks),
        len(struct_chunks),
    )
    return sends
