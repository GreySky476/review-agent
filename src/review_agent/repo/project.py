"""Project Repository。"""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import Platform
from review_agent.types.orm import ProjectModel


def normalize_repo_url(url: str) -> str:
    """标准化仓库 URL，去除格式差异。"""
    return url.removesuffix(".git").removesuffix("/").replace("://www.", "://")


def _build_url_variants(repo_url: str) -> set[str]:
    """为仓库 URL 生成所有可能变体（匹配用户可能存储的任何格式）。"""
    base = normalize_repo_url(repo_url)
    variants = {base, f"{base}.git"}
    if base.startswith("https://"):
        http = base.replace("https://", "http://")
        variants.add(http)
        variants.add(f"{http}.git")
        variants.add(f"{http}/")
        www = base.replace("://", "://www.")
        variants.add(www)
        variants.add(f"{www}.git")
    elif base.startswith("http://"):
        https = base.replace("http://", "https://")
        variants.add(https)
        variants.add(f"{https}.git")
    # SSH format (git@github.com:owner/repo)
    if "github.com" in base:
        parts = base.split("/")
        if len(parts) >= 2:
            owner_repo = "/".join(parts[-2:])
            variants.add(f"git@github.com:{owner_repo}.git")
            variants.add(f"git@github.com:{owner_repo}")
    return variants


class ProjectRepo(BaseRepository[ProjectModel]):  # type: ignore[misc]
    """项目仓库 CRUD。"""

    @property
    def _model(self) -> type[ProjectModel]:
        return ProjectModel  # type: ignore[no-any-return]

    async def get_by_platform_repo(self, platform: Platform, repo_url: str) -> ProjectModel | None:
        """按平台和仓库 URL 查询项目（兼容 .git / www / http 等格式差异）。"""
        variants = _build_url_variants(repo_url)
        stmt = select(ProjectModel).where(
            ProjectModel.platform == platform,
            ProjectModel.repo_url.in_(variants),
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

    async def get_settings(self, project_id: str) -> dict[str, Any]:
        """读取项目的 settings JSON 配置。

        Returns:
            解析后的字典，settings 为空或无效时返回空字典。
        """
        project = await self.get(project_id)
        if project is None:
            return {}
        try:
            return json.loads(project.settings) if project.settings else {}
        except (json.JSONDecodeError, TypeError):
            return {}

    async def update_settings(self, project_id: str, **updates: Any) -> dict[str, Any]:
        """合并更新项目的 settings JSON 配置。

        Args:
            project_id: 项目 ID。
            **updates: 要更新的 settings 键值对。

        Returns:
            更新后的完整 settings 字典。

        Raises:
            NotFoundError: 项目不存在时抛出。
        """
        project = await self.get_or_raise(project_id)
        current: dict[str, Any] = {}
        if project.settings:
            try:
                current = json.loads(project.settings)
            except (json.JSONDecodeError, TypeError):
                current = {}
        current.update(updates)
        project.settings = json.dumps(current, ensure_ascii=False)
        await self._db.flush()
        return current

    async def get_review_branches(self, project_id: str) -> list[str]:
        """获取项目的评审分支模式列表。

        从 settings 中读取 review_branches，不存在时返回 ["*"]（全部匹配）。

        Returns:
            分支模式列表，默认 ["*"]。
        """
        settings = await self.get_settings(project_id)
        branches = settings.get("review_branches")
        if isinstance(branches, list) and branches:
            return [str(b) for b in branches]
        return ["*"]
