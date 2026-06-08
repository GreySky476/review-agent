"""异常监控 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from review_agent.types.models import ErrorStats

router = APIRouter(tags=["errors"])


@router.get("/errors")
async def list_errors(
    project_id: str | None = Query(None),
    error_type: str | None = Query(None),
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """获取异常日志列表。"""
    _ = (project_id, error_type, start_date, end_date)
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
    }


@router.get("/errors/stats")
async def error_statistics(
    start_date: str | None = Query(None),
    end_date: str | None = Query(None),
) -> list[ErrorStats]:
    """获取异常聚合统计。"""
    _ = (start_date, end_date)
    return []
