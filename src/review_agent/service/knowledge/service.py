"""规范知识库服务。

用于管理和检索企业自定义的代码审查规范。
M1 阶段实现基于关键词的简单检索，M2 阶段升级为向量检索。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from review_agent.service.chunking import CodeChunk
from review_agent.service.embedding import EmbeddingService
from review_agent.types.enums import FindingCategory

logger = logging.getLogger(__name__)

# 语言代码 → 文件扩展名映射（用于检索）
_LANGUAGE_EXT_MAP: dict[str, str] = {
    "python": ".py",
    "javascript": ".js",
    "typescript": ".ts",
    "java": ".java",
    "go": ".go",
    "rust": ".rs",
    "ruby": ".rb",
    "php": ".php",
    "kotlin": ".kt",
    "swift": ".swift",
}


class KnowledgeBaseService:
    """规范知识库服务。

    管理审查规范的检索和版本控制。
    M2 版本支持三段式混合检索：语言精确匹配 → 标签匹配 → 语义向量排序。

    Attributes:
        _rules: 活跃规则列表（已加载）。
        _embedding: 嵌入服务（可选），提供向量相似度检索。
    """

    def __init__(self, embedding_service: EmbeddingService | None = None) -> None:
        """初始化知识库服务。

        Args:
            embedding_service: 嵌入服务（可选）。为 None 时回退 M1 关键词匹配。
        """
        self._rules: list[dict[str, Any]] = []
        self._embedding = embedding_service

    async def load_rules(self, rules_data: list[dict[str, Any]]) -> None:
        """加载规范规则。

        将嵌入向量写入服务缓存以供检索。

        Args:
            rules_data: 规则数据列表，每项包含 name, content, category,
                       severity, languages, tags, version, is_active。
        """
        self._rules = [r for r in rules_data if r.get("is_active", True)]
        # 预热嵌入缓存
        if self._embedding is not None:
            for rule in self._rules:
                rule_id = rule.get("id", "")
                if not rule_id:
                    continue
                vector_json = rule.get("embedding")
                if vector_json:
                    try:
                        vec = json.loads(vector_json)
                        self._embedding.cache_set(rule_id, vec)
                    except (json.JSONDecodeError, TypeError):
                        pass

    async def search(self, chunk: CodeChunk, top_k: int = 5) -> list[dict[str, Any]]:
        """检索与代码块最相关的规范规则。

        三段式混合检索：
        1. 语言精确匹配 → 基础分 +3
        2. 标签关键词匹配 → 命中加分 +2
        3. 语义向量相似度 → 相似度 ×5（需要 EmbeddingService）

        Args:
            chunk: 待评审的代码块。
            top_k: 返回的最大规则数。

        Returns:
            匹配的规则列表（按综合得分降序）。
        """
        lang = self._detect_language(chunk.file_path)
        matches: list[tuple[dict[str, Any], float]] = []

        # 尝试获取 chunk 向量
        chunk_vec: list[float] | None = None
        if self._embedding is not None:
            try:
                chunk_vec = await self._embedding.embed(chunk.prompt_text)
            except Exception:
                logger.warning("Chunk embedding failed, skipping vector search")

        for rule in self._rules:
            score = 0.0

            # Stage 1: 语言匹配
            rule_languages = rule.get("languages", [])
            if isinstance(rule_languages, str):
                try:
                    rule_languages = json.loads(rule_languages)
                except (json.JSONDecodeError, TypeError):
                    rule_languages = []
            if lang and lang in rule_languages:
                score += 3.0

            # Stage 2: 标签匹配
            rule_tags = rule.get("tags", [])
            if isinstance(rule_tags, str):
                try:
                    rule_tags = json.loads(rule_tags)
                except (json.JSONDecodeError, TypeError):
                    rule_tags = []
            for tag in rule_tags:
                if tag.lower() in chunk.file_path.lower():
                    score += 2.0
                if tag.lower() in chunk.source_code.lower():
                    score += 1.0

            # Stage 3: 向量相似度
            if chunk_vec is not None and self._embedding is not None:
                rule_id = rule.get("id", "")
                rule_vec = self._embedding.cache_get(rule_id) if rule_id else None
                if rule_vec is not None:
                    sim = EmbeddingService.cosine_similarity(chunk_vec, rule_vec)
                    score += 5.0 * sim

            if score > 0:
                matches.append((rule, score))

        matches.sort(key=lambda x: x[1], reverse=True)
        return [rule for rule, _score in matches[:top_k]]

    async def get_rules_by_category(self, category: FindingCategory) -> list[dict[str, Any]]:
        """按类别获取规则。

        Args:
            category: Finding 类别。

        Returns:
            匹配类别的规则列表。
        """
        return [r for r in self._rules if r.get("category") == category.value]

    @staticmethod
    def _detect_language(file_path: str) -> str:
        """从文件路径推断编程语言。

        Args:
            file_path: 文件路径。

        Returns:
            语言标识（如 ``python``），未知返回空字符串。
        """
        for lang, ext in _LANGUAGE_EXT_MAP.items():
            if file_path.endswith(ext):
                return lang
        return ""
