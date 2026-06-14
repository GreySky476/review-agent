"""轻量嵌入服务（EmbeddingService）。

用于将文本转换为向量表示，支持按需调用外部 LLM 嵌入 API。
内存缓存嵌入结果，可选持久化到数据库。

适用场景：
- 企业自定义代码审查规则的向量检索
- 无需重型向量数据库，50-300 条规则内存运算即可
"""

from __future__ import annotations

import hashlib
import logging
from typing import Any

from review_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

# 回退伪向量的维度
_FALLBACK_DIM = 128


class EmbeddingService:
    """轻量嵌入服务。

    通过外部 LLM 提供的嵌入 API 将文本转为向量。
    结果缓存在内存 dict 中，支持按 project_id 分桶隔离。

    Attributes:
        _cache: ``{rule_id: vector}`` 内存缓存。
        _settings: 应用全局配置。
    """

    def __init__(self, cache: dict[str, list[float]] | None = None) -> None:
        """初始化嵌入服务。

        Args:
            cache: 预填充的内存缓存（可选），用于从 DB 加载历史向量。
        """
        self._cache: dict[str, list[float]] = cache or {}
        self._settings = get_settings()

    async def embed(self, text: str) -> list[float]:
        """将文本转换为向量。

        调用配置的 LLM 嵌入 API。失败时回退为基于 hash 的伪向量，
        保证服务不中断。

        Args:
            text: 待嵌入的文本。

        Returns:
            浮点数向量列表。
        """
        if not text.strip():
            return _pseudo_embedding("")

        try:
            import httpx

            headers = {
                "Authorization": f"Bearer {self._settings.ai_api_key}",
                "Content-Type": "application/json",
            }
            payload: dict[str, Any] = {
                "model": self._settings.ai_embedding_model,
                "input": text,
            }
            timeout = httpx.Timeout(max(10, self._settings.ai_request_timeout))
            async with httpx.AsyncClient(timeout=timeout) as client:
                resp = await client.post(
                    f"{self._settings.ai_base_url}/v1/embeddings",
                    headers=headers,
                    json=payload,
                )
                resp.raise_for_status()
                data = resp.json()
                return data["data"][0]["embedding"]
        except Exception as exc:
            logger.warning("Embedding API failed, using fallback: %s", exc)
            return _pseudo_embedding(text)

    def cache_get(self, rule_id: str) -> list[float] | None:
        """从缓存中获取向量。

        Args:
            rule_id: 规则 ID。

        Returns:
            向量或 None（缓存未命中）。
        """
        return self._cache.get(rule_id)

    def cache_set(self, rule_id: str, vector: list[float]) -> None:
        """将向量写入缓存。

        Args:
            rule_id: 规则 ID。
            vector: 浮点数向量。
        """
        self._cache[rule_id] = vector

    def cache_invalidate(self, rule_id: str) -> None:
        """清除指定规则的缓存。

        Args:
            rule_id: 规则 ID。
        """
        self._cache.pop(rule_id, None)

    def cache_clear(self) -> None:
        """清空全部缓存。"""
        self._cache.clear()

    def cache_size(self) -> int:
        """当前缓存条目数。"""
        return len(self._cache)

    @staticmethod
    def cosine_similarity(a: list[float], b: list[float]) -> float:
        """计算两个向量的余弦相似度。

        结果范围 [-1, 1]，1 表示方向完全一致。

        Args:
            a: 向量 A。
            b: 向量 B。

        Returns:
            余弦相似度。向量为空或长度不匹配时返回 0。
        """
        if not a or not b or len(a) != len(b):
            return 0.0
        dot = sum(x * y for x, y in zip(a, b, strict=False))
        norm_a = sum(x * x for x in a) ** 0.5
        norm_b = sum(y * y for y in b) ** 0.5
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return dot / (norm_a * norm_b)

    @staticmethod
    def cosine_similarity_batch(
        query: list[float],
        candidates: dict[str, list[float]],
    ) -> list[tuple[str, float]]:
        """批量计算余弦相似度并排序。

        Args:
            query: 查询向量。
            candidates: ``{rule_id: vector}`` 候选集。

        Returns:
            按相似度降序排列的 ``[(rule_id, score), ...]`` 列表。
        """
        scores: list[tuple[str, float]] = []
        for rule_id, vec in candidates.items():
            sim = EmbeddingService.cosine_similarity(query, vec)
            scores.append((rule_id, sim))
        scores.sort(key=lambda x: x[1], reverse=True)
        return scores


def _pseudo_embedding(text: str, dim: int = _FALLBACK_DIM) -> list[float]:
    """基于 hash 的伪向量生成器。

    当嵌入 API 不可用时使用，保证服务不中断。
    相同输入产生相同输出，同一空间中的语义距离无意义。

    Args:
        text: 输入文本。
        dim: 向量维度（默认 128）。

    Returns:
        归一化的浮点数向量。
    """
    h = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [b / 255.0 for b in h[:dim]]
    # 补足或截断到 dim
    while len(vec) < dim:
        vec.extend(vec[: dim - len(vec)])
    vec = vec[:dim]
    norm = sum(x * x for x in vec) ** 0.5
    return [x / norm for x in vec] if norm > 0 else vec
