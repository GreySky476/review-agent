"""评审详情与统计 API — 从 reviews.py 拆分以保持单文件 <300 行。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.types.orm import FindingModel, ProjectModel, ReviewModel

router = APIRouter(tags=["review-detail"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


def _calc_duration(review: ReviewModel) -> int | None:
    """计算评审耗时（秒）。"""
    if review.create_time and review.update_time:
        return int((review.update_time - review.create_time).total_seconds())
    return None


async def _fetch_finding_breakdowns(
    db: AsyncSession,
    review_ids: list[str],
) -> dict[str, dict[str, Any]]:
    """批量查询 findings 的严重性和类别分布。"""
    if not review_ids:
        return {}
    rows = await db.execute(
        select(
            FindingModel.review_id,
            FindingModel.severity,
            FindingModel.category,
        ).where(FindingModel.review_id.in_(review_ids))
    )
    result: dict[str, dict[str, Any]] = {}
    for r in rows.all():
        rid = r.review_id
        if rid not in result:
            result[rid] = {"severity": Counter(), "category": Counter()}
        result[rid]["severity"][r.severity] += 1
        result[rid]["category"][r.category] += 1
    return result


async def _fetch_file_summary(db: AsyncSession, review_id: str) -> list[dict[str, Any]]:
    """查询单个 review 的文件级统计。"""
    rows = await db.execute(
        select(FindingModel.file_path, FindingModel.severity).where(
            FindingModel.review_id == review_id
        )
    )
    file_map: dict[str, Counter[str]] = {}
    for r in rows.all():
        if r.file_path not in file_map:
            file_map[r.file_path] = Counter()
        file_map[r.file_path][r.severity] += 1
    return [
        {
            "file_path": path,
            "findings": sum(c.values()),
            "critical": c.get("critical", 0),
            "warning": c.get("warning", 0),
            "info": c.get("info", 0),
        }
        for path, c in sorted(file_map.items())
    ]


@router.get("/reviews/{review_id}")
async def get_review_detail(
    review_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取评审详情（含 findings 和聚合统计）。"""
    row = await db.execute(
        select(ReviewModel, ProjectModel.name.label("project_name"))
        .join(ProjectModel, ReviewModel.project_id == ProjectModel.id)
        .where(ReviewModel.id == review_id, ReviewModel.is_deleted.is_(False))
    )
    result = row.one_or_none()
    if not result:
        return {"error": "not_found", "message": f"Review {review_id} not found"}
    review, project_name = result

    finding_rows = await db.execute(
        select(FindingModel).where(
            FindingModel.review_id == review_id,
            FindingModel.is_deleted.is_(False),
        )
    )
    findings: list[dict[str, Any]] = []
    severity_counts: Counter[str] = Counter()
    category_counts: Counter[str] = Counter()
    for f in finding_rows.scalars().all():
        severity_counts[f.severity] += 1
        category_counts[f.category] += 1
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

    file_summary = await _fetch_file_summary(db, review_id)

    return {
        "id": review.id,
        "project_id": review.project_id,
        "project_name": project_name,
        "pr_number": review.pr_number,
        "pr_title": review.pr_title,
        "head_sha": review.head_sha,
        "status": review.status,
        "score": review.score,
        "findings_count": len(findings),
        "create_time": review.create_time.isoformat() if review.create_time else None,
        "update_time": review.update_time.isoformat() if review.update_time else None,
        "task_id": review.task_id,
        "error_message": review.error_message,
        "summary_markdown": review.summary_markdown,
        "statistics": {
            "severity": dict(severity_counts),
            "category": dict(category_counts),
        },
        "file_summary": file_summary,
        "findings": findings,
        "metrics": {
            "total_prompt_tokens": review.total_prompt_tokens,
            "total_completion_tokens": review.total_completion_tokens,
            "ai_call_count": review.ai_call_count,
            "pipeline_duration_ms": review.pipeline_duration_ms,
            "chunk_count": review.chunk_count,
            "file_count": review.file_count,
        },
    }


@router.get("/reviews/{review_id}/ai-calls")
async def list_review_ai_calls(
    review_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """查询评审的 AI 调用明细列表。"""
    from review_agent.types.orm import ReviewAICallModel

    rows = await db.execute(
        select(ReviewAICallModel)
        .where(ReviewAICallModel.review_id == review_id)
        .order_by(ReviewAICallModel.batch_idx)
    )
    return [
        {
            "id": r.id,
            "batch_idx": r.batch_idx,
            "model": r.model,
            "prompt_tokens": r.prompt_tokens,
            "completion_tokens": r.completion_tokens,
            "total_tokens": r.total_tokens,
            "duration_ms": r.duration_ms,
            "status": r.status,
            "error_message": r.error_message,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows.scalars().all()
    ]


@router.get("/reviews/stats")
async def get_review_stats(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """评审全局统计。"""
    count_result = await db.execute(
        select(func.count(), func.avg(ReviewModel.score)).where(
            ReviewModel.is_deleted.is_(False), ReviewModel.status == "completed"
        )
    )
    total_count, avg_score = count_result.one()
    avg_score = round(float(avg_score), 1) if avg_score else 0

    sev_rows = await db.execute(
        select(FindingModel.severity, func.count())
        .join(ReviewModel, FindingModel.review_id == ReviewModel.id)
        .where(ReviewModel.is_deleted.is_(False), ReviewModel.status == "completed")
        .group_by(FindingModel.severity)
    )
    severity_dist = {row.severity: row[1] for row in sev_rows.all()}

    cat_rows = await db.execute(
        select(FindingModel.category, func.count())
        .join(ReviewModel, FindingModel.review_id == ReviewModel.id)
        .where(ReviewModel.is_deleted.is_(False), ReviewModel.status == "completed")
        .group_by(FindingModel.category)
    )
    category_dist = {row.category: row[1] for row in cat_rows.all()}

    return {
        "total_reviews": total_count or 0,
        "avg_score": avg_score,
        "severity_distribution": severity_dist,
        "category_distribution": category_dist,
    }
