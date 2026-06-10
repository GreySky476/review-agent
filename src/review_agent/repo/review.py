"""Review Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import ReviewModel


class ReviewRepo(BaseRepository[ReviewModel]):  # type: ignore[misc]
    """评审记录仓库 CRUD。"""

    @property
    def _model(self) -> type[ReviewModel]:
        return ReviewModel  # type: ignore[no-any-return]

    async def get_by_project_pr(self, project_id: str, pr_number: int) -> ReviewModel | None:
        """按项目 ID 和 PR 号查询最新评审。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.pr_number == pr_number,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_head_sha(self, head_sha: str) -> ReviewModel | None:
        """按 head_sha 查询已缓存的评审结果。"""
        stmt = select(ReviewModel).where(
            ReviewModel.head_sha == head_sha,
            ReviewModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest(self, project_id: str) -> ReviewModel | None:
        """查询项目的最新评审记录。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
