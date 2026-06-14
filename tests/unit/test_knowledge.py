"""Tests for knowledge base service."""

from __future__ import annotations

import json

import pytest

from review_agent.service.chunking import CodeChunk
from review_agent.service.embedding import EmbeddingService
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

    async def test_search_with_embedding_and_fallback(self, rules: list[dict]) -> None:
        """使用嵌入服务的搜索在 API 失败时回退到关键词匹配。"""
        embedder = EmbeddingService()
        kb = KnowledgeBaseService(embedding_service=embedder)
        await kb.load_rules(rules)
        chunk = _make_chunk("eval(something)", "app.py")
        results = await kb.search(chunk, top_k=5)
        # embedding API 会失败（无密钥），但应回退到 M1 并返回结果
        assert len(results) >= 1

    async def test_search_with_preloaded_embedding(self, rules: list[dict]) -> None:
        """预热缓存后按语义相似度匹配。"""
        embedder = EmbeddingService(
            cache={"": [0.1, 0.2, 0.3]},
        )
        # 给规则预填向量
        rules_with_embeds = [
            {**rules[0], "embedding": json.dumps([0.1, 0.2, 0.3]), "id": "rule-1"},
            {**rules[1], "embedding": json.dumps([0.9, 0.8, 0.7]), "id": "rule-2"},
        ]
        # 预填缓存
        embedder.cache_set("rule-1", [0.1, 0.2, 0.3])
        embedder.cache_set("rule-2", [0.9, 0.8, 0.7])

        kb = KnowledgeBaseService(embedding_service=embedder)
        await kb.load_rules(rules_with_embeds)
        chunk = _make_chunk("test", "app.py")
        results = await kb.search(chunk, top_k=5)
        assert len(results) > 0

    async def test_search_no_embedding_service(self, rules: list[dict]) -> None:
        """无嵌入服务时应回退到 M1 关键词匹配。"""
        kb = KnowledgeBaseService(embedding_service=None)
        await kb.load_rules(rules)
        chunk = _make_chunk("eval(x)", "app.py")
        results = await kb.search(chunk, top_k=5)
        assert len(results) >= 1

    async def test_detect_language(self) -> None:
        assert KnowledgeBaseService._detect_language("test.py") == "python"
        assert KnowledgeBaseService._detect_language("app.ts") == "typescript"
        assert KnowledgeBaseService._detect_language("main.go") == "go"
        assert KnowledgeBaseService._detect_language("unknown.xyz") == ""
