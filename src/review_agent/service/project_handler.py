"""项目管理服务处理 — 封装 ProjectRepo/PullRequestRepo/ReviewRepo/WebhookEventRepo 操作。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.project import ProjectRepo, normalize_repo_url
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.types.orm import ProjectModel, ReviewModel


async def create_project(
    db: AsyncSession,
    *,
    name: str,
    platform: str,
    repo_url: str,
    webhook_enabled: bool = False,
) -> ProjectModel:
    """创建新项目。"""
    return await ProjectRepo(db).create(
        name=name,
        platform=platform,
        repo_url=normalize_repo_url(repo_url),
        webhook_enabled=webhook_enabled,
    )


async def get_project(db: AsyncSession, project_id: str) -> ProjectModel | None:
    """按 ID 获取项目。"""
    return await ProjectRepo(db).get(project_id)


async def get_active_project(db: AsyncSession, project_id: str) -> ProjectModel | None:
    """获取未删除的项目。"""
    return await ProjectRepo(db).get_active(project_id)


async def update_project(db: AsyncSession, project_id: str, **kwargs: Any) -> None:
    """更新项目字段。"""
    await ProjectRepo(db).update(project_id, **kwargs)


async def update_project_settings(
    db: AsyncSession,
    project_id: str,
    **kwargs: Any,
) -> dict[str, Any]:
    """更新项目 settings JSON 字段。"""
    return await ProjectRepo(db).update_settings(project_id, **kwargs)  # type: ignore[no-any-return]


async def delete_project(db: AsyncSession, project_id: str) -> None:
    """软删除项目。"""
    await ProjectRepo(db).soft_delete(project_id)


async def get_project_by_platform_repo(
    db: AsyncSession,
    platform: Any,
    repo_url: str,
) -> ProjectModel | None:
    """按平台和仓库 URL 查询项目。"""
    return await ProjectRepo(db).get_by_platform_repo(platform, repo_url)


async def count_projects(db: AsyncSession) -> int:
    """统计项目总数。"""
    return await ProjectRepo(db).count()  # type: ignore[no-any-return]


async def list_projects(
    db: AsyncSession,
    *,
    skip: int = 0,
    limit: int = 100,
) -> list[ProjectModel]:
    """分页列出项目。"""
    return await ProjectRepo(db).list(skip=skip, limit=limit)  # type: ignore[no-any-return]


async def get_review_branches(db: AsyncSession, project_id: str) -> list[str]:
    """获取项目的评审分支列表。"""
    return await ProjectRepo(db).get_review_branches(project_id)  # type: ignore[no-any-return]


async def count_prs(
    db: AsyncSession,
    project_id: str,
) -> int:
    """统计项目的 PR 数量。"""
    return await PullRequestRepo(db).count(filters={"project_id": project_id})  # type: ignore[no-any-return]


async def count_reviews(
    db: AsyncSession,
    project_id: str,
) -> int:
    """统计项目的评审数量。"""
    return await ReviewRepo(db).count(filters={"project_id": project_id})  # type: ignore[no-any-return]


async def get_latest_review(
    db: AsyncSession,
    project_id: str,
) -> ReviewModel | None:
    """获取项目最近的评审。"""
    return await ReviewRepo(db).get_latest(project_id)


async def get_last_webhook_event_time(
    db: AsyncSession,
    project_id: str,
) -> datetime | None:
    """获取项目最后一次 webhook 事件的时间。"""
    return await WebhookEventRepo(db).last_event_time(project_id)  # type: ignore[no-any-return]
