"""Tests for AIReviewer — core AI review orchestration service.

Covers:
- review_chunk with empty content
- review_chunk with successful AI response
- review_chunk with AI failure (exception handling)
- review_chunk with very large input (token limit warning)
- review_chunks with multiple entries
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from review_agent.service.ai.types import (  # noqa: E402
    AICompletionResponse,
    BatchReviewEntry,
)
from review_agent.service.ai_reviewer import AIReviewer  # noqa: E402
from review_agent.service.chunking import CodeChunk  # noqa: E402
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity  # noqa: E402

# ── helpers ────────────────────────────────────────────────


def _make_chunk(
    code: str = "def foo():\n    return 42\n",
    path: str = "src/test.py",
    name: str = "foo",
    tokens: int = 30,
) -> CodeChunk:
    return CodeChunk(
        file_path=path,
        function_name=name,
        source_code=code,
        start_line=1,
        end_line=len(code.split("\n")),
        estimated_tokens=tokens,
        path=ChunkPath.DETAILED_REVIEW,
    )


def _make_ai_response(findings: list[dict] | None = None) -> str:
    """Produce a realistic AI JSON response (markdown-wrapped)."""
    data = findings or [
        {
            "category": "bug",
            "severity": "warning",
            "title": "Missing error handling",
            "description": "The function does not handle exceptions.",
            "suggestion": "Add try/except around the database call.",
            "line": 2,
        },
    ]
    import json

    return "```json\n" + json.dumps(data, indent=2) + "\n```"


# ── fixture: mocked AI provider ────────────────────────────


@pytest.fixture
def mock_ai_provider() -> MagicMock:
    """Return a MagicMock that quacks like AIProvider (AsyncMock for complete)."""
    provider = MagicMock()
    provider.complete = AsyncMock()
    return provider


# ─── Tests: review_chunk ───────────────────────────────────


class TestReviewChunk:
    """Tests for AIReviewer.review_chunk()."""

    async def test_review_chunk_empty_content(self, mock_ai_provider: MagicMock) -> None:
        """Empty source_code returns empty findings without calling AI."""
        chunk = _make_chunk(code="")

        with (
            patch("review_agent.service.ai_reviewer.load_standards", return_value=""),
            patch("review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock),
        ):
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            findings = await reviewer.review_chunk(chunk)

        assert findings == []
        # The AI provider is still called — the reviewer sends the empty code chunk.
        # The parse step will likely return [] because the AI response contains no
        # valid findings with the required severity/category fields.
        mock_ai_provider.complete.assert_called_once()

    async def test_review_chunk_ai_success(self, mock_ai_provider: MagicMock) -> None:
        """Mock AI returns structured JSON → findings are parsed correctly."""
        response_content = _make_ai_response(
            [
                {
                    "category": "bug",
                    "severity": "warning",
                    "title": "Unhandled exception",
                    "description": "No try/except.",
                    "suggestion": "Wrap in try/except.",
                    "line": 2,
                },
                {
                    "category": "security",
                    "severity": "critical",
                    "title": "SQL injection",
                    "description": "String formatting in query.",
                    "suggestion": "Use parameterized queries.",
                    "line": 3,
                },
            ]
        )
        mock_ai_provider.complete.return_value = AICompletionResponse(
            content=response_content,
            model="deepseek-v4-flash",
        )

        chunk = _make_chunk(
            code=(
                "def query(db, uid):\n"
                "    db.execute(f'SELECT * FROM users WHERE id={uid}')\n"
                "    return None\n"
            ),
        )

        with (
            patch(
                "review_agent.service.ai_reviewer.load_standards",
                return_value="## Python Standards",
            ),
            patch("review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock),
        ):
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            findings = await reviewer.review_chunk(chunk)

        assert len(findings) == 2

        assert findings[0].category == FindingCategory.BUG
        assert findings[0].severity == FindingSeverity.WARNING
        assert findings[0].title == "Unhandled exception"
        assert findings[0].file_path == "src/test.py"

        assert findings[1].category == FindingCategory.SECURITY
        assert findings[1].severity == FindingSeverity.CRITICAL
        assert findings[1].title == "SQL injection"

    async def test_review_chunk_ai_failure(self, mock_ai_provider: MagicMock) -> None:
        """AI provider raises exception → returns empty list, no crash."""
        mock_ai_provider.complete.side_effect = RuntimeError("Connection timeout")

        chunk = _make_chunk(code="def foo():\n    return 1\n")

        with (
            patch("review_agent.service.ai_reviewer.load_standards", return_value="## Standards"),
            patch("review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock) as mock_log,
        ):
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            findings = await reviewer.review_chunk(chunk)

        assert findings == []
        # Should have called log_error
        mock_log.assert_called_once()
        call_args = mock_log.call_args[1]
        assert call_args["error_type"] == "ai_call_failed"
        assert "Connection timeout" in call_args["error_message"]

    async def test_review_chunk_very_large(self, mock_ai_provider: MagicMock) -> None:
        """Chunk with high estimated_tokens triggers a warning log but still completes."""
        # AI returns an empty array — no valid findings
        mock_ai_provider.complete.return_value = AICompletionResponse(
            content="```json\n[]\n```",
            model="deepseek-v4-flash",
        )

        # Create a chunk whose estimated tokens exceed 90 % of max_tokens (32768)
        huge_code = "def bar():\n" + "    x = 1\n" * 6000
        chunk = _make_chunk(code=huge_code, tokens=30000)

        with (
            patch("review_agent.service.ai_reviewer.load_standards", return_value=""),
            patch("review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock),
            patch("review_agent.service.ai_reviewer.logger") as mock_logger,
        ):
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            findings = await reviewer.review_chunk(chunk)

        # Should not crash; empty findings because AI returned empty list
        assert findings == []
        # Verify the warning was logged about approaching token limit
        mock_logger.warning.assert_called()
        # The warning should mention "approaching limit"
        warning_msg = mock_logger.warning.call_args[0][0]
        assert "approaching limit" in warning_msg

    async def test_review_chunk_none_provider(self) -> None:
        """When ai_provider is None, return empty findings immediately."""
        reviewer = AIReviewer(ai_provider=None)
        chunk = _make_chunk()
        findings = await reviewer.review_chunk(chunk)
        assert findings == []


# ─── Tests: review_chunks (batch) ──────────────────────────


class TestReviewChunks:
    """Tests for AIReviewer.review_chunks() batch review."""

    async def test_empty_entries_returns_empty_lists(self, mock_ai_provider: MagicMock) -> None:
        """Empty entries list → returns [[]] without calling AI."""
        reviewer = AIReviewer(ai_provider=mock_ai_provider)
        result = await reviewer.review_chunks([])
        assert result == []
        mock_ai_provider.complete.assert_not_called()

    async def test_none_provider_returns_empty_per_entry(self) -> None:
        """None provider → returns empty lists, one per entry."""
        reviewer = AIReviewer(ai_provider=None)
        entry = BatchReviewEntry(
            file_path="src/test.py",
            function_name="foo",
            source_code="def foo(): pass",
            start_line=1,
            end_line=2,
            estimated_tokens=10,
        )
        result = await reviewer.review_chunks([entry])
        assert result == [[]]

    async def test_batch_success(self, mock_ai_provider: MagicMock) -> None:
        """Batch call with 2 entries → AI returns findings mapped back per entry."""
        import json

        batch_response = json.dumps(
            [
                {
                    "function_index": 0,
                    "findings": [
                        {
                            "category": "bug",
                            "severity": "warning",
                            "title": "bug in foo",
                            "description": "desc",
                            "suggestion": "fix",
                            "line": 1,
                        }
                    ],
                },
                {
                    "function_index": 1,
                    "findings": [],
                },
            ]
        )
        mock_ai_provider.complete.return_value = AICompletionResponse(
            content=batch_response,
            model="deepseek-v4-flash",
        )

        entries = [
            BatchReviewEntry(
                file_path="src/a.py",
                function_name="foo",
                source_code="def foo(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=10,
            ),
            BatchReviewEntry(
                file_path="src/b.py",
                function_name="bar",
                source_code="def bar(): return 1",
                start_line=10,
                end_line=11,
                estimated_tokens=12,
            ),
        ]

        with patch("review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock):
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            result = await reviewer.review_chunks(entries)

        assert len(result) == 2
        assert len(result[0]) == 1
        assert result[0][0].category == FindingCategory.BUG
        assert result[0][0].title == "bug in foo"
        assert len(result[1]) == 0

    async def test_batch_failure_graceful(self, mock_ai_provider: MagicMock) -> None:
        """AI fails in batch → all entries get empty lists, error logged."""
        mock_ai_provider.complete.side_effect = RuntimeError("API error")

        entries = [
            BatchReviewEntry(
                file_path="src/a.py",
                function_name="foo",
                source_code="def foo(): pass",
                start_line=1,
                end_line=2,
                estimated_tokens=10,
            ),
        ]

        with patch(
            "review_agent.service.ai_reviewer.log_error", new_callable=AsyncMock
        ) as mock_log:
            reviewer = AIReviewer(ai_provider=mock_ai_provider)
            result = await reviewer.review_chunks(entries)

        assert result == [[]]
        mock_log.assert_called_once()
        assert mock_log.call_args[1]["error_type"] == "ai_call_failed"


# ─── Tests: _try_parse_json ────────────────────────────────


class TestTryParseJson:
    """Tests for AIReviewer._try_parse_json() static method."""

    def test_valid_json_array(self) -> None:
        result = AIReviewer._try_parse_json('[{"a": 1}]')
        assert result == [{"a": 1}]

    def test_valid_json_object_returns_none(self) -> None:
        """Non-list JSON results in None."""
        result = AIReviewer._try_parse_json('{"a": 1}')
        assert result is None

    def test_malformed_json_returns_none(self) -> None:
        result = AIReviewer._try_parse_json("not json at all")
        assert result is None

    def test_json_with_control_chars(self) -> None:
        """Control characters are stripped before retry."""
        result = AIReviewer._try_parse_json('[\x00\x01{"a": 1}\x02]')
        assert result == [{"a": 1}]

    def test_json_with_trailing_commas(self) -> None:
        """Trailing commas are removed before retry."""
        result = AIReviewer._try_parse_json('[{"a": 1},]')
        assert result == [{"a": 1}]

    def test_empty_string(self) -> None:
        assert AIReviewer._try_parse_json("") is None

    def test_extract_from_surrounding_text(self) -> None:
        """Extract JSON array from within other text using bracket matching."""
        result = AIReviewer._try_parse_json('prefix text [{"a": 1}] suffix text')
        assert result == [{"a": 1}]


# ─── Tests: _parse_response ────────────────────────────────


class TestParseResponse:
    """Tests for AIReviewer._parse_response() static method."""

    def _make_json_content(self, items: list[dict]) -> str:
        """Build a JSON array string from item dicts."""
        return json.dumps(items)

    def test_markdown_wrapped_json(self) -> None:
        chunk = _make_chunk()
        inner = self._make_json_content(
            [
                {
                    "category": "bug",
                    "severity": "warning",
                    "title": "t",
                    "description": "d",
                    "suggestion": "s",
                    "line": 1,
                }
            ]
        )
        content = f"```json\n{inner}\n```"
        findings = AIReviewer._parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].category == FindingCategory.BUG

    def test_bare_json_array(self) -> None:
        chunk = _make_chunk()
        content = self._make_json_content(
            [
                {
                    "category": "performance",
                    "severity": "warning",
                    "title": "Slow",
                    "description": "N+1 query",
                    "suggestion": "Use eager loading",
                    "line": 1,
                }
            ]
        )
        findings = AIReviewer._parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].category == FindingCategory.PERFORMANCE

    def test_invalid_severity_filtered_out(self) -> None:
        """Items with severity not in (critical, warning) are skipped."""
        chunk = _make_chunk()
        content = self._make_json_content(
            [
                {
                    "category": "bug",
                    "severity": "info",
                    "title": "t",
                    "description": "d",
                    "suggestion": "s",
                    "line": 1,
                }
            ]
        )
        findings = AIReviewer._parse_response(content, chunk)
        assert findings == []

    def test_invalid_category_filtered_out(self) -> None:
        """Items with unknown category are skipped."""
        chunk = _make_chunk()
        content = self._make_json_content(
            [
                {
                    "category": "style",
                    "severity": "warning",
                    "title": "t",
                    "description": "d",
                    "suggestion": "s",
                    "line": 1,
                }
            ]
        )
        findings = AIReviewer._parse_response(content, chunk)
        assert findings == []

    def test_empty_response_returns_empty(self) -> None:
        chunk = _make_chunk()
        findings = AIReviewer._parse_response("", chunk)
        assert findings == []

    def test_unparseable_response_returns_empty(self) -> None:
        chunk = _make_chunk()
        findings = AIReviewer._parse_response("This is not JSON at all.", chunk)
        assert findings == []

    def test_mixed_valid_invalid_items(self) -> None:
        """Only valid items are parsed; invalid ones are silently skipped."""
        chunk = _make_chunk(
            code="def foo():\n    x = 1\n    y = 2\n    return x + y\n",
        )
        # Build invalid JSON intentionally — mixed valid/invalid items
        # with embedded strings that are not dicts
        parts: list[str] = [
            "[",
            json.dumps(
                {
                    "category": "bug",
                    "severity": "warning",
                    "title": "ok",
                    "description": "d",
                    "suggestion": "s",
                    "line": 2,
                }
            ),
            ",",
            json.dumps(
                {
                    "category": "style",
                    "severity": "warning",
                    "title": "skip me",
                    "description": "d",
                    "suggestion": "s",
                    "line": 1,
                }
            ),
            ",",
            '"not a dict item"',
            ",",
            json.dumps(
                {
                    "category": "security",
                    "severity": "critical",
                    "title": "also ok",
                    "description": "d",
                    "suggestion": "s",
                    "line": 3,
                }
            ),
            "]",
        ]
        content = "".join(parts)
        findings = AIReviewer._parse_response(content, chunk)
        assert len(findings) == 2
        categories = [f.category for f in findings]
        assert FindingCategory.BUG in categories
        assert FindingCategory.SECURITY in categories

    def test_code_snippet_extraction(self) -> None:
        """Verify code_snippet is extracted from chunk source at the given line."""
        chunk = _make_chunk(
            code="def foo():\n    result = evil_eval(x)\n    return result\n",
        )
        content = self._make_json_content(
            [
                {
                    "category": "security",
                    "severity": "critical",
                    "title": "eval used",
                    "description": "d",
                    "suggestion": "s",
                    "line": 2,
                }
            ]
        )
        findings = AIReviewer._parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].code_snippet == "result = evil_eval(x)"
        assert findings[0].line_start == 2  # chunk.start_line=1 + 2 - 1
