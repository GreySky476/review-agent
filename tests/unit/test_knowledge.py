"""Tests for knowledge base service."""

import json

import pytest

from review_agent.service.chunking import CodeChunk
from review_agent.service.knowledge.service import KnowledgeBaseService
from review_agent.types.enums import ChunkPath, FindingCategory


@pytest.fixture
def rules() -> list[dict]:
    return [
        {
            "name": "No eval",
            "content": "禁止使用 eval 执行用户输入",
            "category": "security",
            "severity": "critical",
            "languages": json.dumps(["python", "javascript"]),
            "tags": json.dumps(["security", "injection"]),
            "version": 1,
            "is_active": True,
        },
        {
            "name": "Use f-strings",
            "content": "优先使用 f-string 格式化字符串",
            "category": "style",
            "severity": "info",
            "languages": json.dumps(["python"]),
            "tags": json.dumps(["string", "format"]),
            "version": 1,
            "is_active": True,
        },
        {
            "name": "Inactive rule",
            "content": "这是一条禁用规则",
            "category": "security",
            "severity": "warning",
            "languages": "[]",
            "tags": "[]",
            "version": 1,
            "is_active": False,
        },
    ]


def _make_chunk(code: str, path: str = "test.py") -> CodeChunk:
    return CodeChunk(
        file_path=path,
        function_name="test",
        source_code=code,
        start_line=1,
        end_line=len(code.split("\n")),
        estimated_tokens=len(code) // 3,
        path=ChunkPath.DETAILED_REVIEW,
    )


class TestKnowledgeBaseService:
    async def test_load_rules_filters_inactive(self, rules: list[dict]) -> None:
        kb = KnowledgeBaseService()
        await kb.load_rules(rules)
        assert len(kb._rules) == 2  # inactive rule filtered out

    async def test_search_returns_matches(self, rules: list[dict]) -> None:
        kb = KnowledgeBaseService()
        await kb.load_rules(rules)
        chunk = _make_chunk("eval(x)", "app.py")
        results = await kb.search(chunk, top_k=5)
        assert len(results) >= 1

    async def test_search_python_scores_higher(self, rules: list[dict]) -> None:
        kb = KnowledgeBaseService()
        await kb.load_rules(rules)
        chunk = _make_chunk("name = 'hello'", "app.py")
        results = await kb.search(chunk, top_k=5)
        assert any("f-string" in r.get("name", "") for r in results)

    async def test_get_rules_by_category(self, rules: list[dict]) -> None:
        kb = KnowledgeBaseService()
        await kb.load_rules(rules)
        results = await kb.get_rules_by_category(FindingCategory.SECURITY)
        assert len(results) == 1
        assert results[0]["name"] == "No eval"
