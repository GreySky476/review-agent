"""PullRequest Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import PullRequestModel


class PullRequestRepo(BaseRepository[PullRequestModel]):  # type: ignore[misc]
    """PR 仓库 CRUD。"""

    @property
    def _model(self) -> type[PullRequestModel]:
        return PullRequestModel  # type: ignore[no-any-return]

    async def get_by_pr_number(self, project_id: str, pr_number: int) -> PullRequestModel | None:
        """按项目 ID 和 PR 编号查询。"""
        stmt = select(PullRequestModel).where(
            PullRequestModel.project_id == project_id,
            PullRequestModel.pr_number == pr_number,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_project(
        self,
        project_id: str,
        *,
        state: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[PullRequestModel]:
        """按项目列出 PR，可选按状态筛选。"""
        stmt = select(PullRequestModel).where(
            PullRequestModel.project_id == project_id,
        )
        if state:
            stmt = stmt.where(PullRequestModel.state == state)
        stmt = stmt.order_by(PullRequestModel.create_time.desc()).offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def update_reviewed_sha(
        self, project_id: str, pr_number: int, sha: str, review_id: str
    ) -> PullRequestModel | None:
        """更新 PR 的 last_reviewed_sha（增量评审进度标记）。"""
        pr = await self.get_by_pr_number(project_id, pr_number)
        if pr:
            pr.last_reviewed_sha = sha  # type: ignore[assignment]
            pr.last_review_id = review_id  # type: ignore[assignment]
            await self._db.flush()
        return pr

    async def update_pr_comment_id(
        self, project_id: str, pr_number: int, comment_id: int
    ) -> PullRequestModel | None:
        """更新 PR 的 GitHub PR Comment ID（用于追评编辑）。"""
        pr = await self.get_by_pr_number(project_id, pr_number)
        if pr:
            pr.pr_comment_id = comment_id  # type: ignore[assignment]
            await self._db.flush()
        return pr

    async def upsert(
        self, project_id: str, pr_number: int, **kwargs: str | bool | None
    ) -> PullRequestModel:
        """创建或更新 PR 记录。"""
        existing = await self.get_by_pr_number(project_id, pr_number)
        if existing:
            for key, value in kwargs.items():
                if hasattr(existing, key) and value is not None:
                    setattr(existing, key, value)
            await self._db.flush()
            return existing
        return await self.create(
            project_id=project_id,
            pr_number=pr_number,
            **kwargs,
        )
