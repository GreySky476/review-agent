"""Webhook 事件处理辅助函数。"""

from __future__ import annotations

import contextlib
import fnmatch
import hashlib
import hmac
import logging
from datetime import datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.repo.commit import CommitRepo
from review_agent.repo.finding import FindingRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.repo.webhook_event import WebhookEventRepo
from review_agent.service.error_logger import log_error
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_commit_review, enqueue_pr_review
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
        await log_error(
            error_type="webhook_parse_failed",
            error_message=f"No project matching repo_url: {repo_url}",
        )
        return None
    if not project.webhook_enabled:
        project.webhook_enabled = True
        await db.flush()
        logger.info("Marked project %s webhook as connected", project.id)
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

    # 检查分支是否在项目的评审分支列表中
    allowed = await project_repo.get_review_branches(project.id)
    if not any(fnmatch.fnmatch(branch, pattern) for pattern in allowed):
        logger.info(
            "Skipped push review: branch='%s' not in review list %s (project=%s)",
            branch,
            allowed,
            project.id,
        )
        return {"status": "skipped", "reason": "branch_not_matched", "branch": branch}

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

    # 解析 commit 作者时间
    raw_timestamp = head_commit.get("timestamp")
    committed_at: datetime | None = None
    if raw_timestamp:
        with contextlib.suppress(ValueError, TypeError):
            committed_at = datetime.fromisoformat(raw_timestamp)

    if existing:
        existing.is_reviewed = False
        existing.message = head_commit.get("message", "")
        existing.branch = branch
        if committed_at:
            existing.committed_at = committed_at
        await db.flush()
        logger.info("Updated existing commit record: %s (resetting is_reviewed)", sha)
    else:
        await commit_repo.create(
            project_id=project.id,
            sha=sha,
            author=head_commit.get("author", {}).get("name"),
            message=head_commit.get("message", ""),
            branch=branch,
            is_reviewed=False,
            committed_at=committed_at,
        )
    review_repo = ReviewRepo(db)
    review = await review_repo.create(
        project_id=project.id,
        pr_number=None,
        pr_title=f"Push {branch}: {sha[:8]}",
        head_sha=sha,
        status=ReviewStatus.PENDING,
        task_id=None,
    )
    task_id = await enqueue_commit_review(
        project_id=project.id,
        repo_name=repo_full_name,
        sha=sha,
        changed_files=changed_files,
        review_id=review.id,
    )
    if task_id:
        review.task_id = task_id
        await db.flush()
    logger.info(
        "Enqueued commit review: %s@%s task=%s files=%d",
        repo_full_name,
        sha,
        task_id,
        len(changed_files),
    )
    return {"status": "accepted", "sha": sha, "task_id": task_id or ""}


