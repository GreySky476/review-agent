"""Tests for ai_resp_parser — AI response parsing utilities.

Covers:
- parse_response with valid / empty / malformed / partial JSON
- try_parse_json with various edge cases
- parse_batch_response with multiple entries
- adjust_batch_line helper
"""

from __future__ import annotations

import json

from review_agent.service.ai.types import BatchReviewEntry
from review_agent.service.ai_resp_parser import (
    adjust_batch_line,
    parse_batch_response,
    parse_response,
    try_parse_json,
)
from review_agent.service.chunking import CodeChunk
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity

# ── helpers ────────────────────────────────────────────────


def _make_chunk(
    code: str = "def foo():\n    return 42\n",
    path: str = "src/test.py",
    name: str = "foo",
    start_line: int = 1,
) -> CodeChunk:
    return CodeChunk(
        file_path=path,
        function_name=name,
        source_code=code,
        start_line=start_line,
        end_line=start_line + len(code.split("\n")) - 1,
        estimated_tokens=len(code) // 2,
        path=ChunkPath.DETAILED_REVIEW,
    )


def _make_batch_entry(
    path: str = "src/a.py",
    name: str = "foo",
    code: str = "def foo(): pass",
    start_line: int = 1,
) -> BatchReviewEntry:
    return BatchReviewEntry(
        file_path=path,
        function_name=name,
        source_code=code,
        start_line=start_line,
        end_line=start_line + len(code.split("\n")) - 1,
        estimated_tokens=len(code) // 2,
    )


# ─── Tests: parse_response ─────────────────────────────────


class TestParseResponse:
    """Tests for parse_response() function."""

    def test_parse_valid_json_response(self) -> None:
        """Valid JSON with findings should parse correctly."""
        chunk = _make_chunk(code="def foo():\n    x = 1\n    return x\n")
        content = (
            "["
            '{"severity": "critical", "title": "Eval used", '
            '"description": "eval is dangerous", "suggestion": "Use ast.literal_eval", '
            '"line": 2},'
            '{"severity": "warning", "title": "No docstring", '
            '"description": "Missing docstring", "suggestion": "Add docstring", '
            '"line": 1}'
            "]"
        )
        findings = parse_response(content, chunk)

        assert len(findings) == 2
        # parser defaults category to BUG
        assert findings[0].category == FindingCategory.BUG
        assert findings[0].severity == FindingSeverity.CRITICAL
        assert findings[0].title == "Eval used"
        assert findings[0].file_path == "src/test.py"
        assert findings[0].line_start == 2  # start_line=1 + line=2 - 1

        assert findings[1].severity == FindingSeverity.WARNING
        assert findings[1].title == "No docstring"

    def test_parse_empty_response(self) -> None:
        """Empty response string returns empty findings list."""
        chunk = _make_chunk()
        findings = parse_response("", chunk)
        assert findings == []

    def test_parse_malformed_response(self) -> None:
        """Malformed JSON does not crash; returns empty findings."""
        chunk = _make_chunk()
        findings = parse_response("definitely not json {{{", chunk)
        assert findings == []

    def test_parse_partial_response(self) -> None:
        """Partial JSON — some items missing fields — parses what's available."""
        chunk = _make_chunk(code="def bar():\n    pass\n")
        content = (
            "["
            '{"severity": "warning", "title": "OK item", "line": 1},'
            '{"severity": "critical"},'
            '"not a dict",'
            "{}"
            "]"
        )
        findings = parse_response(content, chunk)

        # All 3 dict items are accepted because parser doesn't filter by required fields
        assert len(findings) == 3
        # First item has all fields
        assert findings[0].title == "OK item"
        assert findings[0].severity == FindingSeverity.WARNING
        # Second item: severity="critical", title defaults, description defaults
        assert findings[1].severity == FindingSeverity.CRITICAL
        assert findings[1].title == "未命名问题"
        assert findings[1].description == ""
        # Third empty dict: severity defaults to "info", title defaults
        assert findings[2].severity == FindingSeverity.INFO
        assert findings[2].title == "未命名问题"

    def test_parse_response_missing_required_fields(self) -> None:
        """Response items without severity/title get defaults (INFO / 未命名问题)."""
        chunk = _make_chunk()
        content = '[{"description": "just a note"}]'
        findings = parse_response(content, chunk)

        assert len(findings) == 1
        # severity defaults to INFO when missing
        assert findings[0].severity == FindingSeverity.INFO
        # title defaults to "未命名问题"
        assert findings[0].title == "未命名问题"
        assert findings[0].description == "just a note"
        assert findings[0].suggestion == ""
        assert findings[0].category == FindingCategory.BUG  # parser always BUG

    def test_parse_response_unknown_severity_defaults_to_info(self) -> None:
        """Unknown severity string maps to INFO (no filter by valid values)."""
        chunk = _make_chunk()
        content = '[{"severity": "cosmic", "title": "Weird", "line": 1}]'
        findings = parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].severity == FindingSeverity.INFO

    def test_parse_response_markdown_wrapped(self) -> None:
        """JSON inside ```json ... ``` markdown code block is extracted."""
        chunk = _make_chunk()
        content = '```json\n[{"severity": "warning", "title": "Found", "line": 1}]\n```'
        findings = parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].title == "Found"

    def test_parse_response_extracts_from_text(self) -> None:
        """When JSON is embedded in prose, first [ ... ] range is extracted."""
        chunk = _make_chunk()
        content = 'Here is the result: [{"severity": "critical", "title": "XSS", "line": 1}] end.'
        findings = parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].title == "XSS"

    def test_parse_response_line_adjustment(self) -> None:
        """AI line numbers are adjusted to file-absolute via chunk.start_line."""
        chunk = _make_chunk(code="def foo():\n    a = 1\n    b = 2\n", start_line=50)
        content = '[{"severity": "warning", "title": "t", "line": 2}]'
        findings = parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].line_start == 51  # 50 + 2 - 1

    def test_parse_response_ai_line_none(self) -> None:
        """When line is absent, line_start remains None."""
        chunk = _make_chunk()
        content = '[{"severity": "warning", "title": "No line"}]'
        findings = parse_response(content, chunk)
        assert len(findings) == 1
        assert findings[0].line_start is None


