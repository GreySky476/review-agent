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
from review_agent.service.review_graph.edges import route_chunks, route_to_dispatch
from review_agent.service.review_graph.evaluation import (
    run_ai_batch,
    run_all_rules,
    structural_review_chunk,
)
from review_agent.service.review_graph.pipeline import (
    aggregate_findings,
    fetch_and_chunk,
    filter_files,
    generate_summary,
    resolve_incremental,
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
    knowledge_base: Any = None,
) -> Callable[[ReviewState], Any]:
    """注入 ai_provider 和 knowledge_base 的包装器。"""

    async def wrapper(state: ReviewState) -> Any:
        return await node_fn(state, ai_provider=ai_provider, knowledge_base=knowledge_base)

    return wrapper


def build_review_graph(
    git_provider: GitProvider,
    ai_provider: AIProvider | None = None,
    knowledge_base: Any = None,
) -> StateGraph:
    """构建 LangGraph 评审流水线。

    Args:
        git_provider: Git 平台适配器（GitHub / GitLab / Gitee）。
        ai_provider: AI 模型调用器。为 None 时 AI 评审节点跳过。
        knowledge_base: 知识库服务（可选），用于企业自定义规则检索。

    Returns:
        已编译可调用的 StateGraph。
    """
    builder = StateGraph(ReviewState)

    # ─── 注册节点 ───
    builder.add_node("filter_files", filter_files)
    builder.add_node("fetch_and_chunk", _with_git(fetch_and_chunk, git_provider))

    # 五维度规则检查（合并为一个 node，避免 Send reducer 问题）
    builder.add_node("run_all_rules", run_all_rules)

    # 增量去重
    builder.add_node("resolve_incremental", resolve_incremental)

    # AI 与结构评审（均为批量 node，避免 Send reducer 问题）
    builder.add_node("ai_batch", _with_ai(run_ai_batch, ai_provider, knowledge_base))
    builder.add_node("structural_batch", structural_review_chunk)
    builder.add_node("dispatch_chunks", _pass_through)

    # 聚合与输出（不含发布——由 queue.py 的 run_commit_review 统一处理）
    builder.add_node("aggregate", aggregate_findings)
    builder.add_node("summarize", generate_summary)

    # ─── 注册边 ───
    # 线性起始
    builder.add_edge(START, "filter_files")
    builder.add_edge("filter_files", "fetch_and_chunk")

    # fetch_and_chunk → resolve_incremental → run_all_rules（五维度合并）
    builder.add_edge("fetch_and_chunk", "resolve_incremental")
    builder.add_conditional_edges(
        "resolve_incremental",
        route_to_dispatch,
    )

    # run_all_rules → dispatch_chunks（汇聚点）
    builder.add_edge("run_all_rules", "dispatch_chunks")

    # dispatch_chunks → 按 chunk 类型分流到 ai_batch / structural_batch
    builder.add_conditional_edges(
        "dispatch_chunks",
        route_chunks,
    )

    # 各批量节点独立路由到 aggregate（避免 barriers 下未调度节点阻塞）
    builder.add_edge("ai_batch", "aggregate")
    builder.add_edge("structural_batch", "aggregate")

    # aggregate → summarize → END（发布由调用方 queue.py 负责）
    builder.add_edge("aggregate", "summarize")
    builder.add_edge("summarize", END)

    return builder.compile(checkpointer=create_checkpointer())


async def _pass_through(state: ReviewState) -> dict[str, Any]:
    """透传节点：run_all_rules 完成后作为 route_chunks 的起点。"""
    total_rules = len(state.get("rule_findings", []))
    total_files = len(state.get("files", []))
    logger.info(
        "dispatch_chunks: rule check completed, %d total findings, %d files",
        total_rules,
        total_files,
    )
    return {}
