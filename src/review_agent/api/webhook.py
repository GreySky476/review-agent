"""Webhook 接收端点。"""

from __future__ import annotations

import fnmatch
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.webhook_helpers import (
    ensure_project_connected,
    extract_pr_number,
    extract_repo_full_name,
    handle_push_event,
    parse_event_action,
    sync_pull_request,
    trigger_pr_review,
)
from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.service.error_logger import log_error
from review_agent.types.enums import EventAction, Platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitHub Webhook 事件。"""
    raw = await request.body()
    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON payload from GitHub webhook: %s", exc)
        await log_error(
            error_type="webhook_parse_failed",
            error_message=f"GitHub webhook invalid JSON: {exc}",
        )
        return {"status": "ignored", "reason": "invalid_json"}
    event_id = x_github_delivery or str(uuid4())

    logger.info(
        "GitHub webhook received: event=%s delivery=%s",
        x_github_event, event_id,
    )

    if x_github_event == "ping":
        hook_id = payload.get("hook_id", "?")
        zen = payload.get("zen", "")
        logger.info("GitHub ping: hook_id=%s zen=%s", hook_id, zen)
        return {"status": "pong", "hook_id": str(hook_id), "zen": zen}

    if x_github_event == "push":
        return await handle_push_event(db, payload, event_id)

    raw_action = payload.get("action", "")
    repo_full_name = extract_repo_full_name(Platform.GITHUB, payload)
    pr_number = extract_pr_number(Platform.GITHUB, payload)
    parsed_action = parse_event_action(Platform.GITHUB, payload)

    if repo_full_name and pr_number:
        project_id = await ensure_project_connected(
            db=db,
            platform=Platform.GITHUB,
            repo_full_name=repo_full_name,
            event_id=event_id,
            action=parsed_action.value if parsed_action else raw_action,
            pr_number=pr_number,
            raw_payload=raw.decode(),
        )

        pr_data = payload.get("pull_request", {})
        if project_id and pr_data:
            await sync_pull_request(db, project_id, Platform.GITHUB, pr_data, raw_action)

        trigger_actions = {EventAction.OPENED, EventAction.SYNCHRONIZE, EventAction.REOPENED}
        if project_id and parsed_action in trigger_actions:
            # 检查 PR 目标分支是否匹配 review_branches 设置
            pr_base_ref = pr_data.get("base", {}).get("ref")
            project_repo = ProjectRepo(db)
            allowed = await project_repo.get_review_branches(project_id)
            if pr_base_ref and not any(fnmatch.fnmatch(pr_base_ref, p) for p in allowed):
                logger.info(
                    "Skipped PR review: target_branch='%s' not in review list %s (project=%s)",
                    pr_base_ref, allowed, project_id,
                )
                return {"status": "skipped", "reason": "branch_not_matched"}

            pr_head_sha = pr_data.get("head", {}).get("sha")
            await trigger_pr_review(
                db=db,
                project_id=project_id,
                repo_full_name=repo_full_name,
                pr_head_sha=pr_head_sha,
                pr_number=pr_number,
            )

    if parsed_action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitLab Webhook 事件。"""
    raw = await request.body()
    payload: dict[str, Any] = json.loads(raw)
    logger.info("GitLab webhook received")

    repo_full_name = extract_repo_full_name(Platform.GITLAB, payload)
    action = parse_event_action(Platform.GITLAB, payload)
    pr_number = extract_pr_number(Platform.GITLAB, payload)

    if repo_full_name and pr_number:
        await ensure_project_connected(
            db=db,
            platform=Platform.GITLAB,
            repo_full_name=repo_full_name,
            event_id=str(uuid4()),
            action=action.value if action else "unknown",
            pr_number=pr_number,
            raw_payload=raw.decode(),
        )

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitee")
async def gitee_webhook(
    request: Request,
    x_gitee_event: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 Gitee Webhook 事件。"""
    raw = await request.body()
    payload: dict[str, Any] = json.loads(raw)

    logger.info("Gitee webhook received: event=%s", x_gitee_event)

    if x_gitee_event == "Test Hook":
        hook_id = payload.get("hook_id", "?")
        return {"status": "pong", "hook_id": str(hook_id), "event": "test_hook"}

    repo_full_name = extract_repo_full_name(Platform.GITEE, payload)
    action = parse_event_action(Platform.GITEE, payload)
    pr_number = extract_pr_number(Platform.GITEE, payload)

    if repo_full_name and pr_number:
        await ensure_project_connected(
            db=db,
            platform=Platform.GITEE,
            repo_full_name=repo_full_name,
            event_id=str(uuid4()),
            action=action.value if action else "unknown",
            pr_number=pr_number,
            raw_payload=raw.decode(),
        )

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    return {"status": "accepted", "pr_number": str(pr_number)}


@router.get("/health")
async def webhook_health() -> dict[str, str]:
    """Webhook 连通性手动验证端点。"""
    return {"status": "ok", "service": "review-agent"}
