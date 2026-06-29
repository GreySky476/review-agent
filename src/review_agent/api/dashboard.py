"""仪表盘统计 API 端点。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.service.dashboard_handler import (
    count_projects as _count_projects,
)
from review_agent.service.dashboard_handler import (
    list_platform_health,
    list_projects_all,
    list_quality_snapshots,
)
from review_agent.types.models import DashboardStats, EnterpriseDashboard
from review_agent.types.orm import FindingModel, ProjectModel, ReviewErrorLog, ReviewModel

router = APIRouter(tags=["dashboard"])  # TODO: 登录页面未就绪，暂时不启用 JWT 认证


@router.get("/dashboard/stats")
async def dashboard_stats(
    db: AsyncSession = Depends(get_session),
) -> DashboardStats:
    """获取仪表盘统计信息。"""
    total_projects = await _count_projects(db)

    today_start = sa.func.current_date()
    today_count_result = await db.execute(
        select(func.count(ReviewModel.id)).where(
            sa.cast(ReviewModel.create_time, sa.Date) == today_start,
            ReviewModel.is_deleted.is_(False),
        )
    )
    total_reviews_today = today_count_result.scalar() or 0

    avg_result = await db.execute(
        select(func.avg(ReviewModel.score)).where(
            ReviewModel.score.isnot(None),
            ReviewModel.is_deleted.is_(False),
        )
    )
    avg_score = avg_result.scalar() or 0.0

    pending_result = await db.execute(
        select(func.count(ReviewErrorLog.id)).where(ReviewErrorLog.recovered.is_(False))
    )
    pending_errors = pending_result.scalar() or 0

    find_dist_result = await db.execute(
        select(FindingModel.category, func.count(FindingModel.id))
        .where(
            FindingModel.is_deleted.is_(False),
        )
        .group_by(FindingModel.category)
    )
    finding_distribution: dict[str, int] = {}
    for row in find_dist_result.all():
        finding_distribution[row[0]] = row[1]

    return DashboardStats(
        total_projects=total_projects,
        total_reviews_today=total_reviews_today,
        average_score=round(float(avg_score), 1),
        pending_errors=pending_errors,
        finding_distribution=finding_distribution,
    )


@router.get("/dashboard/quality-trends")
async def quality_trends(
    project_id: str | None = Query(None),
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取质量趋势数据（折线图）。"""
    snapshots = await list_quality_snapshots(
        db,
        project_id=project_id,
        period=period,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "items": [
            {
                "date": s.snapshot_date.isoformat() if s.snapshot_date else "",
                "avg_score": s.avg_score,
                "total_reviews": s.total_reviews,
                "total_findings": s.total_findings,
                "critical": s.critical_count,
                "warning": s.warning_count,
                "info": s.info_count,
            }
            for s in snapshots
        ],
        "period": period,
    }


# ── 企业级仪表盘 ──────────────────────────────────────────────


