"""提交管理 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.commit import CommitRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.review import ReviewRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review
from review_agent.types.enums import ReviewStatus
from review_agent.types.models import CommitReviewRequest

logger = logging.getLogger(__name__)
router = APIRouter(tags=["commits"])


@router.get("/projects/{project_id}/commits")
async def list_commits(
    project_id: str,
    branch: str | None = Query(None),
    author: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的提交列表。"""
    repo = CommitRepo(db)

    items = await repo.list_by_project(
        project_id,
        branch=branch,
        author=author,
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total
    count_filters: dict[str, Any] = {"project_id": project_id}
    if branch:
        count_filters["branch"] = branch
    if author:
        count_filters["author"] = author
    total = await repo.count(filters=count_filters)

    return {
        "items": [
            {
                "id": c.id,
                "sha": c.sha,
                "author": c.author,
                "message": c.message,
                "branch": c.branch,
                "pr_number": c.pr_number,
                "is_reviewed": c.is_reviewed,
                "create_time": c.create_time.isoformat() if c.create_time else None,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/projects/{project_id}/commits/{sha}/review", status_code=202)
async def trigger_commit_review(
    project_id: str,
    sha: str,
    body: CommitReviewRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """通过 @mention 触发提交评审。

    1. 查找项目并提取仓库名
    2. 标记 commit is_reviewed = True
    3. 从 Git 平台获取变更文件
    4. 将评审任务加入队列
    """
    logger.info(
        "Manual review triggered: project=%s sha=%s mention_user=%s",
        project_id,
        sha,
        body.mention_user,
    )

    # 1. 查找项目
    project_repo = ProjectRepo(db)
    project = await project_repo.get(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        return {"status": "rejected", "reason": "project_not_found"}

    # 从 repo_url 提取 owner/repo
    repo_name = _extract_repo_name(project.repo_url)
    if not repo_name:
        logger.warning("Cannot extract repo_name from repo_url: %s", project.repo_url)
        return {"status": "rejected", "reason": "invalid_repo_url"}

    # 2. 查找或创建 commit 记录
    commit_repo = CommitRepo(db)
    commit = await commit_repo.get_by_sha(project_id, sha)
    if commit:
        logger.info("Commit found: %s (is_reviewed=%s)", sha, commit.is_reviewed)
        commit.is_reviewed = True
        await db.flush()
    else:
        logger.info("Commit not in DB, creating placeholder: %s", sha)
        commit = await commit_repo.create(
            project_id=project_id,
            sha=sha,
            author=body.mention_user,
            message="",
            branch=None,
            is_reviewed=True,
        )

    # 3. 获取变更文件
    changed_files: list[dict[str, Any]] = []
    try:
        git = GitHubProvider()
        pr_files = await git.get_commit_diff(repo_name, sha)
        changed_files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
            }
            for f in pr_files
        ]
        logger.info("Fetched %d changed files for %s@%s", len(changed_files), repo_name, sha)
    except Exception as exc:
        logger.warning("Failed to fetch commit diff for %s@%s: %s", repo_name, sha, exc)

    if not changed_files:
        logger.warning("No changed files found for commit %s@%s, skipping queue", repo_name, sha)
        return {
            "status": "accepted",
            "task_id": None,
            "commit_found": True,
            "reason": "no_changed_files",
        }

    # 4. 创建评审记录
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project_id,
        pr_number=None,
        pr_title=f"Commit {sha[:8]}",
        head_sha=sha,
        status=ReviewStatus.PENDING,
        task_id=None,
    )
    logger.info("Review record created: id=%s sha=%s", review.id, sha)

    # 5. 加入评审队列（传递 review_id 以便 worker 更新记录）
    task_id = await enqueue_commit_review(
        project_id=project_id,
        repo_name=repo_name,
        sha=sha,
        changed_files=changed_files,
        review_id=review.id,
    )

    # 更新 task_id
    if task_id:
        review.task_id = task_id
        await db.flush()

    logger.info(
        "Review enqueued: project=%s sha=%s repo=%s task=%s review=%s files=%d",
        project_id,
        sha,
        repo_name,
        task_id,
        review.id,
        len(changed_files),
    )

    return {
        "status": "accepted",
        "task_id": task_id or "",
        "review_id": review.id,
        "commit_found": True,
        "files_count": len(changed_files),
    }


def _extract_repo_name(repo_url: str) -> str | None:
    """从 repo_url 中提取 owner/repo 格式的仓库名。

    >>> _extract_repo_name("https://github.com/owner/repo")
    "owner/repo"
    >>> _extract_repo_name("https://github.com/owner/repo.git")
    "owner/repo"
    """
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        name = "/".join(parts[-2:])
        return name.removesuffix(".git")
    return None
