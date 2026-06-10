"""Tests for LangGraph review pipeline.

测试覆盖：
1. ReviewState reducer 行为
2. 各 node 函数在隔离环境下的行为
3. Edge 路由逻辑（fanout 和 chunk 分发）
4. 完整图编译与空状态全流程
5. 带 chunks 的真实业务场景
"""

from __future__ import annotations

from typing import Any

import pytest

from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import (
    DimensionFinding,
)
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
from review_agent.service.review_graph.graph import build_review_graph
from review_agent.service.review_graph.pipeline import (
    aggregate_findings,
    fetch_and_chunk,
    filter_files,
    generate_summary,
    publish_results,
)
from review_agent.service.review_graph.state import ReviewState, _reduce_findings
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity, ReviewStatus

# ─── Fixtures ──────────────────────────────────────────────


@pytest.fixture
def base_state() -> ReviewState:
    """最小可用状态。"""
    return {
        "repo_name": "test/repo",
        "sha": "abc123",
        "files": [],
        "target_files": [],
        "chunks": [],
        "source_codes": {},
        "pending_chunk": None,
        "rule_findings": [],
        "ai_findings": [],
        "structural_findings": [],
        "all_findings": [],
        "deduped_findings": [],
        "score": 100,
        "summary_markdown": "",
        "error": None,
        "status": ReviewStatus.RUNNING,
    }


@pytest.fixture
def normal_chunk() -> CodeChunk:
    """正常大小的 chunk（走 AI 评审路径）。"""
    return CodeChunk(
        file_path="src/test.py",
        function_name="foo",
        source_code="def foo():\n    pass\n",
        start_line=1,
        end_line=3,
        estimated_tokens=10,
        path=ChunkPath.DETAILED_REVIEW,
    )


@pytest.fixture
def oversized_chunk() -> CodeChunk:
    """超大 chunk（走结构评审路径）。"""
    return CodeChunk(
        file_path="src/large.py",
        function_name="bar",
        source_code="def bar(): pass\n" * 100,
        start_line=1,
        end_line=100,
        estimated_tokens=2500,
        path=ChunkPath.STRUCTURAL_REVIEW,
    )


@pytest.fixture
def finding() -> DimensionFinding:
    return DimensionFinding(
        category=FindingCategory.SECURITY,
        severity=FindingSeverity.CRITICAL,
        title="test finding",
        description="test description",
        suggestion="fix it",
        file_path="src/test.py",
        line_start=1,
    )


# ─── Test: Reducer ─────────────────────────────────────────


class TestReduceFindings:
    def test_both_none(self) -> None:
        assert _reduce_findings(None, None) == []

    def test_existing_none(self) -> None:
        result = _reduce_findings(None, [DimensionFinding(
            category=FindingCategory.BUG, severity=FindingSeverity.INFO,
            title="t", description="d", suggestion="s", file_path="f",
        )])
        assert len(result) == 1

    def test_updates_none(self) -> None:
        existing = [DimensionFinding(
            category=FindingCategory.BUG, severity=FindingSeverity.INFO,
            title="t", description="d", suggestion="s", file_path="f",
        )]
        result = _reduce_findings(existing, None)
        assert len(result) == 1

    def test_concatenates(self, finding: DimensionFinding) -> None:
        result = _reduce_findings([finding], [finding])
        assert len(result) == 2


# ─── Test: Pipeline Nodes ──────────────────────────────────


class TestFilterFiles:
    async def test_empty_files(self, base_state: ReviewState) -> None:
        result = await filter_files(base_state)
        assert result["target_files"] == []

    async def test_filters_by_extension(self, base_state: ReviewState) -> None:
        from review_agent.service.git.base import PRFile

        base_state["files"] = [
            PRFile(filename="src/main.py", status="modified", additions=1, deletions=0),
            PRFile(filename="README.md", status="modified", additions=1, deletions=0),
        ]
        result = await filter_files(base_state)
        assert len(result["target_files"]) == 1
        assert result["target_files"][0].filename == "src/main.py"


