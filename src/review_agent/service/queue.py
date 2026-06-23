"""ARQ 任务队列集成。"""

from __future__ import annotations

import logging
import traceback
from dataclasses import dataclass, field
from typing import Any

from arq import create_pool
from arq.connections import RedisSettings
from redis.asyncio import Redis as aioredis  # noqa: N813

from review_agent.config.logging import setup_logging, setup_opentelemetry
from review_agent.config.settings import get_settings
from review_agent.service.dimensions.base import DimensionFinding
from review_agent.service.error_logger import log_error
from review_agent.service.git.base import PRFile
from review_agent.service.git.github_provider import GitHubProvider
from review_agent.types.enums import ReviewStatus


@dataclass
class _ReviewResult:
    """评审结果（LangGraph 路径使用）。"""

    findings: list[DimensionFinding] = field(default_factory=list)
    score: int = 100
    summary_markdown: str = ""
    status: ReviewStatus = ReviewStatus.COMPLETED
    error_message: str | None = None
    reviewed_files: list[dict[str, str | None]] | None = None
    reviewed_functions: list[dict[str, Any]] | None = None


logger = logging.getLogger(__name__)


async def _worker_startup(_ctx: dict[str, Any]) -> None:
    """ARQ Worker 启动时配置日志和 OTEL（独立进程）。"""
    settings = get_settings()
    setup_logging(level=settings.log_level)
    setup_opentelemetry(
        service_name=settings.otel_service_name,
        endpoint=settings.otel_exporter_otlp_endpoint,
        enabled=settings.otel_enabled,
    )
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
    previous_reviewed_files: list[dict] | None = None,
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

    # ── 分布式锁：防止同一 SHA 被多个 Worker 同时处理 ──
    lock_key = f"lock:review:{project_id}:{sha[:12]}"
    redis_client = None
    try:
        redis_client = await aioredis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
        locked = await redis_client.setnx(lock_key, "1")
        if not locked:
            logger.info("SHA %s already locked by another worker, skipping", sha[:8])
            return {"status": "skipped", "reason": "locked", "sha": sha}
        await redis_client.expire(lock_key, 300)
    except Exception:
        logger.debug("Distributed lock unavailable, proceeding without lock")

    try:
        logger.info(
            "Starting PR review #%d for %s@%s (project=%s, incremental=%s)",
            pr_number,
            repo_name,
            sha,
            project_id,
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
                            "category": r.category,
                            "severity": r.severity,
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
                        len(rules),
                        pr_number,
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
            previous_reviewed_files=previous_reviewed_files,
        )

        # 发布 PR Comment（标记 commit SHA，增量时追评）
        if result.summary_markdown and pr_number:
            try:
                from review_agent.repo.pull_request import PullRequestRepo
                from review_agent.service.publisher import Publisher

                sha_short = sha[:8]
                header = f"> AI 评审针对 commit `{sha_short}`\n\n"
                publisher = Publisher()
                comment_id: int | None = None

                if previous_review_id:
                    # 增量评审：追评到已有评论
                    incremental_summary = publisher.generate_incremental_summary(
                        result.findings,
                        result.score,
                        sha,
                        unreviewed_count=0,
                    )
                    new_content = header + incremental_summary
                    async with async_session_factory() as db:
                        pr_repo = PullRequestRepo(db)
                        pr_record = await pr_repo.get_by_pr_number(project_id, pr_number)
                        existing_cid = pr_record.pr_comment_id if pr_record else None
                        if existing_cid:
                            existing_body = await git_provider.get_issue_comment(
                                repo_name,
                                existing_cid,
                            )
                            if existing_body is not None:
                                updated = existing_body + f"\n\n---\n\n{new_content}"
                                await git_provider.edit_issue_comment(
                                    repo_name,
                                    existing_cid,
                                    updated,
                                )
                            else:
                                comment_id = await git_provider.publish_summary_comment(
                                    repo_name,
                                    pr_number,
                                    new_content,
                                )
                        else:
                            comment_id = await git_provider.publish_summary_comment(
                                repo_name,
                                pr_number,
                                new_content,
                            )
                else:
                    # 首次评审：创建新评论
                    comment_id = await git_provider.publish_summary_comment(
                        repo_name,
                        pr_number,
                        header + result.summary_markdown,
                    )

                # 首次创建时保存 comment_id
                if comment_id:
                    async with async_session_factory() as db:
                        pr_repo = PullRequestRepo(db)
                        await pr_repo.update_pr_comment_id(
                            project_id,
                            pr_number,
                            comment_id,
                        )
                        await db.commit()

                logger.info(
                    "Published PR summary for #%d (%d chars, comment=%s)",
                    pr_number,
                    len(result.summary_markdown),
                    comment_id or "appended",
                )
            except Exception:
                logger.warning(
                    "Failed to publish PR summary for #%d: %s",
                    pr_number,
                    traceback.format_exc(),
                )
                await log_error(
                    error_type="publish_failed",
                    error_message=f"Failed to publish PR summary #{pr_number}",
                    project_id=project_id,
                    review_id=review_id,
                )

        # 单一事务写入所有 DB 操作
        if review_id:
            try:
                async with async_session_factory() as db:
                    # 1. 更新 ReviewModel
                    review_repo = ReviewRepo(db)
                    await review_repo.update(
                        review_id,
                        status=result.status.value,
                        score=result.score,
                        findings_count=len(result.findings),
                        error_message=result.error_message,
                    )
                    if result.reviewed_files is not None:
                        await review_repo.update_reviewed_files(review_id, result.reviewed_files)

                    # 2. 写入 Findings
                    if result.findings:
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

                    # 3. 写入 ReviewFunction records
                    if result.reviewed_functions:
                        from review_agent.repo.review_function import ReviewFunctionRepo

                        func_repo = ReviewFunctionRepo(db)
                        func_items = [
                            {**item, "review_id": review_id} for item in result.reviewed_functions
                        ]
                        await func_repo.bulk_create(func_items)

                    # 4. 更新 PR last_reviewed_sha
                    if pr_number:
                        pr_repo = PullRequestRepo(db)
                        await pr_repo.update_reviewed_sha(project_id, pr_number, sha, review_id)

                    # 5. 同步 commit is_reviewed
                    from review_agent.repo.commit import CommitRepo

                    commit_obj = await CommitRepo(db).get_by_sha(project_id, sha)
                    if commit_obj:
                        commit_obj.is_reviewed = True

                    # 一次性提交
                    await db.commit()
                    logger.info(
                        "Review %s persisted: status=%s score=%d findings=%d",
                        review_id,
                        result.status.value,
                        result.score,
                        len(result.findings),
                    )
            except Exception:
                logger.warning(
                    "Failed to persist review %s: %s",
                    review_id,
                    traceback.format_exc(),
                )
                await log_error(
                    error_type="db_write_failed",
                    error_message=f"Failed to persist review {review_id} (transaction rolled back)",
                    project_id=project_id,
                    review_id=review_id,
                )

        logger.info(
            "PR review #%d completed: %d findings, score=%d",
            pr_number,
            len(result.findings),
            result.score,
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
                    review_id,
                    traceback.format_exc(),
                )
        raise
    finally:
        if redis_client:
            await redis_client.delete(lock_key)
            await redis_client.aclose()


