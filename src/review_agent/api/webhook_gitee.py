"""Gitee Webhook 接收端点。

遵循 Gitee Webhook 规范：
- Token 验证：``X-Gitee-Token`` 请求头
- 事件类型：由请求体内容推断（MR 事件含 ``pull_request`` 键，Push 事件含 ``commits`` 键）
- 支持动作：open, update, reopen
"""

from __future__ import annotations

import fnmatch
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.config.settings import get_settings
from review_agent.service.error_logger import log_error
from review_agent.service.webhook_handler import (
    ensure_project_connected,
    extract_pr_number,
    extract_repo_full_name,
    get_project_by_platform_repo,
    get_review_branches_for_project,
    handle_push_event,
    parse_event_action,
    sync_pull_request,
    trigger_pr_review,
)
from review_agent.service.webhook_security import (
    check_payload_size,
    check_rate_limit,
    verify_platform_token,
)
from review_agent.types.enums import Platform

logger = logging.getLogger(__name__)

gitee_router = APIRouter(tags=["webhook"])


@gitee_router.post("/gitee")
async def gitee_webhook(  # noqa: PLR0915
    request: Request,
    x_gitee_token: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """接收 Gitee Webhook 事件。

    安全要求：
    - 若项目配置了 webhook_secret，所有事件需通过 Token 验证
    - Token 验证失败的请求返回 403
    """
    raw = await request.body()

    # ── Payload 大小限制 ──
    content_length: int | None = None
    cl_header = request.headers.get("content-length")
    if cl_header and cl_header.isdigit():
        content_length = int(cl_header)
    if not check_payload_size(content_length, raw):
        logger.warning("Gitee webhook payload too large: %d bytes", len(raw))
        return JSONResponse(
            status_code=413,
            content={"status": "rejected", "reason": "payload_too_large"},
        )

    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Gitee webhook invalid JSON: %s", exc)
        await log_error(
            error_type="webhook_parse_failed",
            error_message=f"Gitee webhook invalid JSON: {exc}",
        )
        return {"status": "ignored", "reason": "invalid_json"}

    event_id = str(uuid4())
    delivery_label = event_id[:8]
    client_ip = request.client.host if request.client else ""

    # 推断事件类型
    is_mr = "pull_request" in payload and "action" in payload
    is_push = "commits" in payload and "ref" in payload
    event_type = "mr" if is_mr else "push" if is_push else "unknown"

    logger.info(
        "GiteeWebhook[%s] received: event_type=%s from=%s",
        delivery_label,
        event_type,
        client_ip or "unknown",
    )

    # ── 速率限制检查 ──
    settings = get_settings()
    should_rate_limit = settings.webhook_rate_limiter_enabled and client_ip
    if should_rate_limit and not await check_rate_limit(client_ip):
        logger.warning(
            "GiteeWebhook[%s] rate limit exceeded for IP=%s",
            delivery_label,
            client_ip,
        )
        await log_error(
            error_type="webhook_verify_failed",
            error_message=f"Rate limit exceeded for IP {client_ip}",
        )
        return JSONResponse(
            status_code=429,
            content={"status": "rejected", "reason": "rate_limited"},
        )

    # ── Token 验证 ──
    repo_full_name = extract_repo_full_name(Platform.GITEE, payload)
    if repo_full_name and x_gitee_token:
        project = await get_project_by_platform_repo(db, Platform.GITEE, repo_full_name)
        if (
            project
            and project.webhook_secret
            and not verify_platform_token(project.webhook_secret, x_gitee_token)
        ):
            logger.warning(
                "GiteeWebhook[%s] token verification FAILED for repo=%s",
                delivery_label,
                repo_full_name,
            )
            await log_error(
                error_type="webhook_verify_failed",
                error_message=f"Gitee webhook token verification failed for {repo_full_name}",
                project_id=project.id,
            )
            return JSONResponse(
                status_code=403,
                content={"status": "rejected", "reason": "invalid_token"},
            )

    # ── Push 事件 ──
    if is_push:
        logger.info("GiteeWebhook[%s] push event -> handle_push_event", delivery_label)
        result = await handle_push_event(db, payload, event_id, platform=Platform.GITEE)
        logger.info(
            "GiteeWebhook[%s] push result: status=%s",
            delivery_label,
            result.get("status"),
        )
        return result

    # ── MR 事件 ──
    if is_mr:
        raw_action = payload.get("action", "")
        pr_number = extract_pr_number(Platform.GITEE, payload)
        parsed_action = parse_event_action(Platform.GITEE, payload)
        action_label = parsed_action.value if parsed_action else raw_action

        logger.info(
            "GiteeWebhook[%s] MR event: repo=%s pr=%s action=%s",
            delivery_label,
            repo_full_name,
            pr_number,
            action_label,
        )

        if repo_full_name and pr_number:
            project_id = await ensure_project_connected(
                db=db,
                platform=Platform.GITEE,
                repo_full_name=repo_full_name,
                event_id=event_id,
                action=action_label,
                pr_number=pr_number,
                raw_payload=raw.decode(),
            )

            pr_data = payload.get("pull_request", {})
            if project_id and pr_data:
                await sync_pull_request(db, project_id, Platform.GITEE, pr_data, raw_action)
                logger.info(
                    "GiteeWebhook[%s] MR synced: project=%s pr=%d",
                    delivery_label,
                    project_id,
                    pr_number,
                )

            pr_base_ref = pr_data.get("base", {}).get("ref")
            trigger_actions = {"open", "update", "reopen"}
            if project_id and raw_action in trigger_actions:
                allowed = await get_review_branches_for_project(db, project_id)
                if pr_base_ref and not any(fnmatch.fnmatch(pr_base_ref, p) for p in allowed):
                    logger.info(
                        "GiteeWebhook[%s] branch skipped: base='%s' not in %s",
                        delivery_label,
                        pr_base_ref,
                        allowed,
                    )
                    return {"status": "skipped", "reason": "branch_not_matched"}

                pr_head_sha = pr_data.get("head", {}).get("sha")
                # Gitee webhook 负载包含变更文件列表
                gitee_files = pr_data.get("files", [])
                extra_files = [
                    {
                        "filename": f.get("filename", ""),
                        "status": f.get("status", "modified"),
                        "additions": f.get("additions", 0),
                        "deletions": f.get("deletions", 0),
                        "patch": f.get("patch"),
                    }
                    for f in gitee_files
                    if f.get("filename")
                ]
                logger.info(
                    "GiteeWebhook[%s] triggering MR review: pr=%d sha=%s files=%d",
                    delivery_label,
                    pr_number,
                    pr_head_sha[:8] if pr_head_sha else "none",
                    len(extra_files),
                )
                await trigger_pr_review(
                    db=db,
                    project_id=project_id,
                    repo_full_name=repo_full_name,
                    pr_head_sha=pr_head_sha,
                    pr_number=pr_number,
                    platform=Platform.GITEE,
                    extra_files=extra_files,
                )
            elif project_id:
                logger.info(
                    "GiteeWebhook[%s] no review: action=%s not in %s",
                    delivery_label,
                    raw_action,
                    trigger_actions,
                )
            return {"status": "accepted", "pr_number": str(pr_number)}

        logger.info("GiteeWebhook[%s] ignored: parse_failed", delivery_label)
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info(
        "GiteeWebhook[%s] ignored: unsupported event_type=%s",
        delivery_label,
        event_type,
    )
    return {"status": "ignored", "reason": "unsupported_event"}
