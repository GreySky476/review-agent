"""PR 管理 API 端点。"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from review_agent.config.database import get_session
from review_agent.repo.commit import CommitRepo
from review_agent.repo.finding import FindingRepo
from review_agent.repo.project import ProjectRepo
from review_agent.repo.pull_request import PullRequestRepo
from review_agent.repo.review import ReviewRepo
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.service.queue import enqueue_pr_review
from review_agent.types.enums import ReviewStatus
from review_agent.types.orm import ReviewModel

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pull-requests"])


@router.get("/projects/{project_id}/pull-requests")
async def list_pull_requests(
    project_id: str,
    state: str | None = Query(None, pattern="^(open|merged|closed)$"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取项目的 PR 列表（含关联的评审状态）。"""
    pr_repo = PullRequestRepo(db)
    review_repo = ReviewRepo(db)

    prs = await pr_repo.list_by_project(
        project_id,
        state=state,
        skip=(page - 1) * page_size,
        limit=page_size,
    )

    # Count total (needs separate query since list_by_project doesn't return count)
    count_filters: dict[str, Any] = {"project_id": project_id}
    if state:
        count_filters["state"] = state
    total = await pr_repo.count(filters=count_filters)

    items = []
    for pr in prs:
        review = await review_repo.get_by_project_pr(project_id, pr.pr_number)
        items.append(
            {
                "pr_number": pr.pr_number,
                "title": pr.title,
                "author": pr.author,
                "state": pr.state,
                "is_merged": pr.is_merged,
                "review_status": review.status if review else None,
                "review_score": review.score if review else None,
                "findings_count": review.findings_count if review else 0,
            }
        )

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/projects/{project_id}/pull-requests/{pr_number}")
async def get_pull_request_detail(
    project_id: str,
    pr_number: int,
    db: AsyncSession = Depends(get_session),
) -> dict[str, Any]:
    """获取 PR 详情（含关联的 Review 和 Findings）。"""
    pr_repo = PullRequestRepo(db)
    review_repo = ReviewRepo(db)

    pr = await pr_repo.get_by_pr_number(project_id, pr_number)
    if pr is None:
        return {
            "pull_request": None,
            "reviews": [],
            "findings": [],
        }

    # 查询 PR 所有 review（按时间升序）
    all_reviews = await review_repo.list_by_pr(project_id, pr_number)

    # 构建 review_by_sha 映射（DB 路径和 GitHub 回退路径共用）
    review_by_sha: dict[str, Any] = {}
    for rv in all_reviews:
        if rv.head_sha:
            review_by_sha[rv.head_sha] = {
                "review_id": rv.id,
                "status": rv.status,
                "score": rv.score,
                "reviewed_files": rv.reviewed_files,
            }

    # 从 commits 表读取 commit 数据（DB 优先，空时回退到 GitHub API）
    commits_data: list[dict[str, Any]] = []
    try:
        commit_records = await CommitRepo(db).list_by_pr(project_id, pr_number)
        if commit_records:
            commit_shas = [c.sha for c in commit_records]

            # 查询 commit 级别（pr_number=None）的 review
            # 使用 asc() 排序：最早创建的先处理，最新创建的覆盖旧记录
            extra_reviews_result = await db.execute(
                select(ReviewModel)
                .where(
                    ReviewModel.project_id == project_id,
                    ReviewModel.head_sha.in_(commit_shas),
                    ReviewModel.is_deleted.is_(False),
                    ReviewModel.pr_number.is_(None),
                )
                .order_by(ReviewModel.create_time.asc())
            )
            all_sha_reviews = list(extra_reviews_result.scalars().all())

            # 合并所有 review，按 head_sha 去重（最新的覆盖旧的）
            for rv in all_sha_reviews:
                if rv.head_sha:
                    review_by_sha[rv.head_sha] = {
                        "review_id": rv.id,
                        "status": rv.status,
                        "score": rv.score,
                        "reviewed_files": rv.reviewed_files,
                    }

            for c in commit_records:
                sha = c.sha
                rv_info = review_by_sha.get(sha, {})
                commits_data.append(
                    {
                        "sha": sha,
                        "message": c.message or "",
                        "author": c.author,
                        "date": c.committed_at.isoformat() if c.committed_at else None,
                        "review_id": rv_info.get("review_id"),
                        "review_status": rv_info.get("status"),
                        "review_score": rv_info.get("score"),
                        "reviewed_files": rv_info.get("reviewed_files"),
                    }
                )
        else:
            # DB 无数据，回退到 GitHub API（首次加载时保证可见）
            logger.debug(
                "No cached commits for PR #%d in project %s, falling back to GitHub API",
                pr_number,
                project_id,
            )
            try:
                project = await ProjectRepo(db).get(project_id)
                if project and project.platform == "github":
                    repo_name = _extract_repo_name(project.repo_url)
                    if repo_name:
                        git = GitHubProvider()
                        pr_commits = await git.get_pr_commits(repo_name, pr_number)
                        # 同样查询 sha-level review
                        fallback_shas = [c["sha"] for c in pr_commits if c.get("sha")]
                        if fallback_shas:
                            extra_fallback = await db.execute(
                                select(ReviewModel)
                                .where(
                                    ReviewModel.project_id == project_id,
                                    ReviewModel.head_sha.in_(fallback_shas),
                                    ReviewModel.is_deleted.is_(False),
                                    ReviewModel.pr_number.is_(None),
                                )
                                .order_by(ReviewModel.create_time.asc())
                            )
                            for rv_extra in list(extra_fallback.scalars().all()):
                                if rv_extra.head_sha:
                                    review_by_sha[rv_extra.head_sha] = {
                                        "review_id": rv_extra.id,
                                        "status": rv_extra.status,
                                        "score": rv_extra.score,
                                        "reviewed_files": rv_extra.reviewed_files,
                                    }
                        for c in pr_commits:
                            sha = c["sha"]
                            rv_info = review_by_sha.get(sha, {})
                            commits_data.append(
                                {
                                    "sha": sha,
                                    "message": c.get("message", ""),
                                    "author": c.get("author"),
                                    "date": c.get("date"),
                                    "review_id": rv_info.get("review_id"),
                                    "review_status": rv_info.get("status"),
                                    "review_score": rv_info.get("score"),
                                    "reviewed_files": rv_info.get("reviewed_files"),
                                }
                            )
                        logger.info(
                            "Fetched %d commits from GitHub API for PR #%d",
                            len(pr_commits),
                            pr_number,
                        )
            except Exception as fb_exc:
                logger.debug("GitHub API fallback failed: %s", fb_exc)
    except Exception:
        logger.debug("Failed to load commits: %s", exc_info=True)

    return {
        "commits": commits_data,
        "pull_request": {
            "pr_number": pr.pr_number,
            "title": pr.title,
            "author": pr.author,
            "source_branch": pr.source_branch,
            "target_branch": pr.target_branch,
            "state": pr.state,
            "is_merged": pr.is_merged,
            "merged_at": pr.merged_at.isoformat() if pr.merged_at else None,
            "platform": pr.platform,
            "create_time": pr.create_time.isoformat() if pr.create_time else None,
        },
        "reviews": [
            {
                "id": rv.id,
                "head_sha": rv.head_sha if rv.head_sha else None,
                "status": rv.status,
                "score": rv.score,
                "findings_count": rv.findings_count,
                "create_time": rv.create_time.isoformat() if rv.create_time else None,
                "reviewed_files": rv.reviewed_files if rv.reviewed_files else None,
            }
            for rv in all_reviews
        ],
        "findings": [],
    }


