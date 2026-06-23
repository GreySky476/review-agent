"""提交管理 API 端点。"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.commit import CommitRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.review import ReviewRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import ReviewModel

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

    # 查询每个 commit 的最新 review（含 score 和 reviewed_files）
    sha_list = [c.sha for c in items if c.sha]
    review_map: dict[str, dict[str, Any]] = {}
    if sha_list:
        review_rows = await db.execute(
            select(
                ReviewModel.id,
                ReviewModel.head_sha,
                ReviewModel.status,
                ReviewModel.score,
                ReviewModel.reviewed_files,
            )
            .where(
                ReviewModel.head_sha.in_(sha_list),
                ReviewModel.project_id == project_id,
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.head_sha, ReviewModel.create_time.desc())
        )
        for r in review_rows.all():
            if r.head_sha not in review_map:
                # 从 reviewed_files 推导严重级别统计
                breakdown: dict[str, int] = {"critical": 0, "warning": 0, "info": 0}
                if r.reviewed_files:
                    for f in r.reviewed_files:
                        sev = f.get("max_severity")
                        if sev in breakdown:
                            breakdown[sev] += 1
                review_map[r.head_sha] = {
                    "review_id": r.id,
                    "review_status": r.status,
                    "review_score": r.score,
                    "severity_breakdown": breakdown if any(breakdown.values()) else None,
                }

    return {
        "items": [
            {
                "id": c.id,
                "sha": c.sha,
                "author": c.author,
                "message": c.message,
                "branch": c.branch,
                "pr_number": c.pr_number,
                "is_reviewed": c.is_reviewed or (c.sha in review_map),
                "review_id": review_map.get(c.sha, {}).get("review_id"),
                "review_status": review_map.get(c.sha, {}).get("review_status"),
                "review_score": review_map.get(c.sha, {}).get("review_score"),
                "severity_breakdown": review_map.get(c.sha, {}).get("severity_breakdown"),
                "create_time": c.create_time.isoformat() if c.create_time else None,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/projects/{project_id}/commits/{sha}/review", status_code=202, response_model=None)
async def trigger_commit_review(
    project_id: str,
    sha: str,
    force: bool = Query(False, description="强制重新评审"),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """触发单次提交评审。

    1. 查找项目并提取仓库名
    2. SHA 去重检查（已有 completed 评审且不强制时跳过）
    3. 加载上一轮 reviewed_files 作为增量上下文
    4. 创建评审记录并加入队列
    """
    logger.info("Commit review triggered: project=%s sha=%s force=%s", project_id, sha, force)

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

    # 2. SHA 去重检查
    try:
        review_repo_instance = ReviewRepo(db)
        existing = await review_repo_instance.get_by_head_sha(sha)
        if existing:
            if existing.status in (ReviewStatus.COMPLETED, ReviewStatus.COMPLETED_WITH_ERRORS):
                if not force:
                    logger.info("SHA %s already completed, skipping", sha[:8])
                    return {"status": "skipped", "reason": "sha_unchanged"}
            elif existing.status in (ReviewStatus.PENDING, ReviewStatus.RUNNING):
                if not force:
                    logger.info("SHA %s review in progress, rejecting", sha[:8])
                    return JSONResponse(
                        {
                            "status": "rejected",
                            "reason": "review_in_progress",
                            "review_id": existing.id,
                        },
                        status_code=409,
                    )
                # force=true: 软删除旧 review 再创建新评审
                logger.info("Force re-review: soft-deleting old review %s", existing.id[:8])
                await review_repo_instance.soft_delete(existing.id)
    except Exception:
        logger.debug("SHA dedup check failed: %s", exc_info=True)

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
        logger.warning("No changed files for commit %s@%s", repo_name, sha)
        return {
            "status": "accepted",
            "task_id": None,
            "commit_found": True,
            "reason": "no_changed_files",
        }

    # 4. 获取 commit message 作为评审标题
    commit_obj = await CommitRepo(db).get_by_sha(project_id, sha)
    commit_message = (
        commit_obj.message[:80] if commit_obj and commit_obj.message else f"Commit {sha[:8]}"
    )

    # 5. 创建评审记录
    review = await ReviewRepo(db).create(
        project_id=project_id,
        pr_number=None,
        pr_title=commit_message,
        head_sha=sha,
        status=ReviewStatus.PENDING,
        task_id=None,
    )
    logger.info("Review record created: id=%s sha=%s", review.id, sha)

    # 6. 入队
    try:
        task_id = await enqueue_commit_review(
            project_id=project_id,
            repo_name=repo_name,
            sha=sha,
            changed_files=changed_files,
            review_id=review.id,
        )
    except Exception:
        logger.warning("Failed to enqueue commit review: %s", traceback.format_exc())
        task_id = None

    if task_id:
        review.task_id = task_id
        await db.flush()

    logger.info(
        "Review enqueued: project=%s sha=%s task=%s review=%s files=%d",
        project_id,
        sha,
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