# ─── Tests: try_parse_json ─────────────────────────────────


class TestTryParseJson:
    """Tests for try_parse_json() utility function."""

    def test_valid_array(self) -> None:
        assert try_parse_json('[{"a": 1}]') == [{"a": 1}]

    def test_object_not_list(self) -> None:
        assert try_parse_json('{"a": 1}') is None

    def test_malformed(self) -> None:
        assert try_parse_json("not json") is None

    def test_empty_string(self) -> None:
        assert try_parse_json("") is None

    def test_control_characters_stripped(self) -> None:
        result = try_parse_json('[\x00\x01{"a": 1}\x02]')
        assert result == [{"a": 1}]

    def test_trailing_comma_fixed(self) -> None:
        result = try_parse_json('[{"a": 1},]')
        assert result == [{"a": 1}]

    def test_bracket_extraction(self) -> None:
        """Extract JSON array from surrounding text via bracket matching."""
        result = try_parse_json('prefix [{"x": 1}] suffix')
        assert result == [{"x": 1}]

    def test_nested_brackets(self) -> None:
        """Nested brackets are handled correctly — outermost [] is extracted."""
        result = try_parse_json('[{"items": [1, 2, 3]}]')
        assert result == [{"items": [1, 2, 3]}]

    def test_multiple_arrays_extracts_first(self) -> None:
        """Multiple top-level arrays — extracts the first complete one."""
        result = try_parse_json('[{"a": 1}] extra [{"b": 2}]')
        assert result == [{"a": 1}]


# ─── Tests: parse_batch_response ───────────────────────────