@router.post("/projects/{project_id}/pull-requests/{pr_number}/sync")
async def sync_pull_request_commits(
    project_id: str,
    pr_number: int,
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """手动同步 PR 的 commit 数据。

    1. 调 GitHub API 获取该 PR 的最新 commits
    2. bulk_upsert 到 commits 表
    3. 返回最新数据 + review 状态
    """
    logger.info("Manual sync triggered: project=%s pr=#%d", project_id, pr_number)

    # 1. 查找项目
    project_repo = ProjectRepo(db)
    project = await project_repo.get(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        return JSONResponse({"status": "rejected", "reason": "project_not_found"}, status_code=404)

    repo_name = _extract_repo_name(project.repo_url)
    if not repo_name:
        logger.warning("Cannot extract repo_name from repo_url: %s", project.repo_url)
        return JSONResponse({"status": "rejected", "reason": "invalid_repo_url"}, status_code=400)

    if project.platform != "github":
        return JSONResponse(
            {"status": "rejected", "reason": f"unsupported_platform: {project.platform}"},
            status_code=400,
        )

    # 2. 调 GitHub API 获取 commits
    try:
        git = GitHubProvider()
        pr_commits = await git.get_pr_commits(repo_name, pr_number)
        if not pr_commits:
            logger.info("No commits found for PR #%d", pr_number)
            return JSONResponse(
                {"status": "completed", "commits": [], "message": "no_commits_found"},
                status_code=200,
            )
    except Exception as exc:
        logger.warning("Failed to fetch commits for PR #%d: %s", pr_number, exc)
        return JSONResponse(
            {"status": "failed", "message": str(exc)},
            status_code=502,
        )

    # 3. bulk_upsert 到 commits 表
    try:
        commit_repo = CommitRepo(db)
        await commit_repo.bulk_upsert(project_id, pr_number, pr_commits)
        await db.commit()
        logger.info(
            "Synced %d commits for PR #%d in project %s",
            len(pr_commits),
            pr_number,
            project_id,
        )
    except Exception as exc:
        logger.warning("Failed to write commits to DB: %s", exc)
        return JSONResponse(
            {"status": "failed", "message": f"db_write_error: {exc}"},
            status_code=500,
        )

    # 4. 读取最新数据并合并 review 状态返回
    commits_data: list[dict[str, Any]] = []
    try:
        review_repo = ReviewRepo(db)
        all_reviews = await review_repo.list_by_pr(project_id, pr_number)
        commit_shas = [c["sha"] for c in pr_commits]

        extra_reviews_result = await db.execute(
            select(ReviewModel)
            .where(
                ReviewModel.project_id == project_id,
                ReviewModel.head_sha.in_(commit_shas),
                ReviewModel.is_deleted.is_(False),
                ReviewModel.pr_number.is_(None),
            )
            .order_by(ReviewModel.create_time.asc())
        )
        all_sha_reviews = list(extra_reviews_result.scalars().all())

        all_for_map = list(all_reviews) + all_sha_reviews
        review_by_sha: dict[str, Any] = {}
        for rv in all_for_map:
            if rv.head_sha:
                review_by_sha[rv.head_sha] = {
                    "review_id": rv.id,
                    "status": rv.status,
                    "score": rv.score,
                    "reviewed_files": rv.reviewed_files,
                }

        for c in pr_commits:
            sha = c["sha"]
            rv_info = review_by_sha.get(sha, {})
            commits_data.append(
                {
                    "sha": sha,
                    "message": c.get("message", ""),
                    "author": c.get("author"),
                    "date": c.get("date"),
                    "review_id": rv_info.get("review_id"),
                    "review_status": rv_info.get("status"),
                    "review_score": rv_info.get("score"),
                    "reviewed_files": rv_info.get("reviewed_files"),
                }
            )
    except Exception as exc:
        logger.debug("Failed to merge review info during sync: %s", exc)

    return JSONResponse({"status": "completed", "commits": commits_data})


@router.post("/projects/{project_id}/pull-requests/{pr_number}/review", response_model=None)
async def trigger_pr_review(
    project_id: str,
    pr_number: int,
    force: bool = Query(False, description="强制重新评审（跳过 SHA 去重）"),
    db: AsyncSession = Depends(get_session),
) -> JSONResponse:
    """手动触发 PR 评审。

    1. 查找项目
    2. 从 GitHub 获取 PR 最新 head SHA
    3. SHA 去重检查（除非 force=true）
    4. 获取变更文件列表
    5. 创建评审记录并加入队列
    """
    logger.info(
        "Manual PR review triggered: project=%s pr=#%d force=%s",
        project_id,
        pr_number,
        force,
    )

    # 1. 查找项目
    project_repo = ProjectRepo(db)
    project = await project_repo.get(project_id)
    if not project:
        logger.warning("Project not found: %s", project_id)
        return JSONResponse({"status": "rejected", "reason": "project_not_found"}, status_code=404)

    repo_name = _extract_repo_name(project.repo_url)
    if not repo_name:
        logger.warning("Cannot extract repo_name from repo_url: %s", project.repo_url)
        return JSONResponse({"status": "rejected", "reason": "invalid_repo_url"}, status_code=400)

    # 2. 从 GitHub 获取 PR 最新 head SHA
    try:
        git = GitHubProvider()
        pr_info = await git.get_pr_info(repo_name, pr_number)
        pr_head_sha = pr_info.head_sha
        logger.info(
            "Fetched PR info: %s#%d head_sha=%s",
            repo_name,
            pr_number,
            pr_head_sha,
        )
    except Exception as exc:
        logger.warning("Failed to fetch PR info for %s#%d: %s", repo_name, pr_number, exc)
        return JSONResponse(
            {"status": "rejected", "reason": f"github_api_failed: {exc}"},
            status_code=502,
        )

    # 3. SHA 去重检查
    force_reuse_review = False
    try:
        review_repo_instance = ReviewRepo(db)
        existing_shas = await review_repo_instance.get_by_head_sha(pr_head_sha)
        if existing_shas:
            if existing_shas.status in (ReviewStatus.COMPLETED, ReviewStatus.COMPLETED_WITH_ERRORS):
                if not force:
                    logger.info(
                        "SHA %s for PR #%d already has completed review %s, skipping"
                        " (use force=true to override)",
                        pr_head_sha[:8],
                        pr_number,
                        existing_shas.id[:8],
                    )
                    return JSONResponse(
                        {"status": "skipped", "reason": "sha_unchanged"},
                        status_code=200,
                    )
            elif existing_shas.status in (ReviewStatus.PENDING, ReviewStatus.RUNNING):
                if not force:
                    logger.info(
                        "SHA %s for PR #%d review in progress, rejecting",
                        pr_head_sha[:8],
                        pr_number,
                    )
                    return JSONResponse(
                        {
                            "status": "rejected",
                            "reason": "review_in_progress",
                            "review_id": existing_shas.id,
                        },
                        status_code=409,
                    )
                # force=true: 复用现有 review 记录，清空旧 findings
                logger.info("Force re-review: reusing existing review %s", existing_shas.id[:8])
                # 更新状态为 PENDING，允许重新入队
                existing_shas.status = ReviewStatus.PENDING
                existing_shas.score = None
                existing_shas.findings_count = 0
                existing_shas.error_message = None
                existing_shas.task_id = None
                force_reuse_review = True
    except Exception:
        logger.debug("Failed to check SHA dedup: %s", exc_info=True)

    # 4. 获取变更文件（全量 diff）
    all_files: list[dict[str, Any]] = []
    try:
        pr_files = await git.get_pr_diff(repo_name, pr_number)
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
            "Fetched PR diff for #%d: %d files (sha=%s)",
            pr_number,
            len(all_files),
            pr_head_sha[:8],
        )
    except Exception as exc:
        logger.warning("Failed to fetch PR diff for %s#%d: %s", repo_name, pr_number, exc)

    if not all_files:
        logger.warning("No changed files for PR #%d@%s", pr_number, repo_name)
        return JSONResponse(
            {"status": "accepted", "task_id": None, "reason": "no_changed_files"},
            status_code=200,
        )

    # 5. 增量上下文：查询上次评审的 reviewed_files
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
                    {"path": f.file_path, "max_severity": f.severity} for f in prev_findings
                ]
            logger.info(
                "Previous review loaded: id=%s sha=%s files=%d",
                prev_review.id,
                last_reviewed_sha[:8] if last_reviewed_sha else "?",
                len(previous_reviewed_files),
            )
    except Exception:
        logger.debug("Failed to load previous review context: %s", exc_info=True)

    # 6. 创建评审记录（force 路径已在第 3 步复用现有 record）
    review_repo = ReviewRepo(db)
    if not force_reuse_review:
        review = await review_repo.create(
            project_id=project_id,
            pr_number=pr_number,
            pr_title=f"PR #{pr_number}",
            head_sha=pr_head_sha,
            status=ReviewStatus.PENDING,
            task_id=None,
        )
        logger.info("Review record created: id=%s pr=#%d", review.id, pr_number)
    else:
        review = existing_shas
        logger.info("Review record reused: id=%s pr=#%d (force mode)", review.id, pr_number)

    # 7. 加入评审队列（PR 增量通道，含 reviewed_files）
    task_id = await enqueue_pr_review(
        project_id=project_id,
        repo_name=repo_name,
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
        "PR review enqueued: project=%s pr=#%d sha=%s task=%s review=%s files=%d"
        " incremental=%s reviewed_files=%d",
        project_id,
        pr_number,
        pr_head_sha[:8],
        task_id,
        review.id,
        len(all_files),
        bool(previous_review_id),
        len(previous_reviewed_files),
    )

    return JSONResponse(
        {
            "status": "accepted",
            "task_id": task_id or "",
            "review_id": review.id,
            "files_count": len(all_files),
        },
        status_code=202,
    )


def _extract_repo_name(repo_url: str) -> str | None:
    """从 repo_url 中提取 owner/repo 格式的仓库名。

    >>> _extract_repo_name("https://github.com/owner/repo")
    "owner/repo"
    >>> _extract_repo_name("https://github.com/owner/repo.git")
    "owner/repo"
    """
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        name = "/".join(parts[-2:])
        return name.removesuffix(".git")
    return None
