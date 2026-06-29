"""PR 管理服务处理 — 封装 PullRequestRepo/ReviewRepo/CommitRepo/ProjectRepo 操作。"""

from __future__ import annotations

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.commit import CommitRepo
from review_agent.repo.finding import FindingRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import ProjectModel, PullRequestModel, ReviewModel

logger = logging.getLogger(__name__)


async def list_prs(
    db: AsyncSession,
    project_id: str,
    *,
    state: str | None = None,
    skip: int = 0,
    limit: int = 20,
) -> list[PullRequestModel]:
    """按项目分页列出 PR。"""
    repo = PullRequestRepo(db)
    return await repo.list_by_project(project_id, state=state, skip=skip, limit=limit)  # type: ignore[no-any-return]


async def count_prs(
    db: AsyncSession,
    project_id: str,
    *,
    state: str | None = None,
) -> int:
    """统计项目 PR 数量。"""
    repo = PullRequestRepo(db)
    filters: dict[str, Any] = {"project_id": project_id}
    if state:
        filters["state"] = state
    return await repo.count(filters=filters)  # type: ignore[no-any-return]


async def get_pr_by_number(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> PullRequestModel | None:
    """按 PR 编号查询。"""
    return await PullRequestRepo(db).get_by_pr_number(project_id, pr_number)


async def get_review_by_project_pr(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> ReviewModel | None:
    """按项目和 PR 编号查询最新评审。"""
    return await ReviewRepo(db).get_by_project_pr(project_id, pr_number)


async def list_reviews_by_pr(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> list[ReviewModel]:
    """按 PR 列出评审记录（按时间升序）。"""
    return await ReviewRepo(db).list_by_pr(project_id, pr_number)  # type: ignore[no-any-return]


async def count_pr_reviews(db: AsyncSession, project_id: str) -> int:
    """统计项目评审数量。"""
    return await ReviewRepo(db).count(filters={"project_id": project_id})  # type: ignore[no-any-return]


async def get_latest_pr_review(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> ReviewModel | None:
    """获取 PR 最近一次已完成的评审。"""
    return await ReviewRepo(db).get_latest_completed_by_pr(project_id, pr_number)


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


async def list_commits_by_pr(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> list[Any]:
    """按 PR 列出 commits。"""
    return await CommitRepo(db).list_by_pr(project_id, pr_number)  # type: ignore[no-any-return]


async def bulk_upsert_commits(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
    commits: list[dict[str, Any]],
) -> None:
    """批量 upsert commits。"""
    await CommitRepo(db).bulk_upsert(project_id, pr_number, commits)


async def list_findings_by_review(
    db: AsyncSession,
    review_id: str,
) -> list[Any]:
    """按评审 ID 列出 findings。"""
    return await FindingRepo(db).list_by_review(review_id)  # type: ignore[no-any-return]


async def get_project(db: AsyncSession, project_id: str) -> ProjectModel | None:
    """按 ID 获取项目。"""
    return await ProjectRepo(db).get(project_id)


def _extract_repo_name(repo_url: str) -> str | None:
    """从 repo_url 中提取 owner/repo 格式的仓库名。"""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:]).removesuffix(".git")
    return None


async def sync_pr_commits(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
) -> tuple[str, list[dict[str, Any]]]:
    """同步 PR 的 commit 数据（从 GitHub API 获取并写入 DB）。"""
    project = await get_project(db, project_id)
    if not project:
        return ("rejected", [])
    repo_name = _extract_repo_name(project.repo_url)
    if not repo_name or project.platform != "github":
        return ("rejected", [])

    git = GitHubProvider()
    pr_commits = await git.get_pr_commits(repo_name, pr_number)
    if not pr_commits:
        return ("completed", [])

    await bulk_upsert_commits(db, project_id, pr_number, pr_commits)
    await db.commit()
    commits_data = await _build_commits_with_reviews(db, project_id, pr_number, pr_commits)
    return ("completed", commits_data)


async def fetch_pr_commits_fallback(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
    repo_name: str,
) -> list[dict[str, Any]]:
    """从 GitHub API 获取 PR commits（DB 无数据时的回退路径）。"""
    git = GitHubProvider()
    pr_commits = await git.get_pr_commits(repo_name, pr_number)
    commits_data: list[dict[str, Any]] = []

    fallback_shas = [c["sha"] for c in pr_commits if c.get("sha")]
    review_by_sha: dict[str, Any] = {}
    if fallback_shas:
        extra_fallback = await db.execute(
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.head_sha.in_(fallback_shas),
                ReviewModel.is_deleted.is_(False),
                ReviewModel.pr_number.is_(None),
            )
            .order_by(ReviewModel.create_time.asc())
        )
        for rv_extra in list(extra_fallback.scalars(ReviewModel).all()):
            if rv_extra.head_sha:
                review_by_sha[rv_extra.head_sha] = {
                    "review_id": rv_extra.id,
                    "status": rv_extra.status,
                    "score": rv_extra.score,
                    "reviewed_files": rv_extra.reviewed_files,
                }

    for c in pr_commits:
        sha = c["sha"]
        rv_info = review_by_sha.get(sha, {})
        commits_data.append(
            {
                "sha": sha,
                "message": c.get("message", ""),
                "author": c.get("author"),
                "date": c.get("date"),
                "review_id": rv_info.get("review_id"),
                "review_status": rv_info.get("status"),
                "review_score": rv_info.get("score"),
                "reviewed_files": rv_info.get("reviewed_files"),
            }
        )
    return commits_data


async def _build_commits_with_reviews(
    db: AsyncSession,
    project_id: str,
    pr_number: int,
    pr_commits: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """构建 commits 数据并合并 review 状态。"""
    all_reviews = await list_reviews_by_pr(db, project_id, pr_number)
    commit_shas = [c["sha"] for c in pr_commits]

    extra_reviews_result = await db.execute(
        select(ReviewModel)
        .where(
            ReviewModel.project_id == project_id,
            ReviewModel.head_sha.in_(commit_shas),
            ReviewModel.is_deleted.is_(False),
            ReviewModel.pr_number.is_(None),
        )
        .order_by(ReviewModel.create_time.asc())
    )
    all_sha_reviews = list(extra_reviews_result.scalars(ReviewModel).all())

    review_by_sha: dict[str, Any] = {}
    for rv in list(all_reviews) + all_sha_reviews:
        if rv.head_sha:
            review_by_sha[rv.head_sha] = {
                "review_id": rv.id,
                "status": rv.status,
                "score": rv.score,
                "reviewed_files": rv.reviewed_files,
            }

    commits_data: list[dict[str, Any]] = []
    for c in pr_commits:
        sha = c["sha"]
        rv_info = review_by_sha.get(sha, {})
        commits_data.append(
            {
                "sha": sha,
                "message": c.get("message", ""),
                "author": c.get("author"),
                "date": c.get("date"),
                "review_id": rv_info.get("review_id"),
                "review_status": rv_info.get("status"),
                "review_score": rv_info.get("score"),
                "reviewed_files": rv_info.get("reviewed_files"),
            }
        )
    return commits_data
