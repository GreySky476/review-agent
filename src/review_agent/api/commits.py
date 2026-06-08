"""提交管理 API 端点。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.commit import CommitRepo
from review_agent.types.models import CommitReviewRequest

router = APIRouter(tags=["commits"])


@router.get("/projects/{project_id}/commits")
async def list_commits(
    project_id: str,
    branch: str | None = Query(None),
    author: str | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的提交列表。"""
    repo = CommitRepo(db)

    items = await repo.list_by_project(
        project_id,
        branch=branch,
        author=author,
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total
    count_filters: dict[str, Any] = {"project_id": project_id}
    if branch:
        count_filters["branch"] = branch
    if author:
        count_filters["author"] = author
    total = await repo.count(filters=count_filters)

    return {
        "items": [
            {
                "id": c.id,
                "sha": c.sha,
                "author": c.author,
                "message": c.message,
                "branch": c.branch,
                "pr_number": c.pr_number,
                "is_reviewed": c.is_reviewed,
                "create_time": c.create_time.isoformat() if c.create_time else None,
            }
            for c in items
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.post("/projects/{project_id}/commits/{sha}/review", status_code=202)
async def trigger_commit_review(
    project_id: str,
    sha: str,
    body: CommitReviewRequest,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """通过 @mention 触发提交评审。"""
    _ = (project_id, body)
    repo = CommitRepo(db)
    commit = await repo.get_by_sha(project_id, sha)

    return {
        "status": "accepted",
        "task_id": None,
        "commit_found": commit is not None,
    }
