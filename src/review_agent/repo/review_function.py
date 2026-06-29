"""ReviewFunction Repository."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import ReviewFunctionModel


class ReviewFunctionRepo(BaseRepository[ReviewFunctionModel]):
    """ReviewFunction 仓库 CRUD。"""

    @property
    def _model(self) -> type[ReviewFunctionModel]:
        return ReviewFunctionModel

    async def list_by_review(self, review_id: str) -> list[ReviewFunctionModel]:
        stmt = (
            select(ReviewFunctionModel)
            .where(ReviewFunctionModel.review_id == review_id)
            .order_by(ReviewFunctionModel.file_path, ReviewFunctionModel.start_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_by_review_and_file(
        self, review_id: str, file_path: str
    ) -> list[ReviewFunctionModel]:
        stmt = (
            select(ReviewFunctionModel)
            .where(
                ReviewFunctionModel.review_id == review_id,
                ReviewFunctionModel.file_path == file_path,
            )
            .order_by(ReviewFunctionModel.start_line)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def bulk_create(self, items: list[dict[str, Any]]) -> list[ReviewFunctionModel]:
        return await self.create_many(items)
