"""Tests for review dimension functions."""

from review_agent.service.chunking import CodeChunk
from review_agent.service.dimensions.base import (
    _find_line,
    review_bug_risk,
    review_code_style,
    review_dependency,
    review_performance,
    review_security,
)
from review_agent.service.dimensions.structure import (
    _calculate_complexity,
    _count_params,
    _estimate_nesting_depth,
    review_structure,
)
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity


def _make_chunk(code: str, name: str = "test_func", path: str = "test.py") -> CodeChunk:
    return CodeChunk(
        file_path=path,
        function_name=name,
        source_code=code,
        start_line=1,
        end_line=len(code.split("\n")),
        estimated_tokens=len(code) // 3,
        path=ChunkPath.DETAILED_REVIEW,
    )


class TestFindLine:
    def test_finds_pattern(self) -> None:
        code = "a = 1\nb = 2\neval(x)"
        assert _find_line(code, "eval") == 3

    def test_not_found(self) -> None:
        assert _find_line("a = 1", "eval") is None


class TestReviewSecurity:
    async def test_detects_eval(self) -> None:
        chunk = _make_chunk("result = eval(user_input)")
        findings = await review_security(chunk)
        assert len(findings) == 1
        assert findings[0].category == FindingCategory.SECURITY
        assert findings[0].severity == FindingSeverity.CRITICAL

    async def test_clean_code_no_findings(self) -> None:
        chunk = _make_chunk("result = a + b")
        findings = await review_security(chunk)
        assert len(findings) == 0

    async def test_detects_sql_injection(self) -> None:
        chunk = _make_chunk('cursor.execute("SELECT * FROM users WHERE id = " + uid)')
        findings = await review_security(chunk)
        assert len(findings) >= 1


class TestReviewBugRisk:
    async def test_detects_bare_except(self) -> None:
        chunk = _make_chunk("try:\n    pass\nexcept:\n    pass")
        findings = await review_bug_risk(chunk)
        assert len(findings) >= 1
        assert "裸 except" in findings[0].title

    async def test_clean_code(self) -> None:
        chunk = _make_chunk("def foo(x: int) -> int:\n    return x + 1")
        findings = await review_bug_risk(chunk)
        assert len(findings) == 0


class TestReviewPerformance:
    async def test_no_findings_for_clean(self) -> None:
        chunk = _make_chunk("x = [i for i in range(10)]")
        findings = await review_performance(chunk)
        assert len(findings) == 0


class TestReviewCodeStyle:
    async def test_short_function_ok(self) -> None:
        chunk = _make_chunk("def foo():\n    pass")
        findings = await review_code_style(chunk)
        assert len(findings) == 0

    async def test_long_function_triggers_warning(self) -> None:
        code = "def foo():\n" + "    pass\n" * 101
        chunk = _make_chunk(code)
        findings = await review_code_style(chunk)
        assert len(findings) == 1
        assert findings[0].category == FindingCategory.STYLE


class TestReviewDependency:
    async def test_detects_pickle(self) -> None:
        chunk = _make_chunk("import pickle")
        findings = await review_dependency(chunk)
        assert len(findings) == 1

    async def test_no_pickle(self) -> None:
        chunk = _make_chunk("import json")
        findings = await review_dependency(chunk)
        assert len(findings) == 0


class TestReviewStructure:
    async def test_complexity_calculation(self) -> None:
        code = "def foo():\n    if a:\n        for b in c:\n            if d:\n                pass"
        chunk = _make_chunk(code, name="foo")
        assert _calculate_complexity(code) > 1

    async def test_nesting_depth(self) -> None:
        code = "def foo():\n    if a:\n        if b:\n            pass"
        chunk = _make_chunk(code, name="foo")
        depth = _estimate_nesting_depth(code)
        assert depth >= 2

    async def test_clean_code_no_findings(self) -> None:
        chunk = _make_chunk("def foo():\n    return 42")
        findings = await review_structure(chunk)
        assert len(findings) == 0

    async def test_count_params(self) -> None:
        code = "def foo(a, b, c):\n    pass"
        assert _count_params(code, "foo") == 3

    async def test_counts_self_as_skip(self) -> None:
        code = "def foo(self, a, b):\n    pass"
        assert _count_params(code, "foo") == 2