async def trigger_pr_review(
    db: AsyncSession,
    project_id: str,
    repo_full_name: str,
    pr_head_sha: str | None,
    pr_number: int,
) -> None:
    """为 PR 事件触发评审（含增量上下文）。"""
    if not pr_head_sha:
        logger.warning("trigger_pr_review: no head SHA for PR #%d", pr_number)
        return
    all_files: list[dict[str, Any]] = []

    # 查 PR 真实标题
    pr_title = f"PR #{pr_number}"
    try:
        pr_record = await PullRequestRepo(db).get_by_pr_number(project_id, pr_number)
        if pr_record and pr_record.title:
            pr_title = pr_record.title
    except Exception:
        logger.debug("trigger_pr_review: failed to load PR title", exc_info=True)

    # SHA 去重检查（只拦截已完成评审的 SHA，失败/进行中不拦截）
    try:
        existing = await ReviewRepo(db).get_completed_by_sha(
            project_id, pr_number, pr_head_sha
        )
        if existing:
            logger.info(
                "SHA %s for PR #%d already has completed review %s, skipping webhook",
                pr_head_sha[:8], pr_number, existing.id[:8],
            )
            return
    except Exception:
        logger.debug("Failed to check SHA dedup: %s", exc_info=True)

    try:
        git = GitHubProvider()
        pr_files = await git.get_pr_diff(repo_full_name, pr_number)
        all_files = [
            {
                "filename": f.filename,
                "status": f.status,
                "additions": f.additions,
                "deletions": f.deletions,
                "patch": f.patch,
            }
            for f in pr_files
        ]
        logger.info(
            "trigger_pr_review: PR #%d diff fetched: %d files sha=%s",
            pr_number,
            len(all_files),
            pr_head_sha[:8],
        )
    except Exception as exc:
        logger.warning("trigger_pr_review: failed to fetch diff for PR #%d: %s", pr_number, exc)
        await log_error(
            error_type="git_api_failed",
            error_message=f"trigger_pr_review: failed to fetch PR #{pr_number} diff: {exc}",
        )

    # 查询上次评审记录，构建增量上下文
    previous_review_id: str | None = None
    last_reviewed_sha: str | None = None
    previous_file_paths: list[str] = []
    previous_reviewed_files: list[dict] = []
    try:
        prev_review = await ReviewRepo(db).get_latest_completed_by_pr(project_id, pr_number)
        if prev_review:
            previous_review_id = prev_review.id
            last_reviewed_sha = prev_review.head_sha
            # 优先使用 reviewed_files（新数据）
            if prev_review.reviewed_files:
                previous_reviewed_files = prev_review.reviewed_files
                previous_file_paths = [f["path"] for f in prev_review.reviewed_files if "path" in f]
            else:
                # 兼容旧数据：从 findings 推导
                prev_findings = await FindingRepo(db).list_by_review(prev_review.id)
                previous_file_paths = list({f.file_path for f in prev_findings})
                previous_reviewed_files = [
                    {"path": f.file_path, "max_severity": f.severity}
                    for f in prev_findings
                ]
            logger.info(
                "trigger_pr_review: previous review found: id=%s sha=%s files=%d",
                prev_review.id,
                last_reviewed_sha[:8] if last_reviewed_sha else "?",
                len(previous_reviewed_files),
            )
    except Exception:
        logger.debug("trigger_pr_review: failed to load previous review context", exc_info=True)

    # 创建评审记录
    review_repo = ReviewRepo(db)
    review_status = ReviewStatus.PENDING if all_files else ReviewStatus.FAILED
    review = await review_repo.create(
        project_id=project_id,
        pr_number=pr_number,
        pr_title=pr_title,
        head_sha=pr_head_sha,
        status=review_status,
        task_id=None,
    )
    logger.info(
        "trigger_pr_review: review created: id=%s status=%s pr_title='%s'",
        review.id,
        review_status.value,
        pr_title,
    )

    # 没有文件 → 标记失败后直接返回
    if not all_files:
        logger.warning(
            "trigger_pr_review: no files for PR #%d, review %s marked failed",
            pr_number,
            review.id,
        )
        await db.flush()
        return

    # 入队
    task_id = await enqueue_pr_review(
        project_id=project_id,
        repo_name=repo_full_name,
        sha=pr_head_sha,
        pr_number=pr_number,
        all_files=all_files,
        review_id=review.id,
        previous_review_id=previous_review_id,
        last_reviewed_sha=last_reviewed_sha,
        previous_file_paths=previous_file_paths,
        previous_reviewed_files=previous_reviewed_files,
    )
    if task_id:
        review.task_id = task_id
        await db.flush()
        logger.info(
            "trigger_pr_review: enqueued: pr=#%d review=%s task=%s files=%d incr=%s",
            pr_number,
            review.id,
            task_id,
            len(all_files),
            bool(previous_review_id),
        )
    else:
        logger.warning(
            "trigger_pr_review: enqueue failed for PR #%d review=%s (Redis down?)",
            pr_number,
            review.id,
        )


async def sync_pull_request(
    db: AsyncSession,
    project_id: str,
    platform: Platform,
    pr_data: dict[str, Any],
    _action: str,
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


def verify_github_signature(payload: bytes, signature: str, secret: str) -> bool:
    """验证 GitHub Webhook 签名。"""
    expected = hmac.new(
        secret.encode("utf-8"),
        msg=payload,
        digestmod=hashlib.sha256,
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
