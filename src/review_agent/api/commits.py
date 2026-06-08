"""提交管理 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Query

from review_agent.types.models import CommitReviewRequest

router = APIRouter(tags=["commits"])


@router.get("/projects/{project_id}/commits")
async def list_commits(
    project_id: str,
    branch: str | None = Query(None),
    author: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
) -> dict[str, Any]:
    """获取项目的提交列表。"""
    _ = (project_id, branch, author)
    return {
        "items": [],
        "total": 0,
        "page": page,
        "page_size": page_size,
    }


@router.post("/projects/{project_id}/commits/{sha}/review", status_code=202)
async def trigger_commit_review(
    project_id: str,
    sha: str,
    body: CommitReviewRequest,
) -> dict[str, Any]:
    """通过 @mention 触发提交评审。"""
    _ = (project_id, sha, body)
    return {
        "status": "accepted",
        "task_id": None,
    }
