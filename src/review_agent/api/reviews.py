"""评审相关 REST API 端点。"""

from __future__ import annotations

import uuid
from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.review import ReviewRepo
from review_agent.types.enums import ReviewStatus
from review_agent.types.models import ReviewCreate

router = APIRouter(tags=["reviews"])


@router.post("/projects/{project_id}/reviews", status_code=202)
async def trigger_review(
    project_id: str,
    _body: ReviewCreate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """手动触发评审。"""
    _ = project_id
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project_id,
        pr_number=_body.pr_number,
        pr_title=_body.pr_title,
        head_sha=_body.head_sha,
        status=ReviewStatus.PENDING,
    )
    task_id = str(uuid.uuid4())
    return {
        "task_id": task_id,
        "status": review.status.value,
        "result_url": None,
    }


@router.get("/projects/{project_id}/reviews/{task_id}")
async def get_review_status(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """查询评审任务状态。"""
    _ = (project_id, task_id)
    repo = ReviewRepo(db)
    review = await repo.get(task_id)
    if review is None:
        return {
            "task_id": task_id,
            "status": ReviewStatus.PENDING.value,
            "score": None,
            "findings_count": 0,
            "result_url": None,
            "findings": [],
        }
    return {
        "task_id": task_id,
        "status": review.status.value,
        "score": review.score,
        "findings_count": review.findings_count,
        "result_url": review.report_url,
        "findings": [],
    }


@router.get("/projects/{project_id}/reviews")
async def list_reviews(
    project_id: str,
    status: str | None = Query(None, pattern="^(pending|running|completed|failed)$"),
    score_min: int | None = Query(None, ge=0, le=100),
    score_max: int | None = Query(None, ge=0, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的评审记录列表。"""
    _ = (project_id, status, score_min, score_max, date_from, date_to)
    repo = ReviewRepo(db)
    filters: dict[str, Any] = {"project_id": project_id}
    if status:
        filters["status"] = status
    items = await repo.list(
        skip=(page - 1) * page_size,
        limit=page_size,
        filters=filters,
    )
    total = await repo.count(filters=filters)
    return {
        "items": [
            {
                "id": r.id,
                "pr_number": r.pr_number,
                "pr_title": r.pr_title,
                "status": r.status.value,
                "score": r.score,
                "findings_count": r.findings_count,
                "create_time": (
                    r.create_time.isoformat() if r.create_time else None
                ),
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
        "finding_summary": {},
    }
