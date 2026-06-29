"""Tests for code chunking service."""

from review_agent.service.chunking import (
    CodeChunk,
    _estimate_tokens,
    _extract_functions,
    adjust_line_number,
    chunk_file,
)
from review_agent.types.enums import ChunkPath


class TestEstimateTokens:
    def test_short_text(self) -> None:
        assert _estimate_tokens("hello") == 2  # 5//2 = 2

    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 1

    def test_longer_text(self) -> None:
        tokens = _estimate_tokens("a" * 300)
        assert tokens == 150  # 300 // 2 (changed from //3)


class TestExtractFunctions:
    def test_no_functions(self) -> None:
        code = "x = 1\ny = 2\nprint(x + y)"
        result = _extract_functions(code)
        assert len(result) == 0

    def test_single_function(self) -> None:
        code = "def hello():\n    print('hi')"
        result = _extract_functions(code)
        assert len(result) == 1
        assert result[0]["name"] == "hello"

    def test_multiple_functions(self) -> None:
        code = """def foo():
    pass

def bar():
    pass
"""
        result = _extract_functions(code)
        assert len(result) == 2
        assert result[0]["name"] == "foo"
        assert result[1]["name"] == "bar"

    def test_async_function(self) -> None:
        code = "async def fetch_data():\n    return await get()"
        result = _extract_functions(code)
        assert len(result) == 1
        assert result[0]["name"] == "fetch_data"

    def test_function_with_params(self) -> None:
        code = "def add(a: int, b: int) -> int:\n    return a + b"
        result = _extract_functions(code)
        assert len(result) == 1
        assert "a" in result[0]["code"]


class TestChunkFile:
    async def test_chunk_simple_file(self) -> None:
        code = "def foo():\n    pass"
        chunks = await chunk_file("test.py", code)
        assert len(chunks) >= 1
        assert chunks[0].file_path == "test.py"
        assert chunks[0].path == ChunkPath.DETAILED_REVIEW

    async def test_chunk_no_functions(self) -> None:
        code = "x = 1"
        chunks = await chunk_file("test.py", code)
        assert len(chunks) == 1
        assert chunks[0].function_name == "__file__"

    async def test_chunk_oversized_triggers_structural(self) -> None:
        code = "def huge():\n    " + "pass\n    " * 1000
        chunks = await chunk_file("test.py", code)
        # This should be oversized due to high token count
        assert any(c.path == ChunkPath.STRUCTURAL_REVIEW for c in chunks)


class TestAdjustLineNumber:
    """Test adjust_line_number helper."""

    def _make_chunk(self, start_line: int = 1) -> CodeChunk:
        return CodeChunk(
            file_path="test.py",
            function_name="test_func",
            source_code="def test_func():\n    pass\n",
            start_line=start_line,
            end_line=start_line + 2,
            estimated_tokens=10,
            path=ChunkPath.DETAILED_REVIEW,
        )

    def test_none_input_returns_none(self) -> None:
        chunk = self._make_chunk()
        assert adjust_line_number(chunk, None) is None

    def test_start_line_1_ai_line_1(self) -> None:
        """Function starts at line 1, AI says line 1 -> file line 1."""
        chunk = self._make_chunk(start_line=1)
        result = adjust_line_number(chunk, 1)
        assert result == 1

    def test_start_line_50_ai_line_5(self) -> None:
        """Function starts at line 50, AI says line 5 -> file line 54."""
        chunk = self._make_chunk(start_line=50)
        result = adjust_line_number(chunk, 5)
        assert result == 54  # 50 + 5 - 1

    def test_start_line_10_ai_line_1(self) -> None:
        """Function starts at line 10, AI says line 1 -> file line 10."""
        chunk = self._make_chunk(start_line=10)
        result = adjust_line_number(chunk, 1)
        assert result == 10  # 10 + 1 - 1

    def test_start_line_100_ai_line_0(self) -> None:
        """AI might return 0 as line number -> file line 99."""
        chunk = self._make_chunk(start_line=100)
        result = adjust_line_number(chunk, 0)
        assert result == 99  # 100 + 0 - 1