@router.get("/dashboard/enterprise")
async def enterprise_dashboard(
    db: AsyncSession = Depends(get_session),
) -> EnterpriseDashboard:
    """企业级仪表盘执行摘要。"""
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    # 项目计数
    total_projects = await _count_projects(db)

    # 本周 vs 上周评审统计
    this_week_total = await db.execute(
        select(func.count(ReviewModel.id)).where(
            ReviewModel.create_time >= week_ago,
            ReviewModel.is_deleted.is_(False),
        )
    )
    reviews_this_week = this_week_total.scalar() or 0

    last_week_total = await db.execute(
        select(func.count(ReviewModel.id)).where(
            ReviewModel.create_time >= two_weeks_ago,
            ReviewModel.create_time < week_ago,
            ReviewModel.is_deleted.is_(False),
        )
    )
    reviews_last_week = last_week_total.scalar() or 0

    # 本周 vs 上周按状态分组
    status_rows = await db.execute(
        select(ReviewModel.status, func.count(ReviewModel.id))
        .where(
            ReviewModel.create_time >= week_ago,
            ReviewModel.is_deleted.is_(False),
        )
        .group_by(ReviewModel.status)
    )
    reviews_by_status: dict[str, int] = {}
    for row in status_rows.all():
        reviews_by_status[row[0]] = row[1]

    last_week_status_rows = await db.execute(
        select(ReviewModel.status, func.count(ReviewModel.id))
        .where(
            ReviewModel.create_time >= two_weeks_ago,
            ReviewModel.create_time < week_ago,
            ReviewModel.is_deleted.is_(False),
        )
        .group_by(ReviewModel.status)
    )
    reviews_last_week_by_status: dict[str, int] = {}
    for row in last_week_status_rows.all():
        reviews_last_week_by_status[row[0]] = row[1]

    # 平均评分
    avg_row = await db.execute(
        select(func.avg(ReviewModel.score)).where(
            ReviewModel.create_time >= week_ago,
            ReviewModel.score.isnot(None),
            ReviewModel.is_deleted.is_(False),
        )
    )
    avg_score = float(avg_row.scalar() or 0.0)

    avg_last_row = await db.execute(
        select(func.avg(ReviewModel.score)).where(
            ReviewModel.create_time >= two_weeks_ago,
            ReviewModel.create_time < week_ago,
            ReviewModel.score.isnot(None),
            ReviewModel.is_deleted.is_(False),
        )
    )
    avg_score_last = float(avg_last_row.scalar() or 0.0)

    # 异常率
    total_completed = reviews_by_status.get("completed", 0) + reviews_by_status.get(
        "completed_with_errors", 0
    )
    total_with_errors = reviews_by_status.get("completed_with_errors", 0)
    error_rate = (total_with_errors / max(total_completed, 1)) * 100

    last_total_completed = reviews_last_week_by_status.get(
        "completed", 0
    ) + reviews_last_week_by_status.get("completed_with_errors", 0)
    last_with_errors = reviews_last_week_by_status.get("completed_with_errors", 0)
    error_rate_last = (last_with_errors / max(last_total_completed, 1)) * 100

    # Top 问题类别
    top_findings_rows = await db.execute(
        select(FindingModel.category, func.count(FindingModel.id))
        .select_from(FindingModel)
        .join(ReviewModel, FindingModel.review_id == ReviewModel.id)
        .where(
            ReviewModel.create_time >= week_ago,
            FindingModel.is_deleted.is_(False),
        )
        .group_by(FindingModel.category)
        .order_by(func.count(FindingModel.id).desc())
        .limit(5)
    )
    top_findings = [{"category": row[0], "count": row[1]} for row in top_findings_rows.all()]

    # 平台健康
    platform_list = await list_platform_health(db)
    platform_health: dict[str, str] = {}
    for p in platform_list:
        platform_health[p["platform"]] = p["status"]

    def _pct_change(current: int | float, previous: int | float) -> float:
        if previous == 0:
            return 100.0 if current > 0 else 0.0
        return round(((current - previous) / previous) * 100, 1)

    return EnterpriseDashboard(
        total_projects=total_projects,
        total_projects_change=0.0,  # 项目数变化较慢，暂不计算
        reviews_this_week=reviews_this_week,
        reviews_week_change=_pct_change(reviews_this_week, reviews_last_week),
        avg_score=round(avg_score, 1),
        avg_score_change=round(avg_score - avg_score_last, 1),
        error_rate=round(error_rate, 1),
        error_rate_change=round(error_rate - error_rate_last, 1),
        review_coverage=0.0,  # commit 覆盖率需要 commit 表配合
        reviews_by_status=reviews_by_status,
        top_findings=top_findings,
    )


