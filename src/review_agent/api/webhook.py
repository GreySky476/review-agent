"""Webhook 接收端点。"""

from __future__ import annotations

import fnmatch
import json
import logging
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.api.webhook_helpers import (
    ensure_project_connected,
    extract_pr_number,
    extract_repo_full_name,
    handle_push_event,
    parse_event_action,
    sync_pull_request,
    trigger_pr_review,
    verify_github_signature,
)
from review_agent.config.database import get_session
from review_agent.config.settings import get_settings
from review_agent.repo.project import ProjectRepo
from review_agent.service.error_logger import log_error
from review_agent.service.webhook_security import (
    check_payload_size,
    check_rate_limit,
    is_github_request,
)
from review_agent.types.enums import EventAction, Platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    x_github_delivery: str | None = Header(None),
    x_hub_signature_256: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """接收 GitHub Webhook 事件。

    安全要求：
    - 若项目配置了 webhook_secret，所有 push/pull_request 事件需通过签名验证
    - 签名验证失败的请求返回 403
    - ping 事件和后向兼容（无 secret 的项目）不验证
    """
    raw = await request.body()

    # ── Payload 大小限制 ──
    content_length: int | None = None
    cl_header = request.headers.get("content-length")
    if cl_header and cl_header.isdigit():
        content_length = int(cl_header)
    if not check_payload_size(content_length, raw):
        logger.warning("Webhook payload too large: %d bytes", len(raw))
        return JSONResponse(
            status_code=413,
            content={"status": "rejected", "reason": "payload_too_large"},
        )

    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("Webhook invalid JSON: %s", exc)
        await log_error(
            error_type="webhook_parse_failed",
            error_message=f"GitHub webhook invalid JSON: {exc}",
        )
        return {"status": "ignored", "reason": "invalid_json"}
    event_id = x_github_delivery or str(uuid4())
    delivery_label = event_id[:8]
    client_ip = request.client.host if request.client else ""

    logger.info(
        "Webhook[%s] received: event=%s from=%s",
        delivery_label,
        x_github_event,
        client_ip or "unknown",
    )

    # ── 速率限制检查 ──
    settings = get_settings()
    should_rate_limit = settings.webhook_rate_limiter_enabled and client_ip
    if should_rate_limit and not await check_rate_limit(client_ip):
        logger.warning(
            "Webhook[%s] rate limit exceeded for IP=%s",
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

    # ── 签名验证（仅对 push/pull_request 事件，ping 跳过） ──
    if x_hub_signature_256 and x_github_event in ("push", "pull_request"):
        repo_full_name = extract_repo_full_name(Platform.GITHUB, payload)
        if repo_full_name:
            repo_url = f"https://github.com/{repo_full_name}"
            project = await ProjectRepo(db).get_by_platform_repo(Platform.GITHUB, repo_url)
            if project and project.webhook_secret:
                if not verify_github_signature(raw, x_hub_signature_256, project.webhook_secret):
                    logger.warning(
                        "Webhook[%s] signature verification FAILED for repo=%s",
                        delivery_label,
                        repo_full_name,
                    )
                    await log_error(
                        error_type="webhook_verify_failed",
                        error_message=(
                            f"GitHub webhook signature verification failed for {repo_full_name}"
                        ),
                        project_id=project.id,
                    )
                    return JSONResponse(
                        status_code=403,
                        content={"status": "rejected", "reason": "invalid_signature"},
                    )
                logger.debug(
                    "Webhook[%s] signature verified for repo=%s project=%s",
                    delivery_label,
                    repo_full_name,
                    project.id,
                )
            elif project and not project.webhook_secret:
                logger.debug(
                    "Webhook[%s] no secret configured for project %s, skipping verification",
                    delivery_label,
                    project.id,
                )
        else:
            logger.debug(
                "Webhook[%s] cannot extract repo, skipping signature verification",
                delivery_label,
            )

    # ── IP 白名单检查（仅 push/pull_request 事件） ──
    # 注：生产环境宜在反向代理层（ALB/nginx）配置 X-Forwarded-For，
    # 此处使用 request.client.host 直接可用
    should_check_ip = (
        settings.webhook_ip_whitelist_enabled
        and x_github_event in ("push", "pull_request")
        and client_ip
    )
    if should_check_ip and not await is_github_request(client_ip):
        logger.warning(
            "Webhook[%s] IP %s not in GitHub whitelist, rejecting",
            delivery_label,
            client_ip,
        )
        await log_error(
            error_type="webhook_verify_failed",
            error_message=(f"Webhook rejected: client IP {client_ip} not in GitHub whitelist"),
        )
        return JSONResponse(
            status_code=403,
            content={"status": "rejected", "reason": "ip_not_whitelisted"},
        )

    # ── ping ──
    if x_github_event == "ping":
        hook_id = payload.get("hook_id", "?")
        zen = payload.get("zen", "")
        logger.info("Webhook[%s] ping: hook_id=%s zen=%s", delivery_label, hook_id, zen)
        return {"status": "pong", "hook_id": str(hook_id), "zen": zen}

    # ── push ──
    if x_github_event == "push":
        logger.info("Webhook[%s] push event -> handle_push_event", delivery_label)
        result = await handle_push_event(db, payload, event_id)
        logger.info(
            "Webhook[%s] push result: status=%s sha=%s",
            delivery_label,
            result.get("status"),
            result.get("sha", "")[:8],
        )
        return result

    # ── PR event ──
    raw_action = payload.get("action", "")
    repo_full_name = extract_repo_full_name(Platform.GITHUB, payload)
    pr_number = extract_pr_number(Platform.GITHUB, payload)
    parsed_action = parse_event_action(Platform.GITHUB, payload)
    action_label = parsed_action.value if parsed_action else raw_action

    logger.info(
        "Webhook[%s] PR event: repo=%s pr=%s action=%s",
        delivery_label,
        repo_full_name,
        pr_number,
        action_label,
    )

    if repo_full_name and pr_number:
        project_id = await ensure_project_connected(
            db=db,
            platform=Platform.GITHUB,
            repo_full_name=repo_full_name,
            event_id=event_id,
            action=action_label,
            pr_number=pr_number,
            raw_payload=raw.decode(),
        )

        if project_id:
            logger.info("Webhook[%s] project found: id=%s", delivery_label, project_id)
        else:
            logger.warning(
                "Webhook[%s] project not found for repo=%s",
                delivery_label,
                repo_full_name,
            )

        pr_data = payload.get("pull_request", {})
        if project_id and pr_data:
            await sync_pull_request(db, project_id, Platform.GITHUB, pr_data, raw_action)
            logger.info(
                "Webhook[%s] PR synced: project=%s pr=%d",
                delivery_label,
                project_id,
                pr_number,
            )

        trigger_actions = {EventAction.OPENED, EventAction.SYNCHRONIZE, EventAction.REOPENED}
        if project_id and parsed_action in trigger_actions:
            pr_base_ref = pr_data.get("base", {}).get("ref")
            project_repo = ProjectRepo(db)
            allowed = await project_repo.get_review_branches(project_id)
            if pr_base_ref and not any(fnmatch.fnmatch(pr_base_ref, p) for p in allowed):
                logger.info(
                    "Webhook[%s] branch skipped: base='%s' not in %s",
                    delivery_label,
                    pr_base_ref,
                    allowed,
                )
                return {"status": "skipped", "reason": "branch_not_matched"}

            pr_head_sha = pr_data.get("head", {}).get("sha")
            logger.info(
                "Webhook[%s] triggering PR review: pr=%d sha=%s",
                delivery_label,
                pr_number,
                pr_head_sha[:8] if pr_head_sha else "none",
            )
            await trigger_pr_review(
                db=db,
                project_id=project_id,
                repo_full_name=repo_full_name,
                pr_head_sha=pr_head_sha,
                pr_number=pr_number,
            )
        elif project_id and parsed_action:
            logger.info(
                "Webhook[%s] no review: action=%s not in %s",
                delivery_label,
                action_label,
                [a.value for a in trigger_actions],
            )
    else:
        logger.warning(
            "Webhook[%s] parse failed: repo=%s pr=%s action=%s",
            delivery_label,
            repo_full_name,
            pr_number,
            action_label,
        )

    if parsed_action is None or pr_number is None:
        logger.info("Webhook[%s] ignored: parse_failed", delivery_label)
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Webhook[%s] accepted: pr=%s action=%s", delivery_label, pr_number, action_label)
    return {"status": "accepted", "pr_number": str(pr_number)}
