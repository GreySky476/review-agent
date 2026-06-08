"""Webhook 接收端点。"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import json
import logging
from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.commit import CommitRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.service.queue import enqueue_commit_review
from review_agent.types.enums import EventAction, Platform

logger = logging.getLogger(__name__)

router = APIRouter(tags=["webhook"])

_PLATFORM_DOMAINS: dict[Platform, str] = {
    Platform.GITHUB: "github.com",
    Platform.GITLAB: "gitlab.com",
    Platform.GITEE: "gitee.com",
}


async def _ensure_project_connected(
    db: AsyncSession,
    platform: Platform,
    repo_full_name: str | None,
    event_id: str,
    action: str,
    pr_number: int,
    raw_payload: str,
) -> str | None:
    """查找项目，标记 webhook 已连接，并记录事件。返回 project_id 或 None。"""
    if not repo_full_name:
        return None
    domain = _PLATFORM_DOMAINS.get(platform)
    if not domain:
        return None
    repo_url = f"https://{domain}/{repo_full_name}"
    project_repo = ProjectRepo(db)
    project = await project_repo.get_by_platform_repo(platform, repo_url)
    if not project:
        logger.warning("No project found for repo: %s", repo_url)
        return None

    # 标记 webhook 已连接
    if not project.webhook_enabled:
        project.webhook_enabled = True
        await db.flush()
        logger.info("Marked project %s webhook as connected", project.id)

    # 记录 Webhook 事件
    event_repo = WebhookEventRepo(db)
    await event_repo.create_from_payload(
        project_id=project.id,
        platform=platform.value,
        event_id=event_id,
        action=action,
        pr_number=pr_number,
        raw_payload=raw_payload,
    )

    return project.id  # type: ignore[no-any-return]


async def _handle_push_event(
    db: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> dict[str, str]:
    """处理 GitHub push 事件。

    提取 head commit 的变更文件，保存 commit 记录并加入评审队列。
    """
    repo_full_name = _extract_repo_full_name(Platform.GITHUB, payload)
    if not repo_full_name:
        return {"status": "ignored", "reason": "no_repo"}

    # 查找项目
    project_repo = ProjectRepo(db)
    domain = _PLATFORM_DOMAINS.get(Platform.GITHUB, "")
    repo_url = f"https://{domain}/{repo_full_name}"
    project = await project_repo.get_by_platform_repo(Platform.GITHUB, repo_url)
    if not project:
        logger.warning("No project found for repo: %s", repo_url)
        return {"status": "ignored", "reason": "no_project"}

    # 标记 webhook 已连接
    if not project.webhook_enabled:
        project.webhook_enabled = True
        await db.flush()
        logger.info("Marked project %s webhook as connected", project.id)

    head_commit: dict[str, Any] = payload.get("head_commit") or {}
    if not head_commit.get("id"):
        return {"status": "ignored", "reason": "no_head_commit"}

    sha: str = head_commit["id"]
    ref: str = payload.get("ref", "")
    branch = ref.replace("refs/heads/", "") if ref.startswith("refs/heads/") else ref

    # 收集变更文件（跳过删除的文件）
    changed_files: list[dict[str, Any]] = []
    for filepath in head_commit.get("added", []):
        changed_files.append({"filename": filepath, "status": "added"})
    for filepath in head_commit.get("modified", []):
        changed_files.append({"filename": filepath, "status": "modified"})

    if not changed_files:
        logger.info("No changed files in push event %s", event_id)
        return {"status": "accepted", "sha": sha}

    # 保存 commit 记录
    commit_repo = CommitRepo(db)
    await commit_repo.create(
        project_id=project.id,
        sha=sha,
        author=head_commit.get("author", {}).get("name"),
        message=head_commit.get("message", ""),
        branch=branch,
        is_reviewed=False,
    )

    # 加入评审队列
    task_id = await enqueue_commit_review(
        project_id=project.id,
        repo_name=repo_full_name,
        sha=sha,
        changed_files=changed_files,
    )

    logger.info(
        "Enqueued commit review: %s@%s task=%s files=%d",
        repo_full_name, sha, task_id, len(changed_files),
    )
    return {"status": "accepted", "sha": sha, "task_id": task_id or ""}


async def _sync_pull_request(
    db: AsyncSession,
    project_id: str,
    platform: Platform,
    pr_data: dict[str, Any],
    _action: str,
) -> None:
    """将 GitHub PR 数据同步到 PullRequestModel。"""
    pr_number = pr_data.get("number")
    if not pr_number:
        return

    repo = PullRequestRepo(db)
    state = "merged" if pr_data.get("merged") else pr_data.get("state", "open")
    merged_at_str = pr_data.get("merged_at")
    merged_at: datetime | None = None
    if merged_at_str:
        with contextlib.suppress(ValueError, TypeError):
            merged_at = datetime.fromisoformat(merged_at_str.replace("Z", "+00:00"))

    await repo.upsert(
        project_id=project_id,
        pr_number=pr_number,
        title=pr_data.get("title", ""),
        author=pr_data.get("user", {}).get("login"),
        source_branch=pr_data.get("head", {}).get("ref"),
        target_branch=pr_data.get("base", {}).get("ref"),
        state=state,
        is_merged=bool(pr_data.get("merged")),
        merged_at=merged_at,
        merge_sha=pr_data.get("merge_commit_sha"),
        platform=platform.value,
    )
    logger.info("Synced PR #%d (%s) for project %s", pr_number, state, project_id)


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
    x_github_delivery: str | None = Header(None),
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitHub Webhook 事件。"""
    raw = await request.body()
    payload: dict[str, Any] = json.loads(raw)
    event_id = x_github_delivery or str(uuid4())

    # 处理 push 事件
    if x_github_event == "push":
        return await _handle_push_event(db, payload, event_id)

    raw_action = payload.get("action", "")

    repo_full_name = _extract_repo_full_name(Platform.GITHUB, payload)
    pr_number = _extract_pr_number(Platform.GITHUB, payload)
    parsed_action = _parse_event_action(Platform.GITHUB, payload)

    if repo_full_name and pr_number:
        project_id = await _ensure_project_connected(
            db=db,
            platform=Platform.GITHUB,
            repo_full_name=repo_full_name,
            event_id=event_id,
            action=parsed_action.value if parsed_action else raw_action,
            pr_number=pr_number,
            raw_payload=raw.decode(),
        )

        # 同步 PR 数据
        pr_data = payload.get("pull_request", {})
        if project_id and pr_data:
            await _sync_pull_request(
                db, project_id, Platform.GITHUB, pr_data, raw_action
            )

    if parsed_action is None or pr_number is None:
        return {"status": "ignored", "reason": "parse_failed"}

    logger.info(
        "Received GitHub webhook: PR #%d action=%s event_id=%s",
        pr_number, parsed_action.value, event_id,
    )
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitlab")
async def gitlab_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 GitLab Webhook 事件。"""
    raw = await request.body()
    payload: dict[str, Any] = json.loads(raw)

    repo_full_name = _extract_repo_full_name(Platform.GITLAB, payload)
    action = _parse_event_action(Platform.GITLAB, payload)
    pr_number = _extract_pr_number(Platform.GITLAB, payload)

    if repo_full_name and pr_number:
        await _ensure_project_connected(
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

    logger.info("Received GitLab webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}


@router.post("/gitee")
async def gitee_webhook(
    request: Request,
    db: AsyncSession = Depends(get_session),
) -> dict[str, str]:
    """接收 Gitee Webhook 事件。"""
    raw = await request.body()
    payload: dict[str, Any] = json.loads(raw)

    repo_full_name = _extract_repo_full_name(Platform.GITEE, payload)
    action = _parse_event_action(Platform.GITEE, payload)
    pr_number = _extract_pr_number(Platform.GITEE, payload)

    if repo_full_name and pr_number:
        await _ensure_project_connected(
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

    logger.info("Received Gitee webhook: PR #%d action=%s", pr_number, action.value)
    return {"status": "accepted", "pr_number": str(pr_number)}
