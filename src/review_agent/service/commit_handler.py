"""Commit 管理服务处理 — 封装 CommitRepo/ProjectRepo/ReviewRepo 操作。"""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.commit import CommitRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.review import ReviewRepo
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import CommitModel, ProjectModel, ReviewModel


async def list_commits(
    db: AsyncSession,
    project_id: str,
    *,
    branch: str | None = None,
    author: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[CommitModel]:
    """分页列出项目的 commits。"""
    return await CommitRepo(db).list_by_project(  # type: ignore[no-any-return]
        project_id,
        branch=branch,
        author=author,
        skip=skip,
        limit=limit,
    )


async def count_commits(
    db: AsyncSession,
    project_id: str,
    *,
    branch: str | None = None,
    author: str | None = None,
) -> int:
    """统计项目 commit 数量。"""
    filters: dict[str, Any] = {"project_id": project_id}
    if branch:
        filters["branch"] = branch
    if author:
        filters["author"] = author
    return await CommitRepo(db).count(filters=filters)  # type: ignore[no-any-return]


async def get_commit_by_sha(
    db: AsyncSession,
    project_id: str,
    sha: str,
) -> CommitModel | None:
    """按 SHA 查询 commit。"""
    return await CommitRepo(db).get_by_sha(project_id, sha)


async def get_project(db: AsyncSession, project_id: str) -> ProjectModel | None:
    """按 ID 获取项目。"""
    return await ProjectRepo(db).get(project_id)


async def create_review(
    db: AsyncSession,
    *,
    project_id: str,
    pr_number: int | None = None,
    pr_title: str | None = None,
    head_sha: str | None = None,
    status: ReviewStatus = ReviewStatus.PENDING,
    task_id: str | None = None,
) -> ReviewModel:
    """创建评审记录。"""
    return await ReviewRepo(db).create(
        project_id=project_id,
        pr_number=pr_number,
        pr_title=pr_title,
        head_sha=head_sha,
        status=status,
        task_id=task_id,
    )


async def get_review_by_head_sha(
    db: AsyncSession,
    project_id: str,
    head_sha: str,
) -> ReviewModel | None:
    """按项目 + head SHA 查评审。"""
    return await ReviewRepo(db).get_by_head_sha(project_id, head_sha)


async def soft_delete_review(db: AsyncSession, review_id: str) -> None:
    """软删除评审。"""
    await ReviewRepo(db).soft_delete(review_id)
