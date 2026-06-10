"""Findings 查询与反馈 API 端点。

提供：
1. GET  /reviews/{review_id}/findings — 获取评审的所有 Finding
2. POST /reviews/{review_id}/findings/{finding_id}/feedback — 提交采纳/无效反馈
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.comment import CommentRepo
from review_agent.repo.finding import FindingRepo

router = APIRouter(tags=["findings"])


@router.get("/reviews/{review_id}/findings")
async def list_review_findings(
    review_id: str,
    db: AsyncSession = Depends(get_session),
) -> list[dict[str, Any]]:
    """获取指定评审的所有 Finding。"""
    repo = FindingRepo(db)
    findings = await repo.list_by_review(review_id)
    return [
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
            "create_time": f.create_time.isoformat() if f.create_time else None,
        }
        for f in findings
    ]


@router.get("/reviews/{review_id}/findings/{finding_id}/feedback")
async def get_finding_feedback(
    review_id: str,
    finding_id: str,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取某个 Finding 的反馈状态与评论。"""
    _ = review_id  # 路径参数，由 FastAPI 注入
    repo = CommentRepo(db)
    comments = await repo.list_by_finding(finding_id)

    # 确定当前反馈状态
    action = None
    for c in comments:
        if c.action in ("accepted", "invalid"):
            action = c.action

    return {
        "finding_id": finding_id,
        "action": action,
        "comments": [
            {
                "id": c.id,
                "author": c.author,
                "content": c.content,
                "action": c.action,
                "create_time": c.create_time.isoformat() if c.create_time else None,
            }
            for c in comments
        ],
    }


@router.post("/reviews/{review_id}/findings/{finding_id}/feedback")
async def submit_feedback(
    review_id: str,
    finding_id: str,
    body: dict[str, Any],
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """提交对 Finding 的反馈（采纳/无效）。

    Body: { "action": "accepted" | "invalid" | null }
    action 为 null 时取消之前的反馈。
    """
    action = body.get("action")
    if action not in ("accepted", "invalid", None):
        return {"status": "error", "message": "action must be 'accepted', 'invalid', or null"}

    repo = CommentRepo(db)
    # 查找该 finding 已有的反馈评论
    existing = await repo.list_by_finding(finding_id)
    feedback_comment = None
    for c in existing:
        if c.action in ("accepted", "invalid"):
            feedback_comment = c
            break

    if action is None:
        # 取消反馈 — 删除原有的反馈评论
        if feedback_comment:
            await repo.hard_delete(feedback_comment.id)
            await db.flush()
        return {"status": "ok", "action": None}

    # 更新或创建反馈
    if feedback_comment:
        await repo.update(feedback_comment.id, action=action)
    else:
        await repo.create(
            review_id=review_id,
            finding_id=finding_id,
            author="system",
            content=f"Feedback: {action}",
            action=action,
        )
    await db.flush()

    return {"status": "ok", "action": action}
