"""LangGraph 评审流水线的图构建与编译。

提供 build_review_graph() 工厂函数，注入 GitProvider 和 AIProvider 依赖。
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from langgraph.graph import END, START, StateGraph

from review_agent.service.ai.base import AIProvider
from review_agent.service.git.base import GitProvider
from review_agent.service.review_graph.checkpointer import create_checkpointer
from review_agent.service.review_graph.edges import fanout_to_dimensions, route_chunks
from review_agent.service.review_graph.evaluation import (
    ai_review_chunk,
    run_bug_rules,
    run_dependency_rules,
    run_performance_rules,
    run_security_rules,
    run_style_rules,
    structural_review_chunk,
)
from review_agent.service.review_graph.pipeline import (
    aggregate_findings,
    fetch_and_chunk,
    filter_files,
    generate_summary,
)
from review_agent.service.review_graph.state import ReviewState

logger = logging.getLogger(__name__)


def _with_git(
    node_fn: Callable[..., Any],
    git_provider: GitProvider,
) -> Callable[[ReviewState], Any]:
    """注入 git_provider 的包装器。

    node_fn 签名: (state, git_provider) → dict
    包装后符合 LangGraph node 签名: (state) → dict
    """

    async def wrapper(state: ReviewState) -> Any:
        return await node_fn(state, git_provider=git_provider)

    return wrapper


def _with_ai(
    node_fn: Callable[..., Any],
    ai_provider: AIProvider | None,
) -> Callable[[ReviewState], Any]:
    """注入 ai_provider 的包装器。"""

    async def wrapper(state: ReviewState) -> Any:
        return await node_fn(state, ai_provider=ai_provider)

    return wrapper


def build_review_graph(
    git_provider: GitProvider,
    ai_provider: AIProvider | None = None,
) -> StateGraph:
    """构建 LangGraph 评审流水线。

    Args:
        git_provider: Git 平台适配器（GitHub / GitLab / Gitee）。
        ai_provider: AI 模型调用器。为 None 时 AI 评审节点跳过。

    Returns:
        已编译可调用的 StateGraph。
    """
    builder = StateGraph(ReviewState)

    # ─── 注册节点 ───
    builder.add_node("filter_files", filter_files)
    builder.add_node("fetch_and_chunk", _with_git(fetch_and_chunk, git_provider))

    # 五个规则维度（Phase 1.2 可拆为 Send 并行）
    builder.add_node("run_security_rules", run_security_rules)
    builder.add_node("run_bug_rules", run_bug_rules)
    builder.add_node("run_performance_rules", run_performance_rules)
    builder.add_node("run_style_rules", run_style_rules)
    builder.add_node("run_dependency_rules", run_dependency_rules)

    # AI 与结构评审
    builder.add_node("ai_review", _with_ai(ai_review_chunk, ai_provider))
    builder.add_node("structural_review", structural_review_chunk)
    builder.add_node("dispatch_chunks", _pass_through)

    # 聚合与输出（不含发布——由 queue.py 的 run_commit_review 统一处理）
    builder.add_node("aggregate", aggregate_findings)
    builder.add_node("summarize", generate_summary)

    # ─── 注册边 ───
    # 线性起始
    builder.add_edge(START, "filter_files")
    builder.add_edge("filter_files", "fetch_and_chunk")

    # fetch_and_chunk → 并行分发到 5 个维度
    builder.add_conditional_edges(
        "fetch_and_chunk",
        fanout_to_dimensions,
    )

    # 5 维度汇聚到 dispatch_chunks
    builder.add_edge(
        [
            "run_security_rules",
            "run_bug_rules",
            "run_performance_rules",
            "run_style_rules",
            "run_dependency_rules",
        ],
        "dispatch_chunks",
    )

    # dispatch_chunks → 按 chunk 类型分流
    builder.add_conditional_edges(
        "dispatch_chunks",
        route_chunks,
    )

    # AI / 结构评审汇聚到 aggregate
    builder.add_edge(["ai_review", "structural_review"], "aggregate")

    # aggregate → summarize → END（发布由调用方 queue.py 负责）
    builder.add_edge("aggregate", "summarize")
    builder.add_edge("summarize", END)

    return builder.compile(checkpointer=create_checkpointer())


async def _pass_through(state: ReviewState) -> dict[str, Any]:
    """透传节点：5 维度汇聚后作为 route_chunks 的起点。"""
    total_rules = len(state.get("rule_findings", []))
    total_files = len(state.get("files", []))
    logger.info(
        "dispatch_chunks: all 5 rule dimensions completed, %d total rule findings, %d files",
        total_rules,
        total_files,
    )
    return {}
