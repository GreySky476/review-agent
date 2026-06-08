"""Webhook 接收端点。"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any

from fastapi import APIRouter, Header, Request

from review_agent.types.enums import EventAction, Platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])


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


@router.post("/github")
async def github_webhook(
    request: Request,
    x_github_event: str | None = Header(None),
) -> dict[str, str]:
    """接收 GitHub Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)
    _ = x_github_event

    action = _parse_event_action(Platform.GITHUB, payload)
    pr_number = _extract_pr_number(Platform.GITHUB, payload)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received GitHub webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitlab")
async def gitlab_webhook(request: Request) -> dict[str, str]:
    """接收 GitLab Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)

    action = _parse_event_action(Platform.GITLAB, payload)
    pr_number = _extract_pr_number(Platform.GITLAB, payload)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received GitLab webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitee")
async def gitee_webhook(request: Request) -> dict[str, str]:
    """接收 Gitee Webhook 事件。"""
    body = await request.body()
    payload: dict[str, Any] = json.loads(body)

    action = _parse_event_action(Platform.GITEE, payload)
    pr_number = _extract_pr_number(Platform.GITEE, payload)

    if action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info("Received Gitee webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}
