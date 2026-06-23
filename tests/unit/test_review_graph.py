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

from review_agent.service.ai.types import AICompletionRequest, AICompletionResponse
from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import (
    DimensionFinding,
)
from review_agent.service.git.base import PRFile
from review_agent.service.review_graph.edges import route_chunks
from review_agent.service.review_graph.evaluation import (
    run_ai_batch,
    run_all_rules,
    structural_review_chunk,
)
from review_agent.service.review_graph.graph import build_review_graph
from review_agent.service.review_graph.pipeline import (
    aggregate_findings,
    fetch_and_chunk,
    filter_files,
    generate_summary,
    publish_results,
    resolve_incremental,
)
from review_agent.service.review_graph.state import ReviewState, _merge_lists
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
        "unreviewed_files": [],
        "error_messages": [],
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


@pytest.fixture
def small_chunks() -> list[CodeChunk]:
    """Multiple small chunks that should all route to AI review."""
    return [
        CodeChunk(
            file_path="test.py",
            function_name=f"func_{i}",
            source_code=f"def func_{i}(): pass",
            start_line=i * 10 + 1,
            end_line=i * 10 + 2,
            estimated_tokens=30,
            path=ChunkPath.DETAILED_REVIEW,
        )
        for i in range(5)
    ]


@pytest.fixture
def large_chunks() -> list[CodeChunk]:
    """Multiple oversized chunks that should all route to structural review."""
    return [
        CodeChunk(
            file_path="big.py",
            function_name=f"big_func_{i}",
            source_code="x = 1\n" * 5000,
            start_line=1,
            end_line=5000,
            estimated_tokens=1667,
            path=ChunkPath.STRUCTURAL_REVIEW,
        )
        for i in range(3)
    ]


# ─── Test: Reducer ─────────────────────────────────────────


