"""ReviewErrorLog Repository。"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import func, select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import ReviewErrorLog


class ReviewErrorRepo(BaseRepository[ReviewErrorLog]):  # type: ignore[misc]
    """评审错误日志仓库 CRUD。"""

    @property
    def _model(self) -> type[ReviewErrorLog]:
        return ReviewErrorLog  # type: ignore[no-any-return]

    async def list_with_filters(
        self,
        *,
        project_id: str | None = None,
        error_type: str | None = None,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[ReviewErrorLog]:
        """按多种条件筛选错误日志。"""
        stmt = select(ReviewErrorLog)
        if project_id:
            stmt = stmt.where(ReviewErrorLog.project_id == project_id)
        if error_type:
            stmt = stmt.where(ReviewErrorLog.error_type == error_type)
        if start_date:
            stmt = stmt.where(ReviewErrorLog.create_time >= start_date)
        if end_date:
            stmt = stmt.where(ReviewErrorLog.create_time <= end_date)
        stmt = stmt.order_by(ReviewErrorLog.create_time.desc()).offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def count_by_type(
        self,
        *,
        start_date: datetime | None = None,
        end_date: datetime | None = None,
    ) -> list[dict[str, int | str | datetime | None]]:
        """按错误类型聚合统计。"""
        stmt = select(
            ReviewErrorLog.error_type,
            func.count(ReviewErrorLog.id).label("count"),
            func.max(ReviewErrorLog.create_time).label("last_occurred"),
        )
        if start_date:
            stmt = stmt.where(ReviewErrorLog.create_time >= start_date)
        if end_date:
            stmt = stmt.where(ReviewErrorLog.create_time <= end_date)
        stmt = stmt.group_by(ReviewErrorLog.error_type).order_by(
            func.count(ReviewErrorLog.id).desc()
        )
        result = await self._db.execute(stmt)
        rows = result.all()
        return [
            {"error_type": r.error_type, "count": r.count, "last_occurred": r.last_occurred}
            for r in rows
        ]
