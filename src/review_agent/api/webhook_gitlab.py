"""GitLab Webhook 接收端点。

遵循 GitLab Webhook 规范：
- Token 验证：``X-Gitlab-Token`` 请求头
- 事件类型：``X-Gitlab-Event: Merge Request Hook`` / ``Push Hook``
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

gitlab_router = APIRouter(tags=["webhook"])


def _normalize_gitlab_push_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """将 GitLab push 载荷转换为 GitHub 兼容格式。

    GitLab push 将 commit 信息放在 ``commits`` 数组中，
    而 handle_push_event 期望 ``head_commit`` 键。
    本函数从 ``commits`` 数组首元素创建 ``head_commit`` 字段。

    Args:
        payload: GitLab push webhook 原始载荷。

    Returns:
        包含 ``head_commit`` 和 ``repository`` 的标准化载荷（浅拷贝）。
    """
    commits: list[dict[str, Any]] = payload.get("commits", [])
    head_commit = commits[0] if commits else {}
    return {
        **payload,
        "head_commit": head_commit,
        "repository": payload.get("project", {}),
    }


def _normalize_gitlab_mr_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """将 GitLab MR 的 object_attributes 转换为 GitHub 兼容格式。

    Args:
        payload: GitLab webhook 原始载荷。

    Returns:
        GitHub 兼容的 PR 数据字典。
    """
    obj = payload.get("object_attributes", {})
    user = payload.get("user", {})
    return {
        "number": obj.get("iid"),
        "state": obj.get("state", "opened"),
        "merged": obj.get("state") == "merged",
        "title": obj.get("title", ""),
        "user": {"login": user.get("username")},
        "head": {"ref": obj.get("source_branch"), "sha": obj.get("last_commit", {}).get("id")},
        "base": {"ref": obj.get("target_branch")},
        "merge_commit_sha": obj.get("merge_commit_sha"),
        "merged_at": obj.get("merged_at"),
    }


@gitlab_router.post("/gitlab")
async def gitlab_webhook(  # noqa: PLR0915
    request: Request,
    x_gitlab_event: str | None = Header(None),
    x_gitlab_token: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> Any:
    """接收 GitLab Webhook 事件。

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
        logger.warning("GitLab webhook payload too large: %d bytes", len(raw))
        return JSONResponse(
            status_code=413,
            content={"status": "rejected", "reason": "payload_too_large"},
        )

    try:
        payload: dict[str, Any] = json.loads(raw)
    except json.JSONDecodeError as exc:
        logger.warning("GitLab webhook invalid JSON: %s", exc)
        await log_error(
            error_type="webhook_parse_failed",
            error_message=f"GitLab webhook invalid JSON: {exc}",
        )
        return {"status": "ignored", "reason": "invalid_json"}

    event_id = str(uuid4())
    delivery_label = event_id[:8]
    client_ip = request.client.host if request.client else ""

    logger.info(
        "GitLabWebhook[%s] received: event=%s from=%s",
        delivery_label,
        x_gitlab_event,
        client_ip or "unknown",
    )

    # ── 速率限制检查 ──
    settings = get_settings()
    should_rate_limit = settings.webhook_rate_limiter_enabled and client_ip
    if should_rate_limit and not await check_rate_limit(client_ip):
        logger.warning(
            "GitLabWebhook[%s] rate limit exceeded for IP=%s",
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
    repo_full_name = extract_repo_full_name(Platform.GITLAB, payload)
    if repo_full_name and x_gitlab_token:
        project = await get_project_by_platform_repo(db, Platform.GITLAB, repo_full_name)
        if (
            project
            and project.webhook_secret
            and not verify_platform_token(project.webhook_secret, x_gitlab_token)
        ):
            logger.warning(
                "GitLabWebhook[%s] token verification FAILED for repo=%s",
                delivery_label,
                repo_full_name,
            )
            await log_error(
                error_type="webhook_verify_failed",
                error_message=f"GitLab webhook token verification failed for {repo_full_name}",
                project_id=project.id,
            )
            return JSONResponse(
                status_code=403,
                content={"status": "rejected", "reason": "invalid_token"},
            )

    # ── Push Hook ──
    if x_gitlab_event == "Push Hook":
        logger.info("GitLabWebhook[%s] push event -> handle_push_event", delivery_label)
        normalized = _normalize_gitlab_push_payload(payload)
        result = await handle_push_event(db, normalized, event_id, platform=Platform.GITLAB)
        logger.info(
            "GitLabWebhook[%s] push result: status=%s",
            delivery_label,
            result.get("status"),
        )
        return result

    # ── Merge Request Hook ──
    if x_gitlab_event == "Merge Request Hook":
        raw_action = payload.get("object_attributes", {}).get("action", "")
        pr_number = extract_pr_number(Platform.GITLAB, payload)
        parsed_action = parse_event_action(Platform.GITLAB, payload)
        action_label = parsed_action.value if parsed_action else raw_action

        logger.info(
            "GitLabWebhook[%s] MR event: repo=%s mr=%s action=%s",
            delivery_label,
            repo_full_name,
            pr_number,
            action_label,
        )

        if repo_full_name and pr_number:
            project_id = await ensure_project_connected(
                db=db,
                platform=Platform.GITLAB,
                repo_full_name=repo_full_name,
                event_id=event_id,
                action=action_label,
                pr_number=pr_number,
                raw_payload=raw.decode(),
            )

            pr_data = _normalize_gitlab_mr_payload(payload)
            if project_id and pr_data:
                await sync_pull_request(db, project_id, Platform.GITLAB, pr_data, raw_action)
                logger.info(
                    "GitLabWebhook[%s] MR synced: project=%s mr=%d",
                    delivery_label,
                    project_id,
                    pr_number,
                )

            obj_attrs = payload.get("object_attributes", {})
            trigger_actions = {"open", "update", "reopen"}
            if project_id and raw_action in trigger_actions:
                mr_target_ref = obj_attrs.get("target_branch")
                allowed = await get_review_branches_for_project(db, project_id)
                if mr_target_ref and not any(fnmatch.fnmatch(mr_target_ref, p) for p in allowed):
                    logger.info(
                        "GitLabWebhook[%s] branch skipped: target='%s' not in %s",
                        delivery_label,
                        mr_target_ref,
                        allowed,
                    )
                    return {"status": "skipped", "reason": "branch_not_matched"}

                mr_head_sha = obj_attrs.get("last_commit", {}).get("id")
                # GitLab Merge Request webhook 的 changes 字段包含文件变更信息
                changes = payload.get("changes", {})
                extra_files: list[dict[str, Any]] = []
                for status_kind, files_list in [
                    ("added", changes.get("added", [])),
                    ("modified", changes.get("modified", [])),
                    ("removed", changes.get("removed", [])),
                ]:
                    for filename in files_list:
                        extra_files.append(
                            {
                                "filename": filename,
                                "status": status_kind,
                                "additions": 0,
                                "deletions": 0,
                                "patch": None,
                            }
                        )
                logger.info(
                    "GitLabWebhook[%s] triggering MR review: mr=%d sha=%s files=%d",
                    delivery_label,
                    pr_number,
                    mr_head_sha[:8] if mr_head_sha else "none",
                    len(extra_files),
                )
                await trigger_pr_review(
                    db=db,
                    project_id=project_id,
                    repo_full_name=repo_full_name,
                    pr_head_sha=mr_head_sha,
                    pr_number=pr_number,
                    platform=Platform.GITLAB,
                    extra_files=extra_files or None,
                )
            elif project_id:
                logger.info(
                    "GitLabWebhook[%s] no review: action=%s not in %s",
                    delivery_label,
                    raw_action,
                    trigger_actions,
                )
            return {"status": "accepted", "pr_number": str(pr_number)}

        logger.info("GitLabWebhook[%s] ignored: parse_failed", delivery_label)
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info(
        "GitLabWebhook[%s] ignored: unsupported event=%s",
        delivery_label,
        x_gitlab_event,
    )
    return {"status": "ignored", "reason": "unsupported_event"}
