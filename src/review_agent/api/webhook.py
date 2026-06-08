"""Webhook 接收端点。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.project import ProjectRepo
from review_agent.types.enums import EventAction, Platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

# Platform name → full domain prefix mapping for repo_url lookup
_PLATFORM_DOMAINS: dict[Platform, str] = {
    Platform.GITHUB: "github.com",
    Platform.GITLAB: "gitlab.com",
    Platform.GITEE: "gitee.com",
}


async def _lookup_and_mark_connected(
    db: AsyncSession,
    platform: Platform,
    repo_full_name: str | None,
) -> None:
    """根据 repo full name 查找项目并标记 webhook 为已连接。"""
    if not repo_full_name:
        return
    domain = _PLATFORM_DOMAINS.get(platform)
    if not domain:
        return
    repo_url = f"https://{domain}/{repo_full_name}"
    repo = ProjectRepo(db)
    project = await repo.get_by_platform_repo(platform, repo_url)
    if project and not project.webhook_enabled:
        project.webhook_enabled = True
        await db.flush()
        logger.info("Marked project %s webhook as connected", project.id)


def _verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """验证 GitHub Webhook 签名。"""
    expected = hmac.new(
        secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def _parse_event_action(platform: Platform, body: dict[str, Any]) -> EventAction | None:
    """从事件体中提取动作类型。"""
    action = body.get("action", "")
    if platform == Platform.GITHUB:
        action_map = {
            "opened": EventAction.OPENED,
            "synchronize": EventAction.SYNCHRONIZE,
            "reopened": EventAction.REOPENED,
        }
        return action_map.get(action)
    if platform in (Platform.GITLAB, Platform.GITEE):
        action_map = {
            "open": EventAction.OPENED,
            "update": EventAction.SYNCHRONIZE,
            "reopen": EventAction.REOPENED,
        }
        return action_map.get(action)
    return None


def _extract_pr_number(platform: Platform, body: dict[str, Any]) -> int | None:
    """从事件体中提取 PR 编号。"""
    if platform == Platform.GITHUB:
        pr: dict[str, Any] = body.get("pull_request", {})
        pr_number: int | None = pr.get("number")
        return pr_number
    if platform in (Platform.GITLAB, Platform.GITEE):
        obj: dict[str, Any] = body.get("object_attributes", {})
        iid: int | None = obj.get("iid")
        return iid
    return None


def _extract_repo_full_name(platform: Platform, body: dict[str, Any]) -> str | None:
    """从事件体中提取仓库全名（org/repo）。"""
    if platform == Platform.GITHUB:
        repo: dict[str, Any] = body.get("repository", {})
        return repo.get("full_name")
    if platform in (Platform.GITLAB, Platform.GITEE):
        project_info: dict[str, Any] = body.get("project", {})
        return project_info.get("path_with_namespace")
    return None


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitHub Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)
    _ = x_github_event

    repo_full_name = _extract_repo_full_name(Platform.GITHUB, payload)
    action = _parse_event_action(Platform.GITHUB, payload)
    pr_number = _extract_pr_number(Platform.GITHUB, payload)

    if repo_full_name:
        await _lookup_and_mark_connected(db, Platform.GITHUB, repo_full_name)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received GitHub webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitLab Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)

    repo_full_name = _extract_repo_full_name(Platform.GITLAB, payload)
    action = _parse_event_action(Platform.GITLAB, payload)
    pr_number = _extract_pr_number(Platform.GITLAB, payload)

    if repo_full_name:
        await _lookup_and_mark_connected(db, Platform.GITLAB, repo_full_name)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received GitLab webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitee")
async def gitee_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 Gitee Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)

    repo_full_name = _extract_repo_full_name(Platform.GITEE, payload)
    action = _parse_event_action(Platform.GITEE, payload)
    pr_number = _extract_pr_number(Platform.GITEE, payload)

    if repo_full_name:
        await _lookup_and_mark_connected(db, Platform.GITEE, repo_full_name)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received Gitee webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}