class TestParseBatchResponse:
    """Tests for parse_batch_response() function."""

    def test_single_entry_with_findings(self) -> None:
        entries = [_make_batch_entry(path="src/a.py", code="def foo(): pass")]
        content = (
            "["
            '{"function_index": 0, "findings": ['
            '  {"category": "bug", "severity": "warning", "title": "T", '
            '   "description": "D", "suggestion": "S", "line": 1}'
            "]}"
            "]"
        )
        result = parse_batch_response(content, entries)

        assert len(result) == 1
        assert len(result[0]) == 1
        assert result[0][0].category == FindingCategory.BUG
        assert result[0][0].severity == FindingSeverity.WARNING
        assert result[0][0].title == "T"

    def test_multiple_entries_mixed(self) -> None:
        """Entry 0 has 2 findings, entry 1 has none, entry 2 has 1."""
        entries = [
            _make_batch_entry(path="src/a.py", name="a"),
            _make_batch_entry(path="src/b.py", name="b"),
            _make_batch_entry(path="src/c.py", name="c"),
        ]
        content = json.dumps(
            [
                {
                    "function_index": 0,
                    "findings": [
                        {
                            "category": "bug",
                            "severity": "warning",
                            "title": "B1",
                            "description": "d",
                            "suggestion": "s",
                            "line": 1,
                        },
                        {
                            "category": "security",
                            "severity": "critical",
                            "title": "S1",
                            "description": "d",
                            "suggestion": "s",
                            "line": 1,
                        },
                    ],
                },
                {"function_index": 1, "findings": []},
                {
                    "function_index": 2,
                    "findings": [
                        {
                            "category": "performance",
                            "severity": "warning",
                            "title": "P1",
                            "description": "d",
                            "suggestion": "s",
                            "line": 1,
                        }
                    ],
                },
            ]
        )
        result = parse_batch_response(content, entries)

        assert len(result) == 3
        assert len(result[0]) == 2
        assert len(result[1]) == 0
        assert len(result[2]) == 1

        assert result[0][0].category == FindingCategory.BUG
        assert result[0][1].category == FindingCategory.SECURITY
        assert result[2][0].category == FindingCategory.PERFORMANCE

    def test_malformed_batch_response(self) -> None:
        """Unparseable batch response → each entry gets empty list."""
        entries = [_make_batch_entry()]
        result = parse_batch_response("not json {{{", entries)
        assert result == [[]]

    def test_invalid_function_index(self) -> None:
        """Out-of-range function_index is ignored."""
        entries = [_make_batch_entry()]
        content = '[{"function_index": 5, "findings": [{"severity": "warning", "title": "T"}]}]'
        result = parse_batch_response(content, entries)
        # The entry is only index 0, index 5 is out of range → ignored
        assert len(result[0]) == 0

    def test_non_dict_items_skipped(self) -> None:
        """Non-dict items in the array are skipped."""
        entries = [_make_batch_entry()]
        content = json.dumps(
            [
                {
                    "function_index": 0,
                    "findings": [
                        {
                            "category": "bug",
                            "severity": "warning",
                            "title": "T",
                            "description": "d",
                            "suggestion": "s",
                            "line": 1,
                        }
                    ],
                },
                "garbage",
                42,
            ]
        )
        result = parse_batch_response(content, entries)
        assert len(result[0]) == 1

    def test_code_snippet_in_batch(self) -> None:
        """Batch findings include code_snippet from the source."""
        entry = _make_batch_entry(
            code="def foo():\n    eval(user_input)\n    return\n",
            start_line=100,
        )
        entries = [entry]
        content = (
            '[{"function_index": 0, "findings": ['
            '{"category": "security", "severity": "critical", "title": "eval", '
            '"description": "d", "suggestion": "s", "line": 2}'
            "]}]"
        )
        result = parse_batch_response(content, entries)
        assert len(result[0]) == 1
        assert result[0][0].line_start == 101  # 100 + 2 - 1
        assert result[0][0].code_snippet == "eval(user_input)"


# ─── Tests: adjust_batch_line ──────────────────────────────


class TestAdjustBatchLine:
    """Tests for adjust_batch_line() helper."""

    def test_none_line_returns_none(self) -> None:
        entry = _make_batch_entry(start_line=10)
        assert adjust_batch_line(entry, None) is None

    def test_start_line_1_ai_line_1(self) -> None:
        entry = _make_batch_entry(start_line=1)
        assert adjust_batch_line(entry, 1) == 1

    def test_start_line_100_ai_line_5(self) -> None:
        entry = _make_batch_entry(start_line=100)
        assert adjust_batch_line(entry, 5) == 104  # 100 + 5 - 1
