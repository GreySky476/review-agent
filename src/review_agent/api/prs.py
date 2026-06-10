"""PR 管理 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.types.orm import FindingModel

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