async def run_commit_review(
    _ctx: dict[str, Any],
    project_id: str,
    repo_name: str,
    sha: str,
    changed_files: list[dict[str, Any]],
    review_id: str = "",
    previous_review_id: str | None = None,
    previous_reviewed_files: list[dict] | None = None,
    skip_levels: str = "",
) -> dict[str, Any]:
    """执行 commit 评审任务（ARQ worker 调用）。"""
    from review_agent.config.database import async_session_factory
    from review_agent.repo.review import ReviewRepo
    from review_agent.types.orm import FindingModel

    _status_completed = ReviewStatus.COMPLETED
    _status_failed = ReviewStatus.FAILED

    # ── 分布式锁：防止同一 SHA 被多个 Worker 同时处理 ──
    lock_key = f"lock:review:{project_id}:{sha[:12]}"
    redis_client = None
    try:
        redis_client = await aioredis.from_url(
            get_settings().redis_url, encoding="utf-8", decode_responses=True
        )
        locked = await redis_client.setnx(lock_key, "1")
        if not locked:
            logger.info("SHA %s already locked by another worker, skipping", sha[:8])
            return {"status": "skipped", "reason": "locked", "sha": sha}
        await redis_client.expire(lock_key, 300)
    except Exception:
        logger.debug("Distributed lock unavailable, proceeding without lock")

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
                            "category": r.category,
                            "severity": r.severity,
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

        # webhook 路径的 changed_files 缺少 patch，从 GitHub API 补全
        if not any(f.get("patch") for f in changed_files):
            try:
                commit_files = await git_provider.get_commit_diff(repo_name, sha)
                patch_map = {cf.filename: cf for cf in commit_files}
                for f in changed_files:
                    cf = patch_map.get(f["filename"])
                    if cf:
                        f["patch"] = cf.patch
                        f["additions"] = cf.additions
                        f["deletions"] = cf.deletions
            except Exception:
                logger.warning(
                    "Failed to enrich patches for %s@%s, falling back to full review",
                    repo_name,
                    sha,
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

        result = await _run_with_langgraph(
            git_provider,
            ai_provider,
            repo_name,
            sha,
            files,
            knowledge_base,
            previous_review_id=previous_review_id,
            previous_reviewed_files=previous_reviewed_files,
            skip_levels=skip_levels,
        )

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

        # 单一事务写入所有 DB 操作
        if review_id:
            try:
                async with async_session_factory() as db:
                    # 1. 更新 ReviewModel
                    review_repo = ReviewRepo(db)
                    await review_repo.update(
                        review_id,
                        status=result.status.value,
                        score=result.score,
                        findings_count=len(result.findings),
                        error_message=result.error_message,
                    )

                    # 2. 写入 Findings
                    if result.findings:
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

                    # 3. 写入 ReviewFunction records
                    if result.reviewed_functions:
                        from review_agent.repo.review_function import ReviewFunctionRepo

                        func_repo = ReviewFunctionRepo(db)
                        func_items = [
                            {**item, "review_id": review_id} for item in result.reviewed_functions
                        ]
                        await func_repo.bulk_create(func_items)

                    # 4. 同步 commit is_reviewed
                    from review_agent.repo.commit import CommitRepo

                    commit_obj = await CommitRepo(db).get_by_sha(project_id, sha)
                    if commit_obj:
                        commit_obj.is_reviewed = True

                    # 一次性提交
                    await db.commit()
                    logger.info(
                        "Review %s persisted: status=%s score=%d findings=%d",
                        review_id,
                        result.status.value,
                        result.score,
                        len(result.findings),
                    )
            except Exception:
                logger.warning(
                    "Failed to persist review %s: %s",
                    review_id,
                    traceback.format_exc(),
                )
                await log_error(
                    error_type="db_write_failed",
                    error_message=f"Failed to persist review {review_id} (transaction rolled back)",
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
        raise
    finally:
        if redis_client:
            await redis_client.delete(lock_key)
            await redis_client.aclose()


_DEFAULT_STATE: dict[str, Any] = {
    "target_files": [],
    "chunks": [],
    "source_codes": {},
    "pending_chunk": None,
    "pending_structural_chunks": [],
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
    "previous_reviewed_files": [],
    "previous_reviewed_functions": [],
    "inter_commit_files": [],
    "skip_levels": "",
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
    previous_reviewed_files: list[dict] | None = None,
    skip_levels: str = "",
) -> Any:
    """使用 LangGraph 图执行评审（支持 PR 增量）。"""
    from review_agent.service.review_graph.checkpointer import (
        create_checkpointer,
        create_postgres_checkpointer,
    )
    from review_agent.service.review_graph.graph import build_review_graph

    logger.info(
        "LangGraph pipeline starting: %s@%s files=%d ai=%s knowledge_base=%s",
        repo_name,
        sha,
        len(files),
        "yes" if ai_provider else "no",
        "yes" if knowledge_base else "no",
    )

    # 尝试使用 PostgresSaver（持久化），失败时降级到 MemorySaver
    try:
        saver_cm = create_postgres_checkpointer()
        saver = await saver_cm.__aenter__()
        try:
            await saver.setup()
        except Exception:
            logger.debug("PostgresSaver setup skipped (tables may already exist)")
        _saver_cleanup = lambda: saver_cm.__aexit__(None, None, None)  # noqa: E731
    except Exception:
        logger.info("PostgresSaver unavailable, falling back to MemorySaver")
        saver = create_checkpointer()
        _saver_cleanup = lambda: None  # noqa: E731

    graph = build_review_graph(
        git_provider=git_provider,
        ai_provider=ai_provider,
        knowledge_base=knowledge_base,
        checkpointer=saver,
    )

    # ── 函数级增量数据加载 ────────────────────────────
    # 从 DB 加载 previous_reviewed_functions
    prev_reviewed_functions: list[dict] = []
    if previous_review_id:
        try:
            from review_agent.config.database import async_session_factory
            from review_agent.repo.review_function import ReviewFunctionRepo

            async with async_session_factory() as db:
                func_repo = ReviewFunctionRepo(db)
                func_records = await func_repo.list_by_review(previous_review_id)
                for rec in func_records:
                    prev_reviewed_functions.append(
                        {
                            "file_path": rec.file_path,
                            "function_name": rec.function_name,
                            "start_line": rec.start_line,
                            "end_line": rec.end_line,
                            "max_severity": rec.max_severity,
                            "sha": rec.sha,
                        }
                    )
        except Exception:
            logger.warning(
                "Failed to load previous_reviewed_functions: %s",
                traceback.format_exc(),
            )

    # 加载 inter-commit diff（PR 增量场景，比较 last_reviewed_sha → sha）
    inter_commit_files: list[PRFile] = []
    if last_reviewed_sha and pr_number:
        try:
            inter_commit_files = await git_provider.get_compare_diff(
                repo_name,
                last_reviewed_sha,
                sha,
            )
            logger.info(
                "Loaded inter-commit diff: %s..%s -> %d files",
                last_reviewed_sha[:8],
                sha[:8],
                len(inter_commit_files),
            )
        except Exception:
            logger.warning(
                "Failed to load inter-commit diff: %s",
                traceback.format_exc(),
            )

    initial_state: dict[str, Any] = {
        "repo_name": repo_name,
        "sha": sha,
        "files": files,
        "pr_number": pr_number,
        "previous_review_id": previous_review_id,
        "last_reviewed_sha": last_reviewed_sha,
        "previous_file_paths": previous_file_paths or [],
        "previous_reviewed_files": previous_reviewed_files or [],
        "previous_reviewed_functions": prev_reviewed_functions,
        "inter_commit_files": inter_commit_files,
        "skip_levels": skip_levels,
        **_DEFAULT_STATE,
    }

    thread_id = f"pr:{repo_name}:{pr_number}:{sha[:12]}" if pr_number else f"{repo_name}:{sha}"
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

    # 计算 reviewed_files
    from review_agent.service.utils import compute_reviewed_files, compute_reviewed_functions

    new_chunks = result_state.get("new_chunks", [])
    deduped = result_state.get("deduped_findings", [])
    reviewed_files = compute_reviewed_files(new_chunks, deduped)
    reviewed_functions = compute_reviewed_functions(new_chunks, deduped, sha)

    has_issues = bool(unreviewed) or bool(error_msgs)
    status = ReviewStatus.COMPLETED_WITH_ERRORS if has_issues else ReviewStatus.COMPLETED

    try:
        return _ReviewResult(
            findings=deduped,
            score=result_state.get("score", 100),
            summary_markdown=result_state.get("summary_markdown", ""),
            status=status,
            error_message="; ".join(error_msgs) if error_msgs else None,
            reviewed_files=reviewed_files,
            reviewed_functions=reviewed_functions,
        )
    finally:
        _saver_cleanup()


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
    previous_review_id: str | None = None,
    previous_reviewed_files: list[dict] | None = None,
    skip_levels: str = "",
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
            previous_review_id,
            previous_reviewed_files,
            skip_levels,
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
    previous_reviewed_files: list[dict] | None = None,
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
            previous_reviewed_files,
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


async def sync_project_data(
    _ctx: dict[str, Any],
    project_id: str,
) -> dict[str, Any]:
    """同步单个项目的所有 Open PR 数据（定时任务调用）。"""
    from review_agent.config.database import async_session_factory
    from review_agent.repo.commit import CommitRepo
    from review_agent.repo.project import ProjectRepo

    logger.info("Syncing project data: project_id=%s", project_id)
    try:
        async with async_session_factory() as db:
            project = await ProjectRepo(db).get(project_id)
            if not project:
                return {
                    "project_id": project_id,
                    "status": "skipped",
                    "reason": "project_not_found",
                }

            repo_name = _extract_repo_name_from_url(project.repo_url)
            if not repo_name:
                return {"project_id": project_id, "status": "skipped", "reason": "invalid_repo_url"}

            git = GitHubProvider()
            commit_repo = CommitRepo(db)

            # 列出 Open PR
            open_prs = await git.list_open_prs(repo_name)
            synced = 0
            for pr_data in open_prs:
                pr_number = pr_data["pr_number"]
                pr_commits = await git.get_pr_commits(repo_name, pr_number)
                if pr_commits:
                    await commit_repo.bulk_upsert(project_id, pr_number, pr_commits)
                    synced += 1

            await db.commit()
            logger.info("Synced %d PRs for project %s", synced, project_id)
            return {
                "project_id": project_id,
                "status": "completed",
                "prs_synced": synced,
            }
    except Exception as exc:
        logger.error("Failed to sync project %s: %s", project_id, exc)
        return {"project_id": project_id, "status": "failed", "error": str(exc)}


def _extract_repo_name_from_url(repo_url: str) -> str | None:
    """从 repo_url 提取 owner/repo 格式的仓库名。"""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:]).removesuffix(".git")
    return None


