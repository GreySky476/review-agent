"""QualitySnapshot Repository。"""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import QualitySnapshot


class QualitySnapshotRepo(BaseRepository[QualitySnapshot]):  # type: ignore[misc]
    """质量快照仓库 CRUD。"""

    @property
    def _model(self) -> type[QualitySnapshot]:
        return QualitySnapshot  # type: ignore[no-any-return]

    async def list_by_project_and_period(
        self,
        project_id: str | None = None,
        *,
        period: str = "monthly",
        start_date: date | None = None,
        end_date: date | None = None,
        skip: int = 0,
        limit: int = 365,
    ) -> list[QualitySnapshot]:
        """按项目和时间粒度查询质量快照。"""
        stmt = select(QualitySnapshot).where(QualitySnapshot.period == period)
        if project_id:
            stmt = stmt.where(QualitySnapshot.project_id == project_id)
        if start_date:
            stmt = stmt.where(QualitySnapshot.snapshot_date >= start_date)
        if end_date:
            stmt = stmt.where(QualitySnapshot.snapshot_date <= end_date)
        stmt = stmt.order_by(QualitySnapshot.snapshot_date.asc()).offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
