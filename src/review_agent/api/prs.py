"""PR 管理 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import FindingModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pull-requests"])


@router.get("/projects/{project_id}/pull-requests")
async def list_pull_requests(
    project_id: str,
    state: str | None = Query(None, pattern="^(open|merged|closed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的 PR 列表（含关联的评审状态）。"""
    pr_repo = PullRequestRepo(db)
    review_repo = ReviewRepo(db)

    prs = await pr_repo.list_by_project(
        project_id,
        state=state,
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total (needs separate query since list_by_project doesn't return count)
    count_filters: dict[str, Any] = {"project_id": project_id}
    if state:
        count_filters["state"] = state
    total = await pr_repo.count(filters=count_filters)

    items = []
    for pr in prs:
        review = await review_repo.get_by_project_pr(project_id, pr.pr_number)
        items.append(
            {
                "pr_number": pr.pr_number,
                "title": pr.title,
                "author": pr.author,
                "state": pr.state,
                "is_merged": pr.is_merged,
                "review_status": review.status if review else None,
                "review_score": review.score if review else None,
                "findings_count": review.findings_count if review else 0,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/projects/{project_id}/pull-requests/{pr_number}")
async def get_pull_request_detail(
    project_id: str,
    pr_number: int,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取 PR 详情（含关联的 Review 和 Findings）。"""
    pr_repo = PullRequestRepo(db)
    review_repo = ReviewRepo(db)

    pr = await pr_repo.get_by_pr_number(project_id, pr_number)
    if pr is None:
        return {
            "pull_request": None,
            "reviews": [],
            "findings": [],
        }

    review = await review_repo.get_by_project_pr(project_id, pr_number)

    # 查询真实 Findings
    findings: list[dict[str, Any]] = []
    if review:
        finding_rows = await db.execute(
            select(FindingModel).where(
                FindingModel.review_id == review.id,
                FindingModel.is_deleted.is_(False),
            )
        )
        for f in finding_rows.scalars().all():
            findings.append(
                {
                    "id": f.id,
                    "file_path": f.file_path,
                    "line_start": f.line_start,
                    "line_end": f.line_end,
                    "category": f.category,
                    "severity": f.severity,
                    "title": f.title,
                    "description": f.description,
                    "suggestion": f.suggestion,
                    "rule_id": f.rule_id,
                    "is_valid": f.is_valid,
                }
            )

    return {
        "pull_request": {
            "pr_number": pr.pr_number,
            "title": pr.title,
            "author": pr.author,
            "source_branch": pr.source_branch,
            "target_branch": pr.target_branch,
            "state": pr.state,
            "is_merged": pr.is_merged,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "platform": pr.platform,
            "create_time": pr.create_time.isoformat() if pr.create_time else None,
        },
        "reviews": [
            {
                "id": review.id,
                "status": review.status,
                "score": review.score,
                "findings_count": review.findings_count,
                "create_time": review.create_time.isoformat() if review.create_time else None,
            }
        ]
        if review
        else [],
        "findings": findings,
    }


@router.post("/projects/{project_id}/pull-requests/{pr_number}/review", status_code=202)
async def trigger_pr_review(
    project_id: str,
    pr_number: int,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """手动触发 PR 评审。

    1. 查找项目
    2. 从 GitHub 获取 PR 最新 head SHA
    3. 获取变更文件列表
    4. 创建评审记录并加入队列
    """
    logger.info("Manual PR review triggered: project=%s pr=#%d", project_id, pr_number)

    # 1. 查找项目
    project_repo = ProjectRepo(db)
    project = await project_repo.get(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        return {"status": "rejected", "reason": "project_not_found"}

    repo_name = _extract_repo_name(project.repo_url)
    if not repo_name:
        logger.warning("Cannot extract repo_name from repo_url: %s", project.repo_url)
        return {"status": "rejected", "reason": "invalid_repo_url"}

    # 2. 从 GitHub 获取 PR 最新 head SHA
    try:
        git = GitHubProvider()
        pr_info = await git.get_pr_info(repo_name, pr_number)
        pr_head_sha = pr_info.head_sha
        logger.info(
            "Fetched PR info: %s#%d head_sha=%s",
            repo_name,
            pr_number,
            pr_head_sha,
        )
    except Exception as exc:
        logger.warning("Failed to fetch PR info for %s#%d: %s", repo_name, pr_number, exc)
        return {"status": "rejected", "reason": f"github_api_failed: {exc}"}

    # 3. 获取变更文件
    changed_files: list[dict[str, Any]] = []
    try:
        pr_files = await git.get_commit_diff(repo_name, pr_head_sha)
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
        logger.info(
            "Fetched %d changed files for PR #%d@%s",
            len(changed_files),
            pr_number,
            pr_head_sha[:8],
        )
    except Exception as exc:
        logger.warning("Failed to fetch PR diff for %s#%d: %s", repo_name, pr_number, exc)

    if not changed_files:
        logger.warning("No changed files for PR #%d@%s", pr_number, repo_name)
        return {"status": "accepted", "task_id": None, "reason": "no_changed_files"}

    # 4. 创建评审记录
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project_id,
        pr_number=pr_number,
        pr_title=f"PR #{pr_number}",
        head_sha=pr_head_sha,
        status=ReviewStatus.PENDING,
        task_id=None,
    )
    logger.info("Review record created: id=%s pr=#%d", review.id, pr_number)

    # 5. 加入评审队列
    task_id = await enqueue_commit_review(
        project_id=project_id,
        repo_name=repo_name,
        sha=pr_head_sha,
        changed_files=changed_files,
        review_id=review.id,
    )

    if task_id:
        review.task_id = task_id
        await db.flush()

    logger.info(
        "PR review enqueued: project=%s pr=#%d sha=%s task=%s review=%s files=%d",
        project_id,
        pr_number,
        pr_head_sha[:8],
        task_id,
        review.id,
        len(changed_files),
    )

    return {
        "status": "accepted",
        "task_id": task_id or "",
        "review_id": review.id,
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