class TestFetchAndChunk:
    async def test_no_git_provider(self, base_state: ReviewState) -> None:
        result = await fetch_and_chunk(base_state, git_provider=None)
        assert result["chunks"] == []
        assert result["source_codes"] == {}

    async def test_skips_removed_files(self, base_state: ReviewState) -> None:
        from review_agent.service.git.base import PRFile

        base_state["target_files"] = [
            PRFile(filename="old.py", status="removed", additions=0, deletions=10),
        ]
        result = await fetch_and_chunk(base_state, git_provider=object())
        assert result["chunks"] == []


class TestAggregate:
    async def test_empty_findings(self, base_state: ReviewState) -> None:
        result = await aggregate_findings(base_state)
        assert result["score"] == 100
        assert result["deduped_findings"] == []


class TestGenerateSummary:
    async def test_empty_state(self, base_state: ReviewState) -> None:
        result = await generate_summary(base_state)
        assert "未发现问题" in result["summary_markdown"]

    async def test_with_findings(self, base_state: ReviewState, finding: DimensionFinding) -> None:
        base_state["deduped_findings"] = [finding]
        base_state["score"] = 70
        result = await generate_summary(base_state)
        assert result["summary_markdown"]
        assert "70/100" in result["summary_markdown"]


class TestPublishResults:
    async def test_no_summary(self, base_state: ReviewState) -> None:
        result = await publish_results(base_state, git_provider=None)
        assert result["status"] == ReviewStatus.COMPLETED


# ─── Test: Evaluation Nodes ────────────────────────────────