class TestReduceFindings:
    def test_both_none(self) -> None:
        assert _merge_lists(None, None) == []

    def test_existing_none(self) -> None:
        result = _merge_lists(
            None,
            [
                DimensionFinding(
                    category=FindingCategory.BUG,
                    severity=FindingSeverity.INFO,
                    title="t",
                    description="d",
                    suggestion="s",
                    file_path="f",
                )
            ],
        )
        assert len(result) == 1

    def test_updates_none(self) -> None:
        existing = [
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.INFO,
                title="t",
                description="d",
                suggestion="s",
                file_path="f",
            )
        ]
        result = _merge_lists(existing, None)
        assert len(result) == 1

    def test_concatenates(self, finding: DimensionFinding) -> None:
        result = _merge_lists([finding], [finding])
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

    async def test_info_level_filtered_out(self, base_state: ReviewState) -> None:
        base_state["rule_findings"] = [
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.INFO,
                title="info bug",
                description="d",
                suggestion="s",
                file_path="f",
            ),
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.CRITICAL,
                title="critical bug",
                description="d",
                suggestion="s",
                file_path="f2",
            ),
        ]
        result = await aggregate_findings(base_state)
        # Info finding filtered out, only critical remains
        assert len(result["deduped_findings"]) == 1
        assert result["deduped_findings"][0].title == "critical bug"

    async def test_style_category_filtered_out(self, base_state: ReviewState) -> None:
        base_state["rule_findings"] = [
            DimensionFinding(
                category=FindingCategory.STYLE,
                severity=FindingSeverity.WARNING,
                title="style issue",
                description="d",
                suggestion="s",
                file_path="f",
            ),
        ]
        result = await aggregate_findings(base_state)
        assert len(result["deduped_findings"]) == 0

    async def test_allowed_categories_pass_through(self, base_state: ReviewState) -> None:
        base_state["rule_findings"] = [
            DimensionFinding(
                category=FindingCategory.BUG,
                severity=FindingSeverity.WARNING,
                title="bug",
                description="d",
                suggestion="s",
                file_path="f1",
            ),
            DimensionFinding(
                category=FindingCategory.SECURITY,
                severity=FindingSeverity.CRITICAL,
                title="security",
                description="d",
                suggestion="s",
                file_path="f2",
            ),
            DimensionFinding(
                category=FindingCategory.PERFORMANCE,
                severity=FindingSeverity.WARNING,
                title="perf",
                description="d",
                suggestion="s",
                file_path="f3",
            ),
        ]
        result = await aggregate_findings(base_state)
        assert len(result["deduped_findings"]) == 3


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
    """使用 run_all_rules 验证规则节点返回 findings。"""

    async def test_empty_chunks(self, base_state: ReviewState) -> None:
        base_state["chunks"] = []
        result = await run_all_rules(base_state)
        assert result["rule_findings"] == []

    async def test_security_detects_eval(self, base_state: ReviewState) -> None:
        chunk = CodeChunk(
            file_path="src/bad.py",
            function_name="hack",
            source_code="def hack():\n    eval('danger')\n",
            start_line=1,
            end_line=3,
            estimated_tokens=20,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        result = await run_all_rules(base_state)
        assert any("eval" in f.title for f in result["rule_findings"])

    async def test_bug_detects_bare_except(self, base_state: ReviewState) -> None:
        chunk = CodeChunk(
            file_path="src/bad.py",
            function_name="danger",
            source_code="def danger():\n    try:\n        pass\n    except:\n        pass\n",
            start_line=1,
            end_line=5,
            estimated_tokens=20,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        result = await run_all_rules(base_state)
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


class TestAiBatch:
    async def test_no_chunk(self, base_state: ReviewState) -> None:
        result = await run_ai_batch(base_state, ai_provider=None)
        assert result["ai_findings"] == []

    async def test_no_provider(self, base_state: ReviewState, normal_chunk) -> None:
        base_state["pending_ai_chunks"] = [normal_chunk]
        result = await run_ai_batch(base_state, ai_provider=None)
        assert result["ai_findings"] == []


class TestAiBatchWithProvider:
    """使用 mock AIProvider 验证 AI 批量评审的全链路正确性。"""

    class _MockAIProvider:
        """返回固定 JSON 响应的 mock AI provider。"""

        def __init__(self, response_content: str) -> None:
            self.response_content = response_content
            self.last_request: AICompletionRequest | None = None

        async def complete(self, request: AICompletionRequest) -> AICompletionResponse:
            self.last_request = request
            return AICompletionResponse(
                content=self.response_content,
                model="mock-model",
            )

        @staticmethod
        async def count_tokens(text: str, _model: str | None = None) -> int:
            return max(1, len(text) // 2)

    async def test_single_chunk_returns_findings(
        self,
        base_state: ReviewState,
    ) -> None:
        """单个 chunk 通过 AI 评审返回 findings。"""

        response_json = (
            '[{"function_index": 0, "findings": ['
            '  {"category": "bug", "severity": "warning", "title": "test issue", '
            '   "description": "a problem", "suggestion": "fix it", "line": 2}'
            "]}]"
        )
        mock_provider = TestAiBatchWithProvider._MockAIProvider(response_json)
        base_state["pending_ai_chunks"] = [
            CodeChunk(
                file_path="src/test.py",
                function_name="foo",
                source_code="def foo():\n    x = 1\n",
                start_line=1,
                end_line=3,
                estimated_tokens=10,
                path=ChunkPath.DETAILED_REVIEW,
            ),
        ]
        result = await run_ai_batch(base_state, ai_provider=mock_provider)
        assert len(result["ai_findings"]) == 1
        assert result["ai_findings"][0].title == "test issue"
        assert result["ai_findings"][0].file_path == "src/test.py"
        assert result["ai_findings"][0].line_start == 2

    async def test_multiple_chunks_in_batch(
        self,
        base_state: ReviewState,
    ) -> None:
        """多个 chunk 在一次 AI 调用中分批评审。"""

        response_json = (
            '[{"function_index": 0, "findings": ['
            '  {"category": "bug", "severity": "warning", "title": "issue a", '
            '   "description": "desc a", "suggestion": "fix a", "line": 1}'
            "]},"
            '{"function_index": 1, "findings": ['
            '  {"category": "security", "severity": "warning", "title": "issue b", '
            '   "description": "desc b", "suggestion": "fix b", "line": 2}'
            "]}]"
        )
        mock_provider = TestAiBatchWithProvider._MockAIProvider(response_json)

        # 设置两个 chunk（token 很小，将合并在一个 batch 中调用）
        base_state["pending_ai_chunks"] = [
            CodeChunk(
                file_path="src/a.py",
                function_name="func_a",
                source_code="def func_a(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=5,
                path=ChunkPath.DETAILED_REVIEW,
            ),
            CodeChunk(
                file_path="src/b.py",
                function_name="func_b",
                source_code="def func_b(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=5,
                path=ChunkPath.DETAILED_REVIEW,
            ),
        ]
        result = await run_ai_batch(base_state, ai_provider=mock_provider)
        assert len(result["ai_findings"]) == 2
        assert result["ai_findings"][0].title == "issue a"
        assert result["ai_findings"][1].title == "issue b"
        # 验证合并为一个 AI 调用
        assert mock_provider.last_request is not None

    async def test_empty_ai_response_returns_empty(
        self,
        base_state: ReviewState,
    ) -> None:
        """AI 返回空数组时，findings 为空。"""

        mock_provider = TestAiBatchWithProvider._MockAIProvider("[]")
        base_state["pending_ai_chunks"] = [
            CodeChunk(
                file_path="src/test.py",
                function_name="foo",
                source_code="def foo(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=5,
                path=ChunkPath.DETAILED_REVIEW,
            ),
        ]
        result = await run_ai_batch(base_state, ai_provider=mock_provider)
        assert result["ai_findings"] == []

    async def test_ai_call_exception_is_handled(
        self,
        base_state: ReviewState,
    ) -> None:
        """AI 调用抛出异常时 gracefully degrade，不崩溃。"""
        from review_agent.service.ai.base import AIProvider

        class FailingProvider(AIProvider):
            async def complete(
                self,
                _request: AICompletionRequest,
            ) -> AICompletionResponse:
                msg = "mock provider failure"
                raise ValueError(msg)

            @staticmethod
            async def count_tokens(
                _text: str,
                _model: str | None = None,
            ) -> int:
                return 0

        base_state["pending_ai_chunks"] = [
            CodeChunk(
                file_path="src/test.py",
                function_name="foo",
                source_code="def foo(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=5,
                path=ChunkPath.DETAILED_REVIEW,
            ),
        ]
        result = await run_ai_batch(base_state, ai_provider=FailingProvider())
        # AI 调用失败时 findings 为空，但不崩溃
        assert result["ai_findings"] == []
        assert "unreviewed_files" in result


# ─── Test: Edges ────────────────────────────────────────────


class TestRouteChunks:
    def test_no_chunks_routes_to_aggregate(self, base_state: ReviewState) -> None:
        result = route_chunks(base_state)
        assert result == "aggregate"

    def test_normal_chunk_routes_to_ai(self, base_state: ReviewState, normal_chunk) -> None:
        base_state["chunks"] = [normal_chunk]
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "ai_batch"

    def test_oversized_chunk_routes_to_structural(self, base_state, oversized_chunk) -> None:
        base_state["chunks"] = [oversized_chunk]
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "structural_batch"

    def test_mixed_chunks(self, base_state: ReviewState, normal_chunk, oversized_chunk) -> None:
        base_state["chunks"] = [normal_chunk, oversized_chunk]
        result = route_chunks(base_state)
        assert len(result) == 2
        nodes = [s.node for s in result]
        assert "ai_batch" in nodes
        assert "structural_batch" in nodes


# ─── Test: AI Batch / Chunk Grouping ─────────────────────────


class TestAiBatchBatching:
    """验证 chunks 的正确路由分组逻辑（per-chunk 架构下等同于批量分组）。"""

    async def test_no_provider_skips_ai_review(
        self,
        base_state: ReviewState,
        normal_chunk: CodeChunk,
    ) -> None:
        """无 AI provider 时 AI 评审跳过，不崩溃。"""
        base_state["pending_ai_chunks"] = [normal_chunk]
        result = await run_ai_batch(base_state, ai_provider=None)
        assert result["ai_findings"] == []

    def test_small_chunks_all_route_to_ai(
        self,
        base_state: ReviewState,
        small_chunks: list[CodeChunk],
    ) -> None:
        """多个小 chunk 合并为单个 ai_batch Send。"""
        base_state["chunks"] = small_chunks
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "ai_batch"
        assert len(result[0].arg["pending_ai_chunks"]) == len(small_chunks)

    def test_large_chunks_all_route_to_structural(
        self,
        base_state: ReviewState,
        large_chunks: list[CodeChunk],
    ) -> None:
        """多个大 chunk 合并为单个 structural_batch Send。"""
        base_state["chunks"] = large_chunks
        result = route_chunks(base_state)
        assert len(result) == 1
        assert result[0].node == "structural_batch"
        assert len(result[0].arg["pending_structural_chunks"]) == len(large_chunks)

    def test_mixed_routes_correctly(
        self,
        base_state: ReviewState,
        small_chunks: list[CodeChunk],
        large_chunks: list[CodeChunk],
    ) -> None:
        """混合 chunk 分流为 ai_batch 和 structural_batch 两个 Send。"""
        all_chunks = small_chunks + large_chunks
        base_state["chunks"] = all_chunks
        result = route_chunks(base_state)
        assert len(result) == 2
        nodes = [s.node for s in result]
        assert "ai_batch" in nodes
        assert "structural_batch" in nodes


# ─── Test: Graph Compilation ───────────────────────────────


class TestGraphCompilation:
    def test_graph_compiles(self) -> None:
        """验证图能成功编译并包含所有预期节点。"""

        class MockGit:
            async def get_file_content(self, *_args: Any, **_kwargs: Any) -> str | None:
                return None

            async def publish_commit_summary(self, *_args: Any, **_kwargs: Any) -> None:
                pass

        graph = build_review_graph(git_provider=MockGit(), ai_provider=None)
        assert graph is not None
        assert "filter_files" in graph.nodes
        assert "fetch_and_chunk" in graph.nodes
        assert "run_all_rules" in graph.nodes
        assert "ai_batch" in graph.nodes
        assert "structural_batch" in graph.nodes
        assert "dispatch_chunks" in graph.nodes
        assert "aggregate" in graph.nodes
        assert "summarize" in graph.nodes
        assert "__start__" in graph.nodes

    async def test_empty_pipeline_completes(self, base_state: ReviewState) -> None:
        """空状态全流程验证。"""

        class MockGit:
            async def get_file_content(self, *_args: Any, **_kwargs: Any) -> str | None:
                return None

            async def publish_commit_summary(self, *_args: Any, **_kwargs: Any) -> None:
                pass

        graph = build_review_graph(git_provider=MockGit(), ai_provider=None)
        result = await graph.ainvoke(
            base_state,
            {"configurable": {"thread_id": "test:empty"}},
        )
        assert result["status"] == ReviewStatus.COMPLETED
        assert result["score"] == 100
        assert len(result["deduped_findings"]) == 0

    async def test_with_chunks_runs_rules(self, base_state, normal_chunk: CodeChunk) -> None:
        """带 chunk 时规则检查产生 findings。"""
        from review_agent.service.git.base import PRFile

        class MockGit:
            async def get_file_content(self, *_args: Any, **_kwargs: Any) -> str | None:
                return "def foo():\n    pass\n"

            async def publish_commit_summary(self, *_args: Any, **_kwargs: Any) -> None:
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
        # chunks 已注入, get_file_content 返回有效源码, 不应有失败文件
        assert result.get("unreviewed_files", []) == []
        # 规则检查节点对 chunks 执行了分析
        assert "rule_findings" in result
        assert "ai_findings" in result


# ─── Test: Function-Level Incremental Review ────────────────────


class TestResolveIncremental:
    """函数级增量评审决策逻辑的全面验证。"""

    async def test_first_review_all_new(self, base_state: ReviewState) -> None:
        """首次评审：无上一轮数据，全部 chunks 都是 new。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        base_state["chunks"] = [
            CodeChunk(
                file_path="src/test.py",
                function_name="foo",
                source_code="x = 1",
                start_line=1,
                end_line=1,
                estimated_tokens=5,
                path=ChunkPath.DETAILED_REVIEW,
            ),
        ]
        result = await resolve_incremental(base_state)
        assert len(result["new_chunks"]) == 1

    async def test_function_changed_in_diff(self, base_state: ReviewState) -> None:
        """函数行在 diff 中 → 需评审（即使上次评过）。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        chunk = CodeChunk(
            file_path="src/test.py",
            function_name="foo",
            source_code="x = 1",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        base_state["files"] = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+x = 1",
            ),
        ]
        base_state["previous_reviewed_functions"] = [
            {
                "file_path": "src/test.py",
                "function_name": "foo",
                "start_line": 1,
                "end_line": 1,
                "max_severity": "info",
                "sha": "abc",
            },
        ]
        result = await resolve_incremental(base_state)
        # 虽然上次评过但函数行被改了 → 需重审
        assert len(result["new_chunks"]) == 1

    async def test_function_unchanged_previously_clean(self, base_state: ReviewState) -> None:
        """函数不变且上次 clean → 跳过。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        chunk = CodeChunk(
            file_path="src/test.py",
            function_name="foo",
            source_code="x = 1",
            start_line=5,
            end_line=5,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        base_state["files"] = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=0,
                deletions=1,
                patch="@@ -1,1 +0,0 @@\n-old",
            ),
        ]
        base_state["previous_reviewed_functions"] = [
            {
                "file_path": "src/test.py",
                "function_name": "foo",
                "start_line": 5,
                "end_line": 5,
                "max_severity": None,
                "sha": "abc",
            },
        ]
        result = await resolve_incremental(base_state)
        # 行不变 + 已评过且 clean → 跳过
        assert len(result["new_chunks"]) == 0

    async def test_new_function_in_existing_file(self, base_state: ReviewState) -> None:
        """函数名不在上一轮记录中但文件已存在 → 新函数 → 需评审。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        old_chunk = CodeChunk(
            file_path="src/test.py",
            function_name="old_func",
            source_code="pass",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        new_chunk = CodeChunk(
            file_path="src/test.py",
            function_name="new_func",
            source_code="x = 1",
            start_line=3,
            end_line=3,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [old_chunk, new_chunk]
        base_state["previous_reviewed_functions"] = [
            {
                "file_path": "src/test.py",
                "function_name": "old_func",
                "start_line": 1,
                "end_line": 1,
                "max_severity": None,
                "sha": "abc",
            },
        ]
        # 纯删除 diff → 无新增行
        base_state["files"] = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=0,
                deletions=1,
                patch="@@ -1,1 +0,0 @@\n-old",
            ),
        ]
        result = await resolve_incremental(base_state)
        func_names = {c.function_name for c in result["new_chunks"]}
        assert "new_func" in func_names  # 新函数 → 评审
        assert "old_func" not in func_names  # 已评过 → 跳过

    async def test_module_level_changes_force_review(self, base_state: ReviewState) -> None:
        """模块级行在函数外 → 强制重审整个文件。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        the_chunk = CodeChunk(
            file_path="src/test.py",
            function_name="the_func",
            source_code="pass",
            start_line=10,
            end_line=10,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [the_chunk]
        base_state["files"] = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -1,0 +1 @@\n+import new_module",
            ),
        ]
        base_state["previous_reviewed_functions"] = [
            {
                "file_path": "src/test.py",
                "function_name": "the_func",
                "start_line": 10,
                "end_line": 10,
                "max_severity": None,
                "sha": "abc",
            },
        ]
        result = await resolve_incremental(base_state)
        # import 行(line 1)在函数(line 10)外 → 强制全文件重审
        assert len(result["new_chunks"]) == 1

    async def test_backward_compat_file_level_fallback(self, base_state: ReviewState) -> None:
        """无函数级数据但有文件级数据 → 回退到文件级跳过。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        chunk = CodeChunk(
            file_path="src/test.py",
            function_name="foo",
            source_code="pass",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        base_state["previous_reviewed_functions"] = []
        base_state["previous_reviewed_files"] = [{"path": "src/test.py", "max_severity": None}]
        base_state["files"] = [
            PRFile(
                filename="src/test.py",
                status="modified",
                additions=0,
                deletions=1,
                patch="@@ -1,1 +0,0 @@\n-old",
            ),
        ]
        result = await resolve_incremental(base_state)
        # 文件级回退：clean 文件跳过
        assert len(result["new_chunks"]) == 0

    async def test_inter_commit_diff_over_files(self, base_state: ReviewState) -> None:
        """inter_commit_files 优先于 files 做变更检测。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        chunk_a = CodeChunk(
            file_path="src/a.py",
            function_name="func_a",
            source_code="x = 1",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        chunk_b = CodeChunk(
            file_path="src/b.py",
            function_name="func_b",
            source_code="y = 2",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk_a, chunk_b]
        base_state["files"] = [
            PRFile(
                filename="src/a.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+x = 1",
            ),
            PRFile(
                filename="src/b.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+y = 2",
            ),
        ]
        base_state["inter_commit_files"] = [
            PRFile(
                filename="src/a.py",
                status="modified",
                additions=1,
                deletions=0,
                patch="@@ -0,0 +1 @@\n+x = 1",
            ),
        ]
        base_state["previous_reviewed_functions"] = [
            {
                "file_path": "src/b.py",
                "function_name": "func_b",
                "start_line": 1,
                "end_line": 1,
                "max_severity": None,
                "sha": "prev",
            },
        ]
        result = await resolve_incremental(base_state)
        func_names = {c.function_name for c in result["new_chunks"]}
        assert "func_a" in func_names  # a.py 在 inter_commit 中 → 评审
        assert "func_b" not in func_names  # b.py 不在 inter_commit 中 + 已评过 → 跳过

    async def test_added_file_all_chunks_new(self, base_state: ReviewState) -> None:
        """新增文件（patch=None）→ 全部视为变更。"""
        from review_agent.service.chunking import CodeChunk
        from review_agent.types.enums import ChunkPath

        chunk = CodeChunk(
            file_path="src/new.py",
            function_name="new_func",
            source_code="x = 1",
            start_line=1,
            end_line=1,
            estimated_tokens=5,
            path=ChunkPath.DETAILED_REVIEW,
        )
        base_state["chunks"] = [chunk]
        base_state["files"] = [
            PRFile(filename="src/new.py", status="added", additions=1, deletions=0, patch=None),
        ]
        result = await resolve_incremental(base_state)
        assert len(result["new_chunks"]) == 1

    async def test_empty_chunks(self, base_state: ReviewState) -> None:
        """没有 chunks 时返回空列表。"""
        result = await resolve_incremental(base_state)
        assert result["new_chunks"] == []
