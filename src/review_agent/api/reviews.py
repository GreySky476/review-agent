"""评审相关 REST API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func as sa_func
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.dependencies.auth import require_role
from review_agent.api.review_detail import _calc_duration, _fetch_finding_breakdowns
from review_agent.config.database import get_session
from review_agent.service.review_handler import (
    count_reviews as _count_reviews,
)
from review_agent.service.review_handler import (
    create_comment_for_review,
    create_or_get_review,
    get_review_by_id,
    list_comments_by_review,
)
from review_agent.service.review_handler import (
    list_reviews as _list_reviews_query,
)
from review_agent.types.enums import ReviewStatus, UserRole
from review_agent.types.models import ReviewCreate
from review_agent.types.orm import ProjectModel, ReviewAICallModel, ReviewModel

router = APIRouter(tags=["reviews"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


@router.post(
    "/projects/{project_id}/reviews",
    status_code=202,
    dependencies=[Depends(require_role(UserRole.PROJECT_ADMIN))],
)
async def trigger_review(
    project_id: str,
    _body: ReviewCreate,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """手动触发评审。"""
    _ = project_id
    review, is_new = await create_or_get_review(
        db,
        project_id=project_id,
        pr_number=_body.pr_number,
        head_sha=_body.head_sha,
        pr_title=_body.pr_title,
        status=ReviewStatus.PENDING,
    )
    # 已有卡住的 PENDING review → 放行返回已有记录，前端可据此决定是否重试
    return {
        "task_id": review.id,
        "review_id": review.id,
        "status": review.status.value,
        "is_new": is_new,
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
    review = await get_review_by_id(db, task_id)
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
        "status": review.status,
        "score": review.score,
        "findings_count": review.findings_count,
        "result_url": review.report_url,
        "findings": [],
    }


@router.get("/projects/{project_id}/reviews")
async def list_reviews(
    project_id: str,
    status: str | None = Query(
        None, pattern="^(pending|running|completed|completed_with_errors|failed)$"
    ),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的评审记录列表。"""
    filters: dict[str, Any] = {"project_id": project_id}
    if status:
        filters["status"] = status
    items = await _list_reviews_query(
        db, skip=(page - 1) * page_size, limit=page_size, filters=filters
    )
    total = await _count_reviews(db, filters=filters)
    breakdowns = await _fetch_finding_breakdowns(db, [r.id for r in items])
    fail_counts = await _batch_query_ai_fail_counts(db, [r.id for r in items])
    return {
        "items": [
            {
                "id": r.id,
                "pr_number": r.pr_number,
                "pr_title": r.pr_title,
                "status": r.status,
                "score": r.score,
                "head_sha": r.head_sha,
                "findings_count": r.findings_count,
                "severity_breakdown": dict(breakdowns.get(r.id, {}).get("severity", {})),
                "category_breakdown": dict(breakdowns.get(r.id, {}).get("category", {})),
                "duration_seconds": _calc_duration(r),
                "create_time": r.create_time.isoformat() if r.create_time else None,
                "metrics": _metrics_response(r),
                "ai_call_failed": fail_counts.get(r.id, 0),
            }
            for r in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/reviews/{review_id}/comments")
async def list_review_comments(
    review_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """获取评审的所有评论。"""
    comments = await list_comments_by_review(db, review_id)
    return [
        {
            "id": c.id,
            "review_id": c.review_id,
            "finding_id": c.finding_id,
            "author": c.author,
            "content": c.content,
            "action": c.action,
            "create_time": c.create_time.isoformat() if c.create_time else None,
        }
        for c in comments
    ]


@router.post("/reviews/{review_id}/comments", status_code=201)
async def create_review_comment(
    review_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """添加评论到评审。"""
    comment = await create_comment_for_review(
        db,
        review_id=review_id,
        finding_id=body.get("finding_id"),
        author=body.get("author", "anonymous"),
        content=body.get("content", ""),
        action=body.get("action"),
    )
    await db.flush()
    return {"id": comment.id, "status": "ok"}


@router.get("/reviews")
async def list_all_reviews(
    project_id: str | None = Query(None),
    status: str | None = Query(
        None, pattern="^(pending|running|completed|completed_with_errors|failed)$"
    ),
    score_min: int | None = Query(None, ge=0, le=100),
    score_max: int | None = Query(None, ge=0, le=100),
    date_from: str | None = Query(None),
    date_to: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """跨项目查询所有评审记录（含项目名和严重性分布）。"""
    stmt = (
        select(ReviewModel, ProjectModel.name.label("project_name"))
        .join(ProjectModel, ReviewModel.project_id == ProjectModel.id)
        .where(ReviewModel.is_deleted.is_(False))
    )
    if project_id:
        stmt = stmt.where(ReviewModel.project_id == project_id)
    if status:
        stmt = stmt.where(ReviewModel.status == status)
    if score_min is not None:
        stmt = stmt.where(ReviewModel.score >= score_min)
    if score_max is not None:
        stmt = stmt.where(ReviewModel.score <= score_max)
    if date_from:
        stmt = stmt.where(ReviewModel.create_time >= date_from)
    if date_to:
        stmt = stmt.where(ReviewModel.create_time <= date_to)

    count_stmt = select(ReviewModel.id).where(ReviewModel.is_deleted.is_(False))
    if project_id:
        count_stmt = count_stmt.where(ReviewModel.project_id == project_id)
    if status:
        count_stmt = count_stmt.where(ReviewModel.status == status)
    total_result = await db.execute(count_stmt)
    total = len(total_result.scalars().all())

    stmt = (
        stmt.order_by(ReviewModel.create_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    rows = await db.execute(stmt)
    review_ids: list[str] = []
    row_list = rows.all()
    for review, _project_name in row_list:
        review_ids.append(review.id)
    breakdowns = await _fetch_finding_breakdowns(db, review_ids)

    fail_counts = await _batch_query_ai_fail_counts(db, [review.id for review, _ in row_list])
    items: list[dict[str, Any]] = []
    for review, project_name in row_list:
        bd = breakdowns.get(review.id, {})
        items.append(
            {
                "id": review.id,
                "project_id": review.project_id,
                "project_name": project_name,
                "pr_number": review.pr_number,
                "pr_title": review.pr_title,
                "head_sha": review.head_sha,
                "status": review.status,
                "score": review.score,
                "findings_count": review.findings_count,
                "severity_breakdown": dict(bd.get("severity", {})),
                "category_breakdown": dict(bd.get("category", {})),
                "duration_seconds": _calc_duration(review),
                "create_time": review.create_time.isoformat() if review.create_time else None,
                "metrics": _metrics_response(review),
                "ai_call_failed": fail_counts.get(review.id, 0),
            }
        )
    return {"items": items, "total": total, "page": page, "page_size": page_size}


def _metrics_response(r: ReviewModel) -> dict[str, Any]:
    """构建评审的监控指标响应。"""
    return {
        "total_prompt_tokens": r.total_prompt_tokens,
        "total_completion_tokens": r.total_completion_tokens,
        "ai_call_count": r.ai_call_count,
        "pipeline_duration_ms": r.pipeline_duration_ms,
        "chunk_count": r.chunk_count,
        "file_count": r.file_count,
    }


async def _batch_query_ai_fail_counts(db: AsyncSession, review_ids: list[str]) -> dict[str, int]:
    """批量查询各评审的 AI 调用失败次数。"""
    if not review_ids:
        return {}
    rows = await db.execute(
        select(ReviewAICallModel.review_id, sa_func.count())
        .where(
            ReviewAICallModel.review_id.in_(review_ids),
            ReviewAICallModel.status == "failed",
        )
        .group_by(ReviewAICallModel.review_id)
    )
    return {row[0]: row[1] for row in rows.all()}