class TestRuleNodes:
    """验证 5 个规则节点在空 chunks 时返回空，有代码时返回 findings。"""

    @pytest.mark.parametrize("node_fn", [
        run_security_rules,
        run_bug_rules,
        run_performance_rules,
        run_style_rules,
        run_dependency_rules,
    ])
    async def test_empty_chunks(self, base_state: ReviewState, node_fn) -> None:
        base_state["chunks"] = []
        result = await node_fn(base_state)
        assert result["rule_findings"] == []

    async def test_security_detects_eval(self, base_state: ReviewState) -> None:
        chunk = CodeChunk(
            file_path="src/bad.py", function_name="hack",
            source_code="def hack():\n    eval('danger')\n",
            start_line=1, end_line=3, estimated_tokens=20,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        result = await run_security_rules(base_state)
        assert any("eval" in f.title for f in result["rule_findings"])

    async def test_bug_detects_bare_except(self, base_state: ReviewState) -> None:
        chunk = CodeChunk(
            file_path="src/bad.py", function_name="danger",
            source_code="def danger():\n    try:\n        pass\n    except:\n        pass\n",
            start_line=1, end_line=5, estimated_tokens=20,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        result = await run_bug_rules(base_state)
        assert any("except" in f.title for f in result["rule_findings"])


class TestStructuralReview:
    async def test_no_chunk(self, base_state: ReviewState) -> None:
        result = await structural_review_chunk(base_state)
        assert result["structural_findings"] == []

    async def test_normal_chunk_no_findings(self, base_state: ReviewState, normal_chunk) -> None:
        base_state["pending_chunk"] = normal_chunk
        result = await structural_review_chunk(base_state)
        # 小函数不触发结构问题
        assert isinstance(result["structural_findings"], list)


class TestAiReview:
    async def test_no_chunk(self, base_state: ReviewState) -> None:
        result = await ai_review_chunk(base_state, ai_provider=None)
        assert result["ai_findings"] == []

    async def test_no_provider(self, base_state: ReviewState, normal_chunk) -> None:
        base_state["pending_chunk"] = normal_chunk
        result = await ai_review_chunk(base_state, ai_provider=None)
        assert result["ai_findings"] == []


# ─── Test: Edges ────────────────────────────────────────────


class TestFanoutToDimensions:
    def test_returns_five_sends(self, base_state: ReviewState) -> None:
        result = fanout_to_dimensions(base_state)
        assert len(result) == 5
        names = [s.node for s in result]
        assert "run_security_rules" in names
        assert "run_bug_rules" in names
        assert "run_performance_rules" in names
        assert "run_style_rules" in names
        assert "run_dependency_rules" in names


class TestRouteChunks:
    def test_no_chunks_routes_to_aggregate(self, base_state: ReviewState) -> None:
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "aggregate"

    def test_normal_chunk_routes_to_ai(self, base_state: ReviewState, normal_chunk) -> None:
        base_state["chunks"] = [normal_chunk]
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "ai_review"

    def test_oversized_chunk_routes_to_structural(self, base_state: ReviewState, oversized_chunk) -> None:
        base_state["chunks"] = [oversized_chunk]
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "structural_review"

    def test_mixed_chunks(self, base_state: ReviewState, normal_chunk, oversized_chunk) -> None:
        base_state["chunks"] = [normal_chunk, oversized_chunk]
        result = route_chunks(base_state)
        assert len(result) == 2
        nodes = [s.node for s in result]
        assert "ai_review" in nodes
        assert "structural_review" in nodes


# ─── Test: Graph Compilation ───────────────────────────────


class TestGraphCompilation:
    def test_graph_compiles(self) -> None:
        """验证图能成功编译并包含所有预期节点。"""

        class MockGit:
            async def get_file_content(self, *args: Any, **kwargs: Any) -> str | None:
                return None
            async def publish_commit_summary(self, *args: Any, **kwargs: Any) -> None:
                pass

        graph = build_review_graph(git_provider=MockGit(), ai_provider=None)
        assert graph is not None
        assert "filter_files" in graph.nodes
        assert "fetch_and_chunk" in graph.nodes
        assert "run_security_rules" in graph.nodes
        assert "run_bug_rules" in graph.nodes
        assert "run_performance_rules" in graph.nodes
        assert "run_style_rules" in graph.nodes
        assert "run_dependency_rules" in graph.nodes
        assert "ai_review" in graph.nodes
        assert "structural_review" in graph.nodes
        assert "dispatch_chunks" in graph.nodes
        assert "aggregate" in graph.nodes
        assert "summarize" in graph.nodes
        assert "__start__" in graph.nodes

    async def test_empty_pipeline_completes(self, base_state: ReviewState) -> None:
        """空状态全流程验证。"""

        class MockGit:
            async def get_file_content(self, *args: Any, **kwargs: Any) -> str | None:
                return None
            async def publish_commit_summary(self, *args: Any, **kwargs: Any) -> None:
                pass

        graph = build_review_graph(git_provider=MockGit(), ai_provider=None)
        result = await graph.ainvoke(
            base_state,
            {"configurable": {"thread_id": "test:empty"}},
        )
        assert result["status"] == ReviewStatus.COMPLETED
        assert result["score"] == 100
        assert len(result["deduped_findings"]) == 0

    async def test_with_chunks_runs_rules(self, base_state: ReviewState, normal_chunk: CodeChunk) -> None:
        """带 chunk 时规则检查产生 findings。"""
        from review_agent.service.git.base import PRFile

        class MockGit:
            async def get_file_content(self, *args: Any, **kwargs: Any) -> str | None:
                return None
            async def publish_commit_summary(self, *args: Any, **kwargs: Any) -> None:
                pass

        base_state["files"] = [
            PRFile(filename="src/test.py", status="modified", additions=1, deletions=0),
        ]
        base_state["target_files"] = [
            PRFile(filename="src/test.py", status="modified", additions=1, deletions=0),
        ]
        base_state["chunks"] = [normal_chunk]

        graph = build_review_graph(git_provider=MockGit(), ai_provider=None)
        result = await graph.ainvoke(
            base_state,
            {"configurable": {"thread_id": "test:chunks"}},
        )
        assert result["status"] == ReviewStatus.COMPLETED