async def _on_job_failure(ctx: dict[str, Any]) -> None:
    """ARQ Job 最终失败回调（所有重试耗尽后调用）。

    记录死信信息到 review_errors 表，供运维排查。
    """
    job_id = ctx.get("job_id", "?")
    function_name = ctx.get("function_name", "?")
    exc_info = ctx.get("exc_info")
    exc_str = str(exc_info[1]) if exc_info and exc_info[1] else "Unknown error"
    args = ctx.get("args", [])
    args_summary = ", ".join(str(a)[:50] for a in args[:3])

    await log_error(
        error_type="arq_job_failed",
        error_message=(
            f"ARQ job {job_id} failed after all retries: "
            f"{function_name}({args_summary}) -> {exc_str}"
        ),
        error_detail=traceback.format_exc() if exc_info else None,
    )
    logger.error(
        "ARQ dead letter: job=%s func=%s args=%s error=%s",
        job_id,
        function_name,
        args_summary,
        exc_str,
    )


class WorkerSettings:
    """ARQ Worker 配置。

    启动方式： uv run arq src.review_agent.service.queue.WorkerSettings
    """

    functions = [run_review, run_commit_review, sync_project_data]
    redis_settings = RedisSettings.from_dsn(get_settings().arq_redis_url)
    keep_result_seconds = 7 * 86400
    keep_result_hours = 7 * 24
    job_retry = get_settings().arq_job_retry
    job_retry_after = get_settings().arq_job_retry_after
    max_jobs = 5
    job_timeout = 600
    on_startup = _worker_startup
    on_failure = _on_job_failure
