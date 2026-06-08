"""PR 管理 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

router = APIRouter(tags=["pull-requests"])


@router.get("/projects/{project_id}/pull-requests")
async def list_pull_requests(
    project_id: str,
    state: str | None = Query(None, pattern="^(open|merged|closed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """获取项目的 PR 列表。"""
    _ = (project_id, state)
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
    }


@router.get("/projects/{project_id}/pull-requests/{pr_number}")
async def get_pull_request_detail(
    project_id: str,
    pr_number: int,
) -> dict[str, Any]:
    """获取 PR 详情（含关联的 Review 和 Findings）。"""
    _ = (project_id, pr_number)
    return {
        "pull_request": {},
        "reviews": [],
        "findings": [],
    }
