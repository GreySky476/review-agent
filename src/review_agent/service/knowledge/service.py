"""规范知识库服务。

用于管理和检索企业自定义的代码审查规范。
M1 阶段实现基于关键词的简单检索，M2 阶段升级为向量检索。
"""

from __future__ import annotations

import json
import logging
from typing import Any

from review_agent.service.chunking import CodeChunk
from review_agent.types.enums import FindingCategory

logger = logging.getLogger(__name__)


class KnowledgeBaseService:
    """规范知识库服务。

    管理审查规范的检索和版本控制。
    """

    def __init__(self) -> None:
        self._rules: list[dict[str, Any]] = []

    async def load_rules(self, rules_data: list[dict[str, Any]]) -> None:
        """加载规范规则。

        Args:
            rules_data: 规则数据列表，每项包含 name, content, category,
                       severity, languages, tags, version, is_active。
        """
        self._rules = [r for r in rules_data if r.get("is_active", True)]

    async def search(self, chunk: CodeChunk, top_k: int = 5) -> list[dict[str, Any]]:
        """检索与代码块最相关的规范规则。

        M1 阶段：基于文件扩展名和关键词匹配。
        M2 阶段：升级为向量相似度检索。

        Args:
            chunk: 待评审的代码块。
            top_k: 返回的最大规则数。

        Returns:
            匹配的规则列表。
        """
        matches: list[tuple[dict[str, Any], int]] = []

        file_ext = chunk.file_path.rsplit(".", 1)[-1] if "." in chunk.file_path else ""
        ext_lang_map = {
            "py": "python",
            "js": "javascript",
            "ts": "typescript",
            "java": "java",
            "go": "go",
            "rs": "rust",
            "rb": "ruby",
            "php": "php",
            "swift": "swift",
            "kt": "kotlin",
        }
        lang = ext_lang_map.get(file_ext, "")

        for rule in self._rules:
            score = 0
            rule_languages = rule.get("languages", [])

            # 语言匹配
            if isinstance(rule_languages, str):
                try:
                    rule_languages = json.loads(rule_languages)
                except (json.JSONDecodeError, TypeError):
                    rule_languages = []

            if lang and lang in rule_languages:
                score += 3

            # 文件路径关键词匹配
            rule_keywords = rule.get("tags", [])
            if isinstance(rule_keywords, str):
                try:
                    rule_keywords = json.loads(rule_keywords)
                except (json.JSONDecodeError, TypeError):
                    rule_keywords = []

            for keyword in rule_keywords:
                if keyword.lower() in chunk.file_path.lower():
                    score += 2
                if keyword.lower() in chunk.source_code.lower():
                    score += 1

            if score > 0:
                matches.append((rule, score))

        # 按匹配度排序
        matches.sort(key=lambda x: x[1], reverse=True)
        return [rule for rule, _score in matches[:top_k]]

    async def get_rules_by_category(self, category: FindingCategory) -> list[dict[str, Any]]:
        """按类别获取规则。"""
        return [r for r in self._rules if r.get("category") == category.value]
