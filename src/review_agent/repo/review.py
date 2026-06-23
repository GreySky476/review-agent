"""Review Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import ReviewStatus
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

    async def list_by_pr(
        self, project_id: str, pr_number: int
    ) -> list[ReviewModel]:
        """查询 PR 的所有评审记录（按时间升序）。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.pr_number == pr_number,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_head_sha(self, head_sha: str) -> ReviewModel | None:
        """按 head_sha 查询已缓存的评审结果。"""
        stmt = select(ReviewModel).where(
            ReviewModel.head_sha == head_sha,
            ReviewModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_completed_by_sha(
        self, project_id: str, pr_number: int, head_sha: str
    ) -> ReviewModel | None:
        """查询指定 SHA 已完成（含 completed_with_errors）的评审。"""
        completed_statuses = [ReviewStatus.COMPLETED, ReviewStatus.COMPLETED_WITH_ERRORS]
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.pr_number == pr_number,
                ReviewModel.head_sha == head_sha,
                ReviewModel.status.in_(completed_statuses),
                ReviewModel.is_deleted.is_(False),
            )
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_latest_completed_by_pr(
        self, project_id: str, pr_number: int
    ) -> ReviewModel | None:
        """查询 PR 最新完成的评审（增量时用于对比 previous_review_id）。"""
        completed = [ReviewStatus.COMPLETED, ReviewStatus.COMPLETED_WITH_ERRORS]
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.pr_number == pr_number,
                ReviewModel.status.in_(completed),
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_reviewed_files(
        self, review_id: str, reviewed_files: list[dict[str, str | None]]
    ) -> ReviewModel | None:
        """更新评审的 reviewed_files 记录。"""
        review = await self.get(review_id)
        if review:
            review.reviewed_files = reviewed_files  # type: ignore[assignment]
            await self._db.flush()
        return review

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
