"""仪表盘统计 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from review_agent.types.models import DashboardStats

router = APIRouter(tags=["dashboard"])


@router.get("/dashboard/stats")
async def dashboard_stats() -> DashboardStats:
    """获取仪表盘统计信息。"""
    return DashboardStats(
        total_projects=0,
        total_reviews_today=0,
        average_score=0.0,
        pending_errors=0,
        finding_distribution={},
    )


@router.get("/dashboard/quality-trends")
async def quality_trends(
    project_id: str | None = Query(None),
    period: str = Query("monthly", pattern="^(daily|weekly|monthly)$"),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> dict[str, Any]:
    """获取质量趋势数据（折线图）。"""
    _ = (project_id, period, start_date, end_date)
    return {
        "items": [],
        "period": period,
    }
