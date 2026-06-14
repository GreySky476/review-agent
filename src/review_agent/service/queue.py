"""ARQ 任务队列集成。"""

from __future__ import annotations

import logging
import traceback
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings

from review_agent.config.logging import setup_logging
from review_agent.config.settings import get_settings
from review_agent.service.error_logger import log_error
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
    _ctx: dict[str, Any],
    project_id: str,
    repo_name: str,
    sha: str,
    pr_number: int,
    all_files: list[dict[str, Any]],
    review_id: str = "",
    previous_review_id: str | None = None,
    last_reviewed_sha: str | None = None,
    previous_file_paths: list[str] | None = None,
) -> dict[str, Any]:
    """执行 PR 评审任务（ARQ worker 调用），支持增量。

    与 run_commit_review 的区别：
    - 使用 get_pr_diff 全量 diff 做上下文
    - 支持 previous_file_paths 增量去重
    - 发布 PR Comment 而非 Commit Comment
    - 更新 pull_requests.last_reviewed_sha
    """
    from review_agent.config.database import async_session_factory
    from review_agent.repo.pull_request import PullRequestRepo
    from review_agent.repo.review import ReviewRepo
    from review_agent.types.orm import FindingModel

    _status_completed = ReviewStatus.COMPLETED
    _status_failed = ReviewStatus.FAILED

    try:
        logger.info(
            "Starting PR review #%d for %s@%s (project=%s, incremental=%s)",
            pr_number, repo_name, sha, project_id,
            bool(previous_review_id),
        )
        settings = get_settings()
        git_provider = GitHubProvider(token=settings.github_token)
        ai_provider: Any = None
        if settings.ai_api_key:
            from review_agent.service.ai.deepseek import DeepSeekProvider

            ai_provider = DeepSeekProvider(
                api_key=settings.ai_api_key,
                base_url=settings.ai_base_url,
            )

        # 加载企业自定义规则到知识库
        knowledge_base: Any = None
        try:
            from review_agent.repo.rule import RuleRepo
            from review_agent.service.knowledge.service import KnowledgeBaseService

            async with async_session_factory() as db:
                rule_repo = RuleRepo(db)
                rules = await rule_repo.list_active()
                if rules:
                    knowledge_base = KnowledgeBaseService()
                    rules_data = [
                        {
                            "id": r.id,
                            "name": r.name,
                            "content": r.content,
                            "category": r.category.value,
                            "severity": r.severity.value,
                            "languages": r.languages,
                            "tags": r.tags,
                            "version": r.version,
                            "is_active": r.is_active,
                            "embedding": r.embedding,
                        }
                        for r in rules
                    ]
                    await knowledge_base.load_rules(rules_data)
                    logger.info(
                        "Loaded %d rules into knowledge base for PR #%d",
                        len(rules), pr_number,
                    )
        except Exception:
            logger.warning("Failed to load rules: %s", traceback.format_exc())

        # 转换 changed_files 为 PRFile 对象
        files = [
            PRFile(
                filename=f["filename"],
                status=f.get("status", "modified"),
                additions=f.get("additions", 0),
                deletions=f.get("deletions", 0),
                patch=f.get("patch"),
            )
            for f in all_files
        ]

        if settings.use_langgraph:
            result = await _run_with_langgraph(
                git_provider,
                ai_provider,
                repo_name,
                sha,
                files,
                knowledge_base,
                pr_number=pr_number,
                previous_review_id=previous_review_id,
                last_reviewed_sha=last_reviewed_sha,
                previous_file_paths=previous_file_paths,
            )
        else:
            from review_agent.service.commit_review import CommitReviewService

            service = CommitReviewService(
                git_provider=git_provider,
                ai_provider=ai_provider,
                knowledge_base=knowledge_base,
            )
            result = await service.review_commit(repo_name, sha, files)

        # 发布 PR Comment（增量场景用增量摘要）
        if result.summary_markdown:
            try:
                if previous_review_id:
                    from review_agent.service.publisher import Publisher

                    publisher = Publisher()
                    incremental_summary = publisher.generate_incremental_summary(
                        result.findings, result.score, sha,
                        unreviewed_count=0,
                    )
                    await git_provider.publish_summary_comment(
                        repo_name, pr_number, incremental_summary
                    )
                else:
                    await git_provider.publish_summary_comment(
                        repo_name, pr_number, result.summary_markdown
                    )
                logger.info(
                    "Published PR summary for #%d (%d chars)",
                    pr_number, len(result.summary_markdown),
                )
            except Exception:
                logger.warning(
                    "Failed to publish PR summary for #%d: %s",
                    pr_number, traceback.format_exc(),
                )
                await log_error(
                    error_type="publish_failed",
                    error_message=f"Failed to publish PR summary #{pr_number}",
                    project_id=project_id,
                    review_id=review_id,
                )

        # 更新 ReviewModel 记录
        if review_id:
            try:
                async with async_session_factory() as db:
                    review_repo = ReviewRepo(db)
                    await review_repo.update(
                        review_id,
                        status=result.status.value,
                        score=result.score,
                        findings_count=len(result.findings),
                        error_message=result.error_message,
                    )
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
                    "Failed to update ReviewModel %s: %s",
                    review_id, traceback.format_exc(),
                )
                await log_error(
                    error_type="db_write_failed",
                    error_message=f"Failed to persist review {review_id}",
                    project_id=project_id,
                    review_id=review_id,
                )

        # 更新 PR last_reviewed_sha
        if review_id and pr_number:
            try:
                async with async_session_factory() as db:
                    pr_repo = PullRequestRepo(db)
                    await pr_repo.update_reviewed_sha(
                        project_id, pr_number, sha, review_id
                    )
                    await db.commit()
                    logger.info(
                        "Updated PR #%d last_reviewed_sha=%s", pr_number, sha[:8],
                    )
            except Exception:
                logger.warning(
                    "Failed to update PR last_reviewed_sha: %s",
                    traceback.format_exc(),
                )

        logger.info(
            "PR review #%d completed: %d findings, score=%d",
            pr_number, len(result.findings), result.score,
        )
        return {
            "project_id": project_id,
            "pr_number": pr_number,
            "sha": sha,
            "status": ReviewStatus.COMPLETED.value,
            "findings_count": len(result.findings),
            "score": result.score,
            "review_id": review_id,
        }
    except Exception:
        error_msg = traceback.format_exc()
        logger.error("PR review #%d failed: %s", pr_number, error_msg)
        await log_error(
            error_type="pipeline_crashed",
            error_message=error_msg[:2000],
            project_id=project_id,
            review_id=review_id,
        )
        if review_id:
            try:
                async with async_session_factory() as db:
                    review_repo = ReviewRepo(db)
                    await review_repo.update(review_id, status=_status_failed)
                    await db.commit()
            except Exception:
                logger.warning(
                    "Failed to mark review %s as failed: %s",
                    review_id, traceback.format_exc(),
                )
        return {
            "project_id": project_id,
            "pr_number": pr_number,
            "sha": sha,
            "status": ReviewStatus.FAILED.value,
            "error": f"review_failed: {error_msg[:200]}",
            "review_id": review_id,
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

        # 加载企业自定义规则到知识库
        knowledge_base: Any = None
        try:
            from review_agent.repo.rule import RuleRepo
            from review_agent.service.knowledge.service import KnowledgeBaseService

            async with async_session_factory() as db:
                rule_repo = RuleRepo(db)
                rules = await rule_repo.list_active()
                if rules:
                    knowledge_base = KnowledgeBaseService()
                    rules_data = [
                        {
                            "id": r.id,
                            "name": r.name,
                            "content": r.content,
                            "category": r.category.value,
                            "severity": r.severity.value,
                            "languages": r.languages,
                            "tags": r.tags,
                            "version": r.version,
                            "is_active": r.is_active,
                            "embedding": r.embedding,
                        }
                        for r in rules
                    ]
                    await knowledge_base.load_rules(rules_data)
                    logger.info(
                        "Loaded %d rules into knowledge base for %s@%s",
                        len(rules),
                        repo_name,
                        sha,
                    )
        except Exception:
            logger.warning("Failed to load rules into knowledge base: %s", traceback.format_exc())

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
                knowledge_base,
            )
        else:
            from review_agent.service.commit_review import CommitReviewService

            service = CommitReviewService(
                git_provider=git_provider,
                ai_provider=ai_provider,
                knowledge_base=knowledge_base,
            )
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
                await log_error(
                    error_type="publish_failed",
                    error_message=f"Failed to publish commit summary for {repo_name}@{sha}",
                    project_id=project_id,
                    review_id=review_id,
                )

        # 更新 ReviewModel 记录
        if review_id:
            try:
                async with async_session_factory() as db:
                    review_repo = ReviewRepo(db)
                    await review_repo.update(
                        review_id,
                        status=result.status.value,
                        score=result.score,
                        findings_count=len(result.findings),
                        error_message=result.error_message,
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
                        review_id,
                        result.score,
                        len(result.findings),
                    )
            except Exception:
                logger.warning(
                    "Failed to update ReviewModel %s: %s", review_id, traceback.format_exc()
                )
                await log_error(
                    error_type="db_write_failed",
                    error_message=f"Failed to persist ReviewModel {review_id}",
                    project_id=project_id,
                    review_id=review_id,
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
        await log_error(
            error_type="pipeline_crashed",
            error_message=error_msg[:2000],
            project_id=project_id,
            review_id=review_id,
        )
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
                await log_error(
                    error_type="db_write_failed",
                    error_message=f"Failed to mark review {review_id} as failed",
                    project_id=project_id,
                    review_id=review_id,
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
    "unreviewed_files": [],
    "error_messages": [],
    "pr_number": None,
    "previous_review_id": None,
    "last_reviewed_sha": None,
    "previous_file_paths": [],
    "new_chunks": [],
}


async def _run_with_langgraph(
    git_provider: Any,
    ai_provider: Any,
    repo_name: str,
    sha: str,
    files: list[PRFile],
    knowledge_base: Any = None,
    *,
    pr_number: int | None = None,
    previous_review_id: str | None = None,
    last_reviewed_sha: str | None = None,
    previous_file_paths: list[str] | None = None,
) -> Any:
    """使用 LangGraph 图执行评审（支持 PR 增量）。"""
    from review_agent.service.commit_review import CommitReviewResult
    from review_agent.service.review_graph.graph import build_review_graph

    logger.info(
        "LangGraph pipeline starting: %s@%s files=%d ai=%s knowledge_base=%s",
        repo_name,
        sha,
        len(files),
        "yes" if ai_provider else "no",
        "yes" if knowledge_base else "no",
    )
    graph = build_review_graph(
        git_provider=git_provider,
        ai_provider=ai_provider,
        knowledge_base=knowledge_base,
    )

    initial_state: dict[str, Any] = {
        "repo_name": repo_name,
        "sha": sha,
        "files": files,
        "pr_number": pr_number,
        "previous_review_id": previous_review_id,
        "last_reviewed_sha": last_reviewed_sha,
        "previous_file_paths": previous_file_paths or [],
        **_DEFAULT_STATE,
    }

    thread_id = (
        f"pr:{repo_name}:{pr_number}:{sha[:12]}"
        if pr_number
        else f"{repo_name}:{sha}"
    )
    result_state = await graph.ainvoke(
        initial_state,
        {"configurable": {"thread_id": thread_id}},
    )

    error_msgs = result_state.get("error_messages", [])
    unreviewed = result_state.get("unreviewed_files", [])

    if unreviewed:
        await log_error(
            error_type="pipeline_partial_failure",
            error_message=(
                f"部分文件未完成评审: {', '.join(unreviewed[:10])}"
                f"{'...' if len(unreviewed) > 10 else ''}"
            ),
        )

    return CommitReviewResult(
        findings=result_state.get("deduped_findings", []),
        score=result_state.get("score", 100),
        summary_markdown=result_state.get("summary_markdown", ""),
        status=result_state.get("status", ReviewStatus.COMPLETED),
        error_message="; ".join(error_msgs) if error_msgs else None,
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
        await log_error(
            error_type="queue_enqueue_failed",
            error_message=f"Failed to enqueue PR review for {project_id}#{pr_number}: {exc}",
            project_id=project_id,
        )
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
        await log_error(
            error_type="queue_enqueue_failed",
            error_message=f"Failed to enqueue commit review for {project_id}@{sha}: {exc}",
            project_id=project_id,
        )
        return None


async def enqueue_pr_review(
    project_id: str,
    repo_name: str,
    sha: str,
    pr_number: int,
    all_files: list[dict[str, Any]],
    review_id: str = "",
    previous_review_id: str | None = None,
    last_reviewed_sha: str | None = None,
    previous_file_paths: list[str] | None = None,
) -> str | None:
    """将 PR 评审任务加入队列（含增量上下文）。"""
    try:
        settings = get_settings()
        redis = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
        job = await redis.enqueue_job(
            "run_review",
            project_id,
            repo_name,
            sha,
            pr_number,
            all_files,
            review_id,
            previous_review_id,
            last_reviewed_sha,
            previous_file_paths,
        )
        await redis.close()
        return job.job_id if job else None
    except Exception as exc:
        logger.error("Failed to enqueue PR review job: %s", exc)
        await log_error(
            error_type="queue_enqueue_failed",
            error_message=f"Failed to enqueue PR review for {project_id}#{pr_number}: {exc}",
            project_id=project_id,
        )
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
