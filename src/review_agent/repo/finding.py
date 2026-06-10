"""Finding Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import FindingCategory, FindingSeverity
from review_agent.types.orm import FindingModel


class FindingRepo(BaseRepository[FindingModel]):  # type: ignore[misc]
    """Finding 仓库 CRUD。"""

    @property
    def _model(self) -> type[FindingModel]:
        return FindingModel  # type: ignore[no-any-return]

    async def list_by_review(self, review_id: str) -> list[FindingModel]:
        """按评审 ID 列出所有 Finding。"""
        stmt = (
            select(FindingModel)
            .where(
                FindingModel.review_id == review_id,
                FindingModel.is_deleted.is_(False),
            )
            .order_by(FindingModel.create_time)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_category(self, review_id: str) -> dict[FindingCategory, int]:
        """统计评审中各类别 Finding 数量。"""
        findings = await self.list_by_review(review_id)
        counts: dict[FindingCategory, int] = {}
        for f in findings:
            counts[f.category] = counts.get(f.category, 0) + 1
        return counts

    async def count_by_severity(self, review_id: str) -> dict[FindingSeverity, int]:
        """统计评审中各严重性级别 Finding 数量。"""
        findings = await self.list_by_review(review_id)
        counts: dict[FindingSeverity, int] = {}
        for f in findings:
            counts[f.severity] = counts.get(f.severity, 0) + 1
        return counts
