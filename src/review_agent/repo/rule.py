"""Rule Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import FindingCategory
from review_agent.types.orm import RuleModel


class RuleRepo(BaseRepository[RuleModel]):  # type: ignore[misc]
    """规范规则仓库 CRUD。"""

    @property
    def _model(self) -> type[RuleModel]:
        return RuleModel  # type: ignore[no-any-return]

    async def list_active(self) -> list[RuleModel]:
        """列出所有启用的规则。"""
        stmt = select(RuleModel).where(
            RuleModel.is_active.is_(True),
            RuleModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_category(self, category: FindingCategory) -> list[RuleModel]:
        """按类别列出规则。"""
        stmt = select(RuleModel).where(
            RuleModel.category == category,
            RuleModel.is_active.is_(True),
            RuleModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_project(self, project_id: str) -> list[RuleModel]:
        """返回全局规则和项目专属规则。

        Args:
            project_id: 项目 ID。

        Returns:
            全局规则 (project_id IS NULL) 和项目专属规则的并集。
        """
        stmt = select(RuleModel).where(
            RuleModel.is_active.is_(True),
            RuleModel.is_deleted.is_(False),
            (RuleModel.project_id == project_id) | (RuleModel.project_id.is_(None)),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_by_language(self, language: str) -> list[RuleModel]:
        """按语言预过滤规则。

        Args:
            language: 语言标识（如 ``python``、``javascript``）。

        Returns:
            匹配语言的活跃规则列表。
        """
        stmt = select(RuleModel).where(
            RuleModel.is_active.is_(True),
            RuleModel.is_deleted.is_(False),
            RuleModel.languages.contains(language),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def bulk_update_embeddings(
        self,
        embeddings: dict[str, str],
        model_name: str,
    ) -> None:
        """批量写入规则 embedding 向量。

        Args:
            embeddings: ``{rule_id: json_encoded_vector}`` 映射。
            model_name: 生成 embedding 的模型名。
        """
        for rule_id, vector_json in embeddings.items():
            rule = await self._db.get(RuleModel, rule_id)
            if rule:
                rule.embedding = vector_json
                rule.embedding_model = model_name
