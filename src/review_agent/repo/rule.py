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
