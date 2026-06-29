"""异常监控 API 端点。"""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.config.settings import get_settings
from review_agent.repo.project import ProjectRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.review_error import ReviewErrorRepo
from review_agent.service.error_handler import (
    count_errors_by_type as _count_errors_by_type_query,
)
from review_agent.service.error_handler import (
    list_errors as _list_errors_query,
)
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review, enqueue_pr_review
from review_agent.types.models import ErrorStats
from review_agent.types.orm import ReviewErrorLog

logger = logging.getLogger(__name__)

router = APIRouter(tags=["errors"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


def _parse_date(value: str | None) -> datetime | None:
    """将 ISO 日期字符串转为 datetime，失败时返回 None。"""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None


@router.get("/errors")
async def list_errors(
    project_id: str | None = Query(None),
    error_type: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取异常日志列表。"""
    items = await _list_errors_query(
        db,
        project_id=project_id,
        error_type=error_type,
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total
    count_stmt = select(func.count(ReviewErrorLog.id))
    if project_id:
        count_stmt = count_stmt.where(ReviewErrorLog.project_id == project_id)
    if error_type:
        count_stmt = count_stmt.where(ReviewErrorLog.error_type == error_type)
    result = await db.execute(count_stmt)
    total = result.scalar() or 0

    return {
        "items": [
            {
                "id": e.id,
                "project_id": e.project_id,
                "review_id": e.review_id,
                "error_type": e.error_type,
                "error_message": e.error_message,
                "error_detail": e.error_detail,
                "frequency": e.frequency,
                "recovered": e.recovered,
                "create_time": e.create_time.isoformat() if e.create_time else None,
            }
            for e in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/errors/stats")
async def error_statistics(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
) -> list[ErrorStats]:
    """获取异常聚合统计。"""
    rows = await _count_errors_by_type_query(
        db,
        start_date=_parse_date(start_date),
        end_date=_parse_date(end_date),
    )
    return [
        ErrorStats(
            error_type=row["error_type"],
            count=row["count"],
            last_occurred=row["last_occurred"],
        )
        for row in rows
    ]


@router.get("/errors/trend")
async def error_trend(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """按天统计错误数量趋势（用于折线图）。"""
    start = datetime.now(UTC) - timedelta(days=days)
    stmt = (
        select(
            func.date(ReviewErrorLog.create_time).label("date"),
            func.count(ReviewErrorLog.id).label("count"),
        )
        .where(ReviewErrorLog.create_time >= start)
        .group_by(func.date(ReviewErrorLog.create_time))
        .order_by(func.date(ReviewErrorLog.create_time))
    )
    result = await db.execute(stmt)
    return [{"date": str(row.date), "count": row.count} for row in result.all()]


def _extract_repo_name_from_url(repo_url: str) -> str | None:
    """从 repo_url 提取 owner/repo 格式的仓库名。"""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:]).removesuffix(".git")
    return None


@router.post("/errors/{error_id}/replay", status_code=202)
async def replay_error_job(
    error_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """从错误日志中重新入队失败的 ARQ 评审任务。

    仅支持 error_type="arq_job_failed" 的错误记录。
    通过关联的 project_id 和 review_id 获取上下文，
    从 GitHub 重新拉取文件变更，调用 enqueue 重新入队。

    Args:
        error_id: 错误日志 ID。
        db: 数据库会话。

    Returns:
        202 Accepted 及 job_id。

    Raises:
        404: 错误记录 / Review / Project 不存在。
        400: 错误类型不支持重放，或缺少 project_id / review_id。
        409: 错误记录已被恢复。
    """
    # 1. 查找错误记录
    error_repo = ReviewErrorRepo(db)
    error_log = await error_repo.get(error_id)
    if error_log is None:
        raise HTTPException(status_code=404, detail=f"Error log {error_id} not found")

    # 2. 验证错误类型
    if error_log.error_type != "arq_job_failed":
        raise HTTPException(
            status_code=400,
            detail=f"Only arq_job_failed errors can be replayed, got {error_log.error_type}",
        )
    if error_log.recovered:
        raise HTTPException(status_code=409, detail="Error log already recovered")

    # 3. 验证关联数据
    if not error_log.project_id:
        raise HTTPException(status_code=400, detail="Error log has no associated project_id")
    if not error_log.review_id:
        raise HTTPException(status_code=400, detail="Error log has no associated review_id")

    # 4. 获取 Review 上下文
    review_repo = ReviewRepo(db)
    review = await review_repo.get(error_log.review_id)
    if review is None:
        raise HTTPException(status_code=404, detail=f"Review {error_log.review_id} not found")

    # 5. 获取 Project 上下文
    project_repo = ProjectRepo(db)
    project = await project_repo.get(review.project_id)
    if project is None:
        raise HTTPException(status_code=404, detail=f"Project {review.project_id} not found")

    repo_name = _extract_repo_name_from_url(project.repo_url)
    if not repo_name:
        raise HTTPException(
            status_code=400, detail=f"Cannot extract repo_name from {project.repo_url}"
        )

    # 6. 从 GitHub 重新获取文件变更
    settings = get_settings()
    git_provider = GitHubProvider(token=settings.github_token.get_secret_value())

    job_id: str | None = None
    if review.pr_number is not None:
        # PR review：重新获取 PR diff 文件列表
        pr_files = await git_provider.get_pr_diff(repo_name, review.pr_number)
        all_files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
            }
            for f in pr_files
        ]
        if not all_files:
            raise HTTPException(
                status_code=400,
                detail=f"No files found for PR #{review.pr_number} in {repo_name}",
            )
        job_id = await enqueue_pr_review(
            project_id=review.project_id,
            repo_name=repo_name,
            sha=review.head_sha,
            pr_number=review.pr_number,
            all_files=all_files,
            review_id=review.id,
        )
    else:
        # Commit review：重新获取 commit diff
        commit_files = await git_provider.get_commit_diff(repo_name, review.head_sha)
        changed_files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
            }
            for f in commit_files
        ]
        if not changed_files:
            raise HTTPException(
                status_code=400,
                detail=f"No files found for commit {review.head_sha[:8]} in {repo_name}",
            )
        job_id = await enqueue_commit_review(
            project_id=review.project_id,
            repo_name=repo_name,
            sha=review.head_sha,
            changed_files=changed_files,
            review_id=review.id,
        )

    if job_id is None:
        raise HTTPException(status_code=500, detail="Failed to enqueue job (queue unavailable)")

    # 7. 标记为已恢复
    error_log.recovered = True
    await db.commit()

    logger.info(
        "Replayed error %s: enqueued job %s for review %s",
        error_id,
        job_id,
        review.id,
    )

    return {
        "status": "accepted",
        "error_id": error_id,
        "review_id": review.id,
        "job_id": job_id,
    }
