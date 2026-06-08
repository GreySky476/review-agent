"""Comment Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import CommentModel


class CommentRepo(BaseRepository[CommentModel]):  # type: ignore[misc]
    """评论仓库 CRUD。"""

    @property
    def _model(self) -> type[CommentModel]:
        return CommentModel  # type: ignore[no-any-return]

    async def list_by_review(
        self,
        review_id: str,
        *,
        skip: int = 0,
        limit: int = 50,
    ) -> list[CommentModel]:
        """按评审列出评论。"""
        stmt = (
            select(CommentModel)
            .where(CommentModel.review_id == review_id)
            .order_by(CommentModel.create_time.asc())
            .offset(skip)
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_finding(
        self,
        finding_id: str,
    ) -> list[CommentModel]:
        """按 Finding 列出评论。"""
        stmt = (
            select(CommentModel)
            .where(CommentModel.finding_id == finding_id)
            .order_by(CommentModel.create_time.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())
