"""LangGraph 评审流水线的条件路由 Edge 函数。

edges 是纯函数，接收 state 返回 list[Send]，LangGraph 根据返回值
动态创建并行执行的子分支。
"""

from __future__ import annotations

import logging

from langgraph.types import Send

from review_agent.service.review_graph.state import ReviewState
from review_agent.types.enums import ChunkPath

logger = logging.getLogger(__name__)


def fanout_to_dimensions(state: ReviewState) -> list[Send]:
    """fetch_and_chunk 完成后，并行分发到五个规则检查维度。

    Send 创建的子分支不会自动继承父 state，因此需要显式传入 chunks。
    各分支的 rule_findings 通过 Annotated reducer 自动合并到 state。
    """
    chunks = state.get("chunks", [])
    logger.info(
        "fanout_to_dimensions: dispatching %d chunks to 5 rule dimensions",
        len(chunks),
    )
    return [
        Send("run_security_rules", {"chunks": chunks}),
        Send("run_bug_rules", {"chunks": chunks}),
        Send("run_performance_rules", {"chunks": chunks}),
        Send("run_style_rules", {"chunks": chunks}),
        Send("run_dependency_rules", {"chunks": chunks}),
    ]


def route_chunks(state: ReviewState) -> list[Send]:
    """遍历所有 chunks，按类型分发到 AI 评审或结构评审。

    每个 chunk 独立路由互不阻塞：
    - DETAILED_REVIEW → ai_review node（同时传入 files 供 patch 查找）
    - STRUCTURAL_REVIEW → structural_review node

    Send 子分支不会自动继承父 state，必须显式传入节点需要的数据。
    如果没有任何 chunk，直接路由到 aggregate 确保流程完整。
    """
    sends: list[Send] = []
    chunks = state.get("chunks", [])
    files = state.get("files", [])

    ai_count = 0
    struct_count = 0
    for chunk in chunks:
        if chunk.path == ChunkPath.DETAILED_REVIEW:
            sends.append(
                Send(
                    "ai_review",
                    {
                        "pending_chunk": chunk,
                        "files": files,
                    },
                )
            )
            ai_count += 1
        else:
            sends.append(
                Send(
                    "structural_review",
                    {
                        "pending_chunk": chunk,
                    },
                )
            )
            struct_count += 1

    if not sends:
        logger.info("route_chunks: no chunks to review, routing directly to aggregate")
        sends.append(Send("aggregate", {}))
    else:
        logger.info(
            "route_chunks: %d chunks → %d ai_review, %d structural_review",
            len(chunks),
            ai_count,
            struct_count,
        )
    return sends
