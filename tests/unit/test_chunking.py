"""Tests for code chunking service."""

from review_agent.service.chunking import _estimate_tokens, _extract_functions, chunk_file
from review_agent.types.enums import ChunkPath


class TestEstimateTokens:
    def test_empty_string(self) -> None:
        assert _estimate_tokens("") == 1

    def test_short_text(self) -> None:
        assert _estimate_tokens("hello") == 1

    def test_longer_text(self) -> None:
        tokens = _estimate_tokens("a" * 300)
        assert tokens == 100  # 300 // 3


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
