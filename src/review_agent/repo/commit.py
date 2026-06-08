"""Commit Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import CommitModel


class CommitRepo(BaseRepository[CommitModel]):  # type: ignore[misc]
    """提交记录 仓库 CRUD。"""

    @property
    def _model(self) -> type[CommitModel]:
        return CommitModel  # type: ignore[no-any-return]

    async def list_by_project(
        self,
        project_id: str,
        *,
        branch: str | None = None,
        author: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[CommitModel]:
        """按项目列出提交，可选按分支/作者筛选。"""
        stmt = select(CommitModel).where(
            CommitModel.project_id == project_id,
        )
        if branch:
            stmt = stmt.where(CommitModel.branch == branch)
        if author:
            stmt = stmt.where(CommitModel.author == author)
        stmt = stmt.order_by(CommitModel.create_time.desc()).offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sha(self, project_id: str, sha: str) -> CommitModel | None:
        """按 SHA 查询提交。"""
        stmt = select(CommitModel).where(
            CommitModel.project_id == project_id,
            CommitModel.sha == sha,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
