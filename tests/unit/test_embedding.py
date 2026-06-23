"""Tests for embedding service."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

from review_agent.service.embedding import EmbeddingService, _pseudo_embedding


class TestPseudoEmbedding:
    """伪向量生成器测试。"""

    def test_returns_fixed_dimension(self) -> None:
        vec = _pseudo_embedding("hello")
        assert len(vec) == 128

    def test_deterministic_output(self) -> None:
        a = _pseudo_embedding("same text")
        b = _pseudo_embedding("same text")
        assert a == b

    def test_different_input_different_vector(self) -> None:
        a = _pseudo_embedding("hello")
        b = _pseudo_embedding("world")
        assert a != b

    def test_empty_string_returns_normalized(self) -> None:
        vec = _pseudo_embedding("")
        norm = sum(x * x for x in vec) ** 0.5
        assert abs(norm - 1.0) < 0.01  # normalized

    def test_custom_dimension(self) -> None:
        vec = _pseudo_embedding("test", dim=64)
        assert len(vec) == 64


class TestCosineSimilarity:
    """余弦相似度计算测试。"""

    def test_identical_vectors(self) -> None:
        vec = [1.0, 0.0, 0.0]
        sim = EmbeddingService.cosine_similarity(vec, vec)
        assert abs(sim - 1.0) < 1e-6

    def test_opposite_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [-1.0, 0.0]
        sim = EmbeddingService.cosine_similarity(a, b)
        assert abs(sim - (-1.0)) < 1e-6

    def test_orthogonal_vectors(self) -> None:
        a = [1.0, 0.0]
        b = [0.0, 1.0]
        sim = EmbeddingService.cosine_similarity(a, b)
        assert abs(sim) < 1e-6

    def test_zero_vector(self) -> None:
        a = [0.0, 0.0]
        b = [1.0, 0.0]
        sim = EmbeddingService.cosine_similarity(a, b)
        assert sim == 0.0

    def test_empty_vectors(self) -> None:
        sim = EmbeddingService.cosine_similarity([], [1.0])
        assert sim == 0.0

    def test_mismatched_length(self) -> None:
        sim = EmbeddingService.cosine_similarity([1.0], [1.0, 2.0])
        assert sim == 0.0


class TestEmbeddingCache:
    """嵌入缓存测试。"""

    def test_cache_roundtrip(self) -> None:
        svc = EmbeddingService()
        vec = [0.1, 0.2, 0.3]
        svc.cache_set("rule-1", vec)
        assert svc.cache_get("rule-1") == vec

    def test_cache_miss(self) -> None:
        svc = EmbeddingService()
        assert svc.cache_get("nonexistent") is None

    def test_cache_invalidate(self) -> None:
        svc = EmbeddingService()
        svc.cache_set("rule-1", [1.0, 2.0])
        svc.cache_invalidate("rule-1")
        assert svc.cache_get("rule-1") is None

    def test_cache_clear(self) -> None:
        svc = EmbeddingService()
        svc.cache_set("a", [1.0])
        svc.cache_set("b", [2.0])
        svc.cache_clear()
        assert svc.cache_size() == 0

    def test_cache_size(self) -> None:
        svc = EmbeddingService()
        assert svc.cache_size() == 0
        svc.cache_set("a", [1.0])
        assert svc.cache_size() == 1

    def test_prepopulated_cache(self) -> None:
        cache = {"pre-1": [1.0, 2.0]}
        svc = EmbeddingService(cache=cache)
        assert svc.cache_get("pre-1") == [1.0, 2.0]
        assert svc.cache_size() == 1


class TestEmbedService:
    """嵌入 API 调用测试。"""

    async def test_embed_fallback_on_api_failure(self) -> None:
        """API 失败时自动回退伪向量。"""
        svc = EmbeddingService()
        # 不 mock httpx，让 API 调用因无密钥而失败
        # 回退逻辑应在 embed() 的 except 中触发
        vec = await svc.embed("test text")
        assert len(vec) == 128  # 回退向量维度

    async def test_embed_empty_text(self) -> None:
        svc = EmbeddingService()
        vec = await svc.embed("")
        assert len(vec) == 128

    async def test_embed_with_mock(self) -> None:
        """mock httpx 模拟成功嵌入。"""
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "data": [{"embedding": [0.1, 0.2, 0.3]}],
        }
        mock_response.raise_for_status = MagicMock()

        mock_client = AsyncMock()
        mock_client.__aenter__.return_value = mock_client
        mock_client.post = AsyncMock(return_value=mock_response)

        with patch("httpx.AsyncClient", return_value=mock_client):
            svc = EmbeddingService()
            vec = await svc.embed("hello")
            assert vec == [0.1, 0.2, 0.3]

    async def test_cosine_similarity_batch(self) -> None:
        query = [1.0, 0.0]
        candidates = {
            "a": [1.0, 0.0],  # cos=1.0
            "b": [0.0, 1.0],  # cos=0.0
            "c": [-1.0, 0.0],  # cos=-1.0
        }
        results = EmbeddingService.cosine_similarity_batch(query, candidates)
        assert len(results) == 3
        assert results[0][0] == "a"  # 最相似
        assert results[2][0] == "c"  # 最不相似
