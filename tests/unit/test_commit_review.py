"""Tests for CommitReviewService."""

from unittest.mock import MagicMock

import pytest

from review_agent.service.chunking import CodeChunk
from review_agent.service.commit_review import CommitReviewResult, CommitReviewService
from review_agent.service.git.base import PRFile
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity


class MockAIProvider:
    """Mock AI provider that returns predefined findings."""

    def __init__(self, findings_json: str = "[]") -> None:
        self.findings_json = findings_json

    async def complete(self, _request: object) -> MagicMock:
        resp = MagicMock()
        resp.content = self.findings_json
        return resp

    async def count_tokens(self, text: str, _model: str | None = None) -> int:
        return len(text) // 3


class MockGitProvider:
    """Mock Git provider for testing."""

    def __init__(self) -> None:
        self.files: dict[str, str] = {}

    async def get_file_content(
        self, _repo_name: str, file_path: str, _ref: str
    ) -> str | None:
        return self.files.get(file_path)


class TestCommitReviewService:
    def test_should_skip_file_by_extension(self) -> None:
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        assert service._should_skip_file("readme.md") is True
        assert service._should_skip_file("docs/guide.rst") is True
        assert service._should_skip_file("main.py") is False
        assert service._should_skip_file("src/app.ts") is False

    async def test_review_commit_empty_files(self) -> None:
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        result = await service.review_commit("owner/repo", "abc123", [])
        assert isinstance(result, CommitReviewResult)
        assert result.findings == []
        assert result.score == 100
        assert "未发现问题" in result.summary_markdown

    async def test_review_commit_skips_removed_files(self) -> None:
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        files = [PRFile(filename="old.py", status="removed", additions=0, deletions=10)]
        result = await service.review_commit("owner/repo", "abc123", files)
        assert result.findings == []

    async def test_review_commit_skips_md_files(self) -> None:
        git = MockGitProvider()
        git.files["readme.md"] = "# Hello"
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        files = [PRFile(filename="readme.md", status="modified", additions=1, deletions=0)]
        result = await service.review_commit("owner/repo", "abc123", files)
        assert result.findings == []

    async def test_review_commit_rules_for_all_chunks(self) -> None:
        """Rule-based dimension checks run on all chunks."""
        code = """
def unsafe_function(data):
    result = execute("SELECT * FROM " + data)
    return result
"""
        git = MockGitProvider()
        git.files["app.py"] = code
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        files = [PRFile(filename="app.py", status="modified", additions=5, deletions=0)]
        result = await service.review_commit("owner/repo", "abc123", files)

        # Should find SQL injection pattern via rule check
        assert len(result.findings) >= 1
        assert any("SQL" in f.title or "拼接" in f.title for f in result.findings)

    async def test_ai_review_with_valid_json(self) -> None:
        """AI review with valid JSON response should produce findings."""
        ai_response = """```json
[
  {
    "severity": "warning",
    "title": "Missing error handling",
    "description": "No try/except around file open",
    "suggestion": "Wrap in try/except",
    "line": 5
  }
]
```"""
        git = MockGitProvider()
        git.files["app.py"] = "def read_file(path):\n    f = open(path)\n    return f.read()"
        ai = MockAIProvider(findings_json=ai_response)
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        files = [PRFile(
            filename="app.py", status="added", additions=3, deletions=0,
            patch="+def read_file...",
        )]
        result = await service.review_commit("owner/repo", "abc123", files)

        assert len(result.findings) >= 1
        ai_findings = [f for f in result.findings if f.category == FindingCategory.BUG]
        assert len(ai_findings) >= 1
        assert ai_findings[0].title == "Missing error handling"
        assert ai_findings[0].line_start == 5

    async def test_parse_ai_response_empty(self) -> None:
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        chunk = CodeChunk(
            file_path="test.py",
            function_name="foo",
            source_code="def foo(): pass",
            start_line=1,
            end_line=1,
            estimated_tokens=10,
            path=ChunkPath.DETAILED_REVIEW,
        )
        findings = service._parse_ai_response("[]", chunk)
        assert findings == []

    async def test_parse_ai_response_invalid_json(self) -> None:
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        chunk = CodeChunk(
            file_path="test.py",
            function_name="foo",
            source_code="def foo(): pass",
            start_line=1,
            end_line=1,
            estimated_tokens=10,
            path=ChunkPath.DETAILED_REVIEW,
        )
        findings = service._parse_ai_response("not json at all", chunk)
        assert findings == []

    async def test_parse_ai_response_no_markdown(self) -> None:
        """Plain JSON array without markdown fences should also parse."""
        git = MockGitProvider()
        ai = MockAIProvider()
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        chunk = CodeChunk(
            file_path="test.py",
            function_name="foo",
            source_code="def foo(): pass",
            start_line=1,
            end_line=1,
            estimated_tokens=10,
            path=ChunkPath.DETAILED_REVIEW,
        )
        findings = service._parse_ai_response(
            '[{"severity": "critical", "title": "Bug", "description": "d", "suggestion": "s"}]',
            chunk,
        )
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.CRITICAL

    async def test_ai_review_handles_exception_gracefully(self) -> None:
        """If AI provider raises, review should continue without findings."""
        git = MockGitProvider()
        git.files["app.py"] = "def foo():\n    pass"

        class FailingAI:
            async def complete(self, _request: object) -> object:
                msg = "API error"
                raise RuntimeError(msg)

            async def count_tokens(self, text: str, _model: str | None = None) -> int:
                return len(text) // 3

        service = CommitReviewService(git_provider=git, ai_provider=FailingAI())  # type: ignore[arg-type]
        files = [PRFile(filename="app.py", status="added", additions=1, deletions=0)]
        result = await service.review_commit("owner/repo", "abc123", files)
        # Should not crash - returns empty findings gracefully
        assert isinstance(result, CommitReviewResult)


@pytest.mark.asyncio
class TestCommitReviewIntegration:
    async def test_review_commit_returns_summary(self) -> None:
        """End-to-end test with mocked providers."""
        code = """
def process(data):
    result = execute(data)
    return result
"""
        git = MockGitProvider()
        git.files["process.py"] = code
        ai = MockAIProvider(findings_json="[]")
        service = CommitReviewService(git_provider=git, ai_provider=ai)  # type: ignore[arg-type]

        files = [PRFile(
            filename="process.py",
            status="modified",
            additions=3,
            deletions=1,
            patch="@@ -1,3 +1,3 @@\n-def old():\n+def process(data):",
        )]
        result = await service.review_commit("owner/repo", "abc123", files)

        assert result.score >= 0
        assert isinstance(result.summary_markdown, str)
        assert len(result.summary_markdown) > 10
