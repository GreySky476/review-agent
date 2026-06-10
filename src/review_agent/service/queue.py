"""ARQ 任务队列集成。"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from review_agent.config.logging import setup_logging
from review_agent.config.settings import get_settings
from review_agent.service.git.base import PRFile
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.types.enums import ReviewStatus

logger = logging.getLogger(__name__)


async def _worker_startup(_ctx: dict[str, Any]) -> None:
    """ARQ Worker 启动时配置日志（独立进程，默认日志级别为 WARNING）。"""
    settings = get_settings()
    setup_logging(level=settings.log_level)
    logger.info("ARQ worker started: log_level=%s", settings.log_level)


async def run_review(
    _ctx: dict[str, Any], project_id: str, pr_number: int, _head_sha: str
) -> dict[str, Any]:
    """执行 PR 评审任务（ARQ worker 调用）。"""
    try:
        logger.info("Starting review for PR #%d (project=%s)", pr_number, project_id)
        # TODO: 实际 PR 评审逻辑
        return {
            "project_id": project_id,
            "pr_number": pr_number,
            "status": ReviewStatus.COMPLETED.value,
            "findings_count": 0,
        }
    except Exception:
        error_msg = traceback.format_exc()
        logger.error("Review failed for PR #%d (project=%s): %s", pr_number, project_id, error_msg)
        # TODO: 写入 ReviewErrorLog（需要 DB session）
        return {
            "project_id": project_id,
            "pr_number": pr_number,
            "status": ReviewStatus.FAILED.value,
            "error": f"ai_call_failed: {error_msg[:200]}",
        }


async def run_commit_review(
    _ctx: dict[str, Any],
    project_id: str,
    repo_name: str,
    sha: str,
    changed_files: list[dict[str, Any]],
    review_id: str = "",
) -> dict[str, Any]:
    """执行 commit 评审任务（ARQ worker 调用）。"""
    from review_agent.config.database import async_session_factory
    from review_agent.repo.review import ReviewRepo
    from review_agent.types.orm import FindingModel

    _status_completed = ReviewStatus.COMPLETED
    _status_failed = ReviewStatus.FAILED

    try:
        logger.info("Starting commit review for %s@%s (project=%s)", repo_name, sha, project_id)
        settings = get_settings()
        git_provider = GitHubProvider(token=settings.github_token)
        ai_provider: Any = None
        if settings.ai_api_key:
            from review_agent.service.ai.deepseek import DeepSeekProvider

            ai_provider = DeepSeekProvider(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            )

        # 转换 changed_files 为 PRFile 对象
        files = [
            PRFile(
                filename=f["filename"],
                status=f.get("status", "modified"),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            )
            for f in changed_files
        ]

        if settings.use_langgraph:
            result = await _run_with_langgraph(
                git_provider,
                ai_provider,
                repo_name,
                sha,
                files,
            )
        else:
            from review_agent.service.commit_review import CommitReviewService

            service = CommitReviewService(git_provider=git_provider, ai_provider=ai_provider)
            result = await service.review_commit(repo_name, sha, files)

        # 发布摘要评论到 GitHub（失败不影响评审结果）
        if result.summary_markdown:
            try:
                await git_provider.publish_commit_summary(repo_name, sha, result.summary_markdown)
                logger.info(
                    "Published commit summary for %s@%s (%d chars)",
                    repo_name,
                    sha,
                    len(result.summary_markdown),
                )
            except Exception:
                logger.warning(
                    "Failed to publish commit summary for %s@%s: %s",
                    repo_name,
                    sha,
                    traceback.format_exc(),
                )

        # 更新 ReviewModel 记录
        if review_id:
            try:
                async with async_session_factory() as db:
                    review_repo = ReviewRepo(db)
                    await review_repo.update(
                        review_id,
                        status=_status_completed,
                        score=result.score,
                        findings_count=len(result.findings),
                    )
                    # 创建 FindingModel 记录
                    for finding in result.findings:
                        finding_record = FindingModel(
                            review_id=review_id,
                            file_path=finding.file_path,
                            line_start=finding.line_start,
                            line_end=finding.line_end,
                            category=finding.category,
                            severity=finding.severity,
                            title=finding.title,
                            description=finding.description,
                            suggestion=finding.suggestion,
                            rule_id=finding.rule_id,
                        )
                        db.add(finding_record)
                    await db.commit()
                    logger.info(
                        "ReviewModel updated: id=%s status=completed score=%d findings=%d",
                        review_id, result.score, len(result.findings),
                    )
            except Exception:
                logger.warning(
                    "Failed to update ReviewModel %s: %s", review_id, traceback.format_exc()
                )

        logger.info(
            "Commit review completed for %s@%s: %d findings, score=%d",
            repo_name,
            sha,
            len(result.findings),
            result.score,
        )
        return {
            "project_id": project_id,
            "sha": sha,
            "status": ReviewStatus.COMPLETED.value,
            "findings_count": len(result.findings),
            "score": result.score,
            "review_id": review_id,
        }
    except Exception:
        error_msg = traceback.format_exc()
        logger.error("Commit review failed for %s@%s: %s", repo_name, sha, error_msg)
        # 更新 ReviewModel 为 failed
        if review_id:
            try:
                async with async_session_factory() as db:
                    review_repo = ReviewRepo(db)
                    await review_repo.update(review_id, status=_status_failed)
                    await db.commit()
                    logger.info("ReviewModel %s marked as failed", review_id)
            except Exception:
                logger.warning(
                    "Failed to mark review %s as failed: %s", review_id, traceback.format_exc()
                )
        return {
            "project_id": project_id,
            "sha": sha,
            "status": ReviewStatus.FAILED.value,
            "error": f"review_failed: {error_msg[:200]}",
            "review_id": review_id,
        }


_DEFAULT_STATE: dict[str, Any] = {
    "target_files": [],
    "chunks": [],
    "source_codes": {},
    "pending_chunk": None,
    "rule_findings": [],
    "ai_findings": [],
    "structural_findings": [],
    "all_findings": [],
    "deduped_findings": [],
    "score": 100,
    "summary_markdown": "",
    "error": None,
    "status": ReviewStatus.RUNNING,
}


async def _run_with_langgraph(
    git_provider: Any,
    ai_provider: Any,
    repo_name: str,
    sha: str,
    files: list[PRFile],
) -> Any:
    """使用 LangGraph 图执行评审。"""
    from review_agent.service.commit_review import CommitReviewResult
    from review_agent.service.review_graph.graph import build_review_graph

    logger.info(
        "LangGraph pipeline starting: %s@%s files=%d ai=%s",
        repo_name,
        sha,
        len(files),
        "yes" if ai_provider else "no",
    )
    graph = build_review_graph(git_provider=git_provider, ai_provider=ai_provider)

    initial_state: dict[str, Any] = {
        "repo_name": repo_name,
        "sha": sha,
        "files": files,
        **_DEFAULT_STATE,
    }

    result_state = await graph.ainvoke(
        initial_state,
        {"configurable": {"thread_id": f"{repo_name}:{sha}"}},
    )

    return CommitReviewResult(
        findings=result_state.get("deduped_findings", []),
        score=result_state.get("score", 100),
        summary_markdown=result_state.get("summary_markdown", ""),
    )


async def enqueue_review(project_id: str, pr_number: int, head_sha: str) -> str | None:
    """将 PR 评审任务加入队列。"""
    try:
        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
        job = await redis.enqueue_job("run_review", project_id, pr_number, head_sha)
        await redis.close()
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue review job: %s", exc)
        return None


async def enqueue_commit_review(
    project_id: str,
    repo_name: str,
    sha: str,
    changed_files: list[dict[str, Any]],
    review_id: str = "",
) -> str | None:
    """将 commit 评审任务加入队列。"""
    try:
        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
        job = await redis.enqueue_job(
            "run_commit_review",
            project_id,
            repo_name,
            sha,
            changed_files,
            review_id,
        )
        await redis.close()
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue commit review job: %s", exc)
        return None


class WorkerSettings:
    """ARQ Worker 配置。

    启动方式： uv run arq src.review_agent.service.queue.WorkerSettings
    """

    functions = [run_review, run_commit_review]
    redis_settings = RedisSettings.from_dsn(get_settings().arq_redis_url)
    keep_result_seconds = 7 * 86400
    keep_result_hours = 7 * 24
    on_startup = _worker_startup
