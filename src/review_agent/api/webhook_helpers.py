"""Webhook 事件处理辅助函数。"""

from __future__ import annotations

import contextlib
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.commit import CommitRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review
from review_agent.types.enums import EventAction, Platform, ReviewStatus

logger = logging.getLogger(__name__)

_PLATFORM_DOMAINS: dict[Platform, str] = {
    Platform.GITHUB: "github.com",
    Platform.GITLAB: "gitlab.com",
    Platform.GITEE: "gitee.com",
}


async def ensure_project_connected(
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
    if not project.webhook_enabled:
        project.webhook_enabled = True
        await db.flush()
        logger.info("Marked project %s webhook as connected", project.id)
    event_repo = WebhookEventRepo(db)
    await event_repo.create_from_payload(
        project_id=project.id, platform=platform.value, event_id=event_id,
        action=action, pr_number=pr_number, raw_payload=raw_payload,
    )
    return project.id  # type: ignore[no-any-return]


async def handle_push_event(
    db: AsyncSession,
    payload: dict[str, Any],
    event_id: str,
) -> dict[str, str]:
    """处理 GitHub push 事件。"""
    repo_full_name = extract_repo_full_name(Platform.GITHUB, payload)
    if not repo_full_name:
        return {"status": "ignored", "reason": "no_repo"}
    project_repo = ProjectRepo(db)
    domain = _PLATFORM_DOMAINS.get(Platform.GITHUB, "")
    repo_url = f"https://{domain}/{repo_full_name}"
    project = await project_repo.get_by_platform_repo(Platform.GITHUB, repo_url)
    if not project:
        logger.warning("No project found for repo: %s", repo_url)
        return {"status": "ignored", "reason": "no_project"}
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
    changed_files: list[dict[str, Any]] = []
    for filepath in head_commit.get("added", []):
        changed_files.append({"filename": filepath, "status": "added"})
    for filepath in head_commit.get("modified", []):
        changed_files.append({"filename": filepath, "status": "modified"})
    if not changed_files:
        logger.info("No changed files in push event %s", event_id)
        return {"status": "accepted", "sha": sha}
    commit_repo = CommitRepo(db)
    existing = await commit_repo.get_by_sha(project.id, sha)
    if existing:
        existing.is_reviewed = False
        existing.message = head_commit.get("message", "")
        existing.branch = branch
        await db.flush()
        logger.info("Updated existing commit record: %s (resetting is_reviewed)", sha)
    else:
        await commit_repo.create(
            project_id=project.id, sha=sha,
            author=head_commit.get("author", {}).get("name"),
            message=head_commit.get("message", ""), branch=branch, is_reviewed=False,
        )
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project.id, pr_number=None,
        pr_title=f"Push {branch}: {sha[:8]}", head_sha=sha,
        status=ReviewStatus.PENDING, task_id=None,
    )
    task_id = await enqueue_commit_review(
        project_id=project.id, repo_name=repo_full_name, sha=sha,
        changed_files=changed_files, review_id=review.id,
    )
    if task_id:
        review.task_id = task_id
        await db.flush()
    logger.info(
        "Enqueued commit review: %s@%s task=%s files=%d",
        repo_full_name, sha, task_id, len(changed_files),
    )
    return {"status": "accepted", "sha": sha, "task_id": task_id or ""}


async def trigger_pr_review(
    db: AsyncSession,
    project_id: str,
    repo_full_name: str,
    pr_head_sha: str | None,
    pr_number: int,
) -> None:
    """为 PR 事件触发评审。"""
    if not pr_head_sha:
        logger.warning("No head SHA in PR #%d, skipping review", pr_number)
        return
    changed_files: list[dict[str, Any]] = []
    try:
        git = GitHubProvider()
        pr_files = await git.get_commit_diff(repo_full_name, pr_head_sha)
        changed_files = [
            {
                "filename": f.filename, "status": f.status,
                "additions": f.additions, "deletions": f.deletions,
                "patch": f.patch,
            }
            for f in pr_files
        ]
        logger.info(
            "Fetched %d changed files for PR #%d@%s",
            len(changed_files), pr_number, pr_head_sha[:8],
        )
    except Exception as exc:
        logger.warning(
            "Failed to fetch PR #%d diff for %s: %s", pr_number, repo_full_name, exc,
        )
    if not changed_files:
        logger.info("No changed files found for PR #%d, skipping review", pr_number)
        return
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project_id, pr_number=pr_number,
        pr_title=f"PR #{pr_number}", head_sha=pr_head_sha,
        status=ReviewStatus.PENDING, task_id=None,
    )
    task_id = await enqueue_commit_review(
        project_id=project_id, repo_name=repo_full_name,
        sha=pr_head_sha, changed_files=changed_files, review_id=review.id,
    )
    if task_id:
        review.task_id = task_id
        await db.flush()
    logger.info(
        "PR review triggered: project=%s pr=#%d sha=%s review=%s",
        project_id, pr_number, pr_head_sha[:8], review.id,
    )


async def sync_pull_request(
    db: AsyncSession, project_id: str, platform: Platform,
    pr_data: dict[str, Any], _action: str,
) -> None:
    """将 PR 数据同步到 PullRequestModel。"""
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
        project_id=project_id, pr_number=pr_number, title=pr_data.get("title", ""),
        author=pr_data.get("user", {}).get("login"),
        source_branch=pr_data.get("head", {}).get("ref"),
        target_branch=pr_data.get("base", {}).get("ref"),
        state=state, is_merged=bool(pr_data.get("merged")),
        merged_at=merged_at, merge_sha=pr_data.get("merge_commit_sha"),
        platform=platform.value,
    )
    logger.info("Synced PR #%d (%s) for project %s", pr_number, state, project_id)


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """验证 GitHub Webhook 签名。"""
    expected = hmac.new(
        secret.encode("utf-8"), msg=payload, digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(f"sha256={expected}", signature)


def parse_event_action(platform: Platform, body: dict[str, Any]) -> EventAction | None:
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


def extract_repo_full_name(platform: Platform, body: dict[str, Any]) -> str | None:
    """从事件体中提取仓库全名（org/repo）。"""
    if platform == Platform.GITHUB:
        repo: dict[str, Any] = body.get("repository", {})
        return repo.get("full_name")
    if platform in (Platform.GITLAB, Platform.GITEE):
        project_info: dict[str, Any] = body.get("project", {})
        return project_info.get("path_with_namespace")
    return None


def extract_pr_number(platform: Platform, body: dict[str, Any]) -> int | None:
    """从事件体中提取 PR 编号。"""
    if platform == Platform.GITHUB:
        pr: dict[str, Any] = body.get("pull_request", {})
        return pr.get("number")
    if platform in (Platform.GITLAB, Platform.GITEE):
        obj: dict[str, Any] = body.get("object_attributes", {})
        return obj.get("iid")
    return None
