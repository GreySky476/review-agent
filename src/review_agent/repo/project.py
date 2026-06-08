"""Project Repository。"""

from __future__ import annotations

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import Platform
from review_agent.types.orm import ProjectModel


class ProjectRepo(BaseRepository[ProjectModel]):  # type: ignore[misc]
    """项目仓库 CRUD。"""

    @property
    def _model(self) -> type[ProjectModel]:
        return ProjectModel  # type: ignore[no-any-return]

    async def get_by_platform_repo(self, platform: Platform, repo_url: str) -> ProjectModel | None:
        """按平台和仓库 URL 查询项目。"""
        stmt = select(ProjectModel).where(
            ProjectModel.platform == platform,
            ProjectModel.repo_url == repo_url,
            ProjectModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_webhook_secret(self, secret: str) -> ProjectModel | None:
        """按 Webhook Secret 查询项目。"""
        stmt = select(ProjectModel).where(
            ProjectModel.webhook_secret == secret,
            ProjectModel.is_deleted.is_(False),
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()
