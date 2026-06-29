"""Review Repository。"""

from __future__ import annotations

from typing import Any, cast

from sqlalchemy import select, update

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

    async def list_by_pr(self, project_id: str, pr_number: int) -> list[ReviewModel]:
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

    async def get_by_head_sha(self, project_id: str, head_sha: str) -> ReviewModel | None:
        """按项目 + SHA 查询最近一次评审记录。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.head_sha == head_sha,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_sha(
        self, project_id: str, pr_number: int, head_sha: str
    ) -> ReviewModel | None:
        """查询指定 SHA 的最新评审记录（不限状态），用于 SHA 去重。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.pr_number == pr_number,
                ReviewModel.head_sha == head_sha,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
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

    async def get_running_by_sha(self, project_id: str, head_sha: str) -> ReviewModel | None:
        """查询指定 SHA 是否有进行中的评审（PENDING/RUNNING）。"""
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.head_sha == head_sha,
                ReviewModel.status.in_([ReviewStatus.PENDING, ReviewStatus.RUNNING]),
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
            review.reviewed_files = reviewed_files
            await self._db.flush()
        return review

    async def create_or_get(
        self,
        project_id: str,
        pr_number: int | None,
        head_sha: str,
        **kwargs: Any,
    ) -> tuple[ReviewModel, bool]:
        """创建评审记录，有进行中的评审时返回已有记录（并发保护）。

        Returns:
            (ReviewModel, is_new: bool) — is_new 表示是否为新建。
        """
        existing = await self.get_running_by_sha(project_id, head_sha)
        if existing:
            return existing, False
        instance = self._model(
            project_id=project_id,
            pr_number=pr_number,
            head_sha=head_sha,
            **kwargs,
        )
        self._db.add(instance)
        await self._db.flush()
        return instance, True

    async def list_stale(self, timeout_minutes: int = 30) -> list[ReviewModel]:
        """查询超时未完成的评审（PENDING/RUNNING 超过指定分钟数）。

        Args:
            timeout_minutes: 超时阈值（分钟）。

        Returns:
            超时的 ReviewModel 列表。
        """
        from datetime import UTC, datetime, timedelta

        cutoff = datetime.now(UTC) - timedelta(minutes=timeout_minutes)
        stmt = (
            select(ReviewModel)
            .where(
                ReviewModel.status.in_([ReviewStatus.PENDING, ReviewStatus.RUNNING]),
                ReviewModel.create_time < cutoff,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def batch_mark_failed(self, review_ids: list[str], error_message: str = "") -> int:
        """批量将评审标记为 FAILED。

        Args:
            review_ids: 要标记的评审 ID 列表。
            error_message: 附加错误信息。

        Returns:
            实际更新的记录数。
        """
        stmt = (
            update(ReviewModel)
            .where(ReviewModel.id.in_(review_ids))
            .values(
                status=ReviewStatus.FAILED,
                error_message=error_message,
            )
        )
        result = await self._db.execute(stmt)
        await self._db.flush()
        return cast(int, result.rowcount)

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