@router.get("/dashboard/project-health")
async def project_health(
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """项目健康矩阵。"""
    now = datetime.now(UTC)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    projects = await list_projects_all(db, limit=100)

    items: list[dict[str, Any]] = []
    for p in projects:
        # 最新评分
        latest_row = await db.execute(
            select(ReviewModel.score, ReviewModel.create_time)
            .where(
                ReviewModel.project_id == p.id,
                ReviewModel.score.isnot(None),
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        latest = latest_row.first()
        latest_score = latest[0] if latest else None
        last_review_at = latest[1].isoformat() if latest and latest[1] else None

        # 7 天前评分（用于计算变化）
        old_row = await db.execute(
            select(ReviewModel.score)
            .where(
                ReviewModel.project_id == p.id,
                ReviewModel.create_time >= two_weeks_ago,
                ReviewModel.create_time < week_ago,
                ReviewModel.score.isnot(None),
                ReviewModel.is_deleted.is_(False),
            )
            .order_by(ReviewModel.create_time.desc())
            .limit(1)
        )
        old_score = old_row.scalar_one_or_none()

        # 7 天内评审数和异常数
        count_row = await db.execute(
            select(
                func.count(ReviewModel.id),
                func.sum(
                    sa.cast(ReviewModel.status == "completed_with_errors", sa.Integer),
                ),
            ).where(
                ReviewModel.project_id == p.id,
                ReviewModel.create_time >= week_ago,
                ReviewModel.is_deleted.is_(False),
            )
        )
        counts = count_row.first()
        review_count_7d = int(counts[0]) if counts and counts[0] is not None else 0
        error_count_7d = int(counts[1]) if counts and counts[1] is not None else 0

        # 健康状态
        if latest_score is None:
            health = "dormant"
        elif latest_score >= 90 and error_count_7d == 0:
            health = "active"
        elif latest_score >= 70:
            health = "warning"
        else:
            health = "critical"

        # 评分变化
        score_change: int | None = None
        if latest_score is not None and old_score is not None:
            score_change = latest_score - old_score

        items.append(
            {
                "project_id": p.id,
                "project_name": p.name,
                "platform": p.platform,
                "latest_score": latest_score,
                "score_change": score_change,
                "health": health,
                "review_count_7d": review_count_7d,
                "error_count_7d": error_count_7d,
                "last_review_at": last_review_at,
            }
        )

    # 按健康状态排序：critical → warning → active → dormant
    health_order = {"critical": 0, "warning": 1, "active": 2, "dormant": 3}
    items.sort(key=lambda x: (health_order.get(x["health"], 99), -(x["latest_score"] or 0)))

    return {"items": items, "total": len(items)}


@router.get("/dashboard/recent-reviews")
async def recent_reviews(
    limit: int = Query(10, ge=1, le=50),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """最近评审活动。"""
    rows = await db.execute(
        select(
            ReviewModel.id,
            ProjectModel.name.label("project_name"),
            ReviewModel.project_id,
            ReviewModel.pr_title,
            ReviewModel.branch,
            ReviewModel.status,
            ReviewModel.score,
            ReviewModel.head_sha,
            ReviewModel.create_time,
            ReviewModel.update_time,
        )
        .join(ProjectModel, ReviewModel.project_id == ProjectModel.id)
        .where(ReviewModel.is_deleted.is_(False))
        .order_by(ReviewModel.create_time.desc())
        .limit(limit)
    )

    items: list[dict[str, Any]] = []
    for row in rows.all():
        duration: int | None = None
        if row.create_time and row.update_time:
            duration = int((row.update_time - row.create_time).total_seconds())
        items.append(
            {
                "review_id": row.id,
                "project_name": row.project_name,
                "project_id": row.project_id,
                "pr_title": row.pr_title,
                "branch": row.branch,
                "status": row.status,
                "score": row.score,
                "head_sha": row.head_sha[:8] if row.head_sha else "",
                "duration_seconds": duration,
                "created_at": row.create_time.isoformat() if row.create_time else None,
            }
        )

    return {"items": items}
