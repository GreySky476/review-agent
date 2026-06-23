"""Commit 评审编排服务。

负责接收一次提交的变更文件，依次执行：
1. 代码分块（按函数）
2. 规则检查（全部 chunk 都执行，零成本）
3. AI 评审（仅 normal 大小 chunk）
4. 结构评审（超大 chunk 或边界 chunk）
5. 结果聚合与摘要生成

多文件评审使用 asyncio.gather 并发执行，通过 review_max_concurrency
控制最大并发数以避免 API 限流。
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai_reviewer import AIReviewer
from review_agent.service.chunking import CodeChunk, chunk_file
from review_agent.service.dimensions.base import (
    DimensionFinding,
    review_bug_risk,
    review_code_style,
    review_dependency,
    review_performance,
    review_security,
)
from review_agent.service.dimensions.structure import review_structure
from review_agent.service.error_logger import log_error
from review_agent.service.git.base import GitProvider, PRFile
from review_agent.service.knowledge.service import KnowledgeBaseService
from review_agent.service.publisher import Publisher
from review_agent.service.utils import parse_skip_patterns, should_skip_file
from review_agent.types.enums import ChunkPath, ReviewStatus

logger = logging.getLogger(__name__)


@dataclass
class CommitReviewResult:
    """一次 commit 评审的完整结果。"""

    findings: list[DimensionFinding] = field(default_factory=list)
    score: int = 100
    summary_markdown: str = ""
    status: ReviewStatus = ReviewStatus.COMPLETED
    error_message: str | None = None
    reviewed_files: list[dict[str, str | None]] | None = None


# 边界 Token 常量（与 settings 联动，但提供默认值）
_DETAILED_MAX = 1500
_OVERSIZED_MIN = 2000


class CommitReviewService:
    """Commit 评审编排服务。"""

    def __init__(
        self,
        git_provider: GitProvider,
        ai_provider: AIProvider | None = None,
        knowledge_base: KnowledgeBaseService | None = None,
    ) -> None:
        self._git = git_provider
        self._ai = ai_provider
        self._ai_reviewer = AIReviewer(ai_provider)
        self._knowledge_base = knowledge_base
        self._settings = get_settings()
        self._publisher = Publisher()
        self._skip_patterns = parse_skip_patterns()
        self._semaphore = asyncio.Semaphore(self._settings.review_max_concurrency)

    async def review_commit(
        self,
        repo_name: str,
        sha: str,
        files: list[PRFile],
    ) -> CommitReviewResult:
        """编排一次 commit 的完整评审（文件级并发）。"""
        logger.info(
            "Starting commit review: %s@%s total_files=%d concurrency=%d",
            repo_name,
            sha,
            len(files),
            self._settings.review_max_concurrency,
        )

        # 筛选出需要评审的文件
        target_files = [f for f in files if not should_skip_file(f.filename, self._skip_patterns)]
        skipped = len(files) - len(target_files)
        if skipped:
            logger.info("Skipped %d files by path pattern for %s@%s", skipped, repo_name, sha)

        # 文件级并发：每个文件作为一个独立 task，由 semaphore 控制并发上限
        async def _review_with_semaphore(pr_file: PRFile) -> list[DimensionFinding]:
            async with self._semaphore:
                return await self._review_file(repo_name, sha, pr_file)

        tasks = [_review_with_semaphore(f) for f in target_files]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # 收集结果，过滤异常
        all_findings: list[DimensionFinding] = []
        for f, r in zip(target_files, results, strict=False):
            if isinstance(r, BaseException):
                logger.error("File review failed for %s: %s", f.filename, r)
                continue
            all_findings.extend(r)

        # 聚合去重 + 打分
        deduped, score = self._publisher.aggregate(all_findings)

        logger.info(
            "Review summary for %s@%s: %d raw findings → %d deduped, score=%d",
            repo_name,
            sha,
            len(all_findings),
            len(deduped),
            score,
        )

        # 生成摘要
        summary = self._publisher.generate_summary(deduped, score)

        return CommitReviewResult(
            findings=deduped,
            score=score,
            summary_markdown=summary,
        )

    async def _review_file(
        self,
        repo_name: str,
        sha: str,
        pr_file: PRFile,
    ) -> list[DimensionFinding]:
        """评审单个文件。"""
        # 已删除的文件不需要评审
        if pr_file.status == "removed":
            logger.debug("Skipping removed file: %s", pr_file.filename)
            return []

        source_code = await self._git.get_file_content(repo_name, pr_file.filename, sha)
        if not source_code:
            logger.warning("Failed to fetch content: %s@%s:%s", repo_name, sha, pr_file.filename)
            await log_error(
                error_type="git_file_fetch_failed",
                error_message=(
                    f"Failed to fetch content for review: {repo_name}@{sha}:{pr_file.filename}"
                ),
            )
            return []

        chunks = await chunk_file(pr_file.filename, source_code)

        # 统计 chunk 路径分布
        normal = sum(1 for c in chunks if c.path == ChunkPath.DETAILED_REVIEW)
        oversized = sum(1 for c in chunks if c.path == ChunkPath.STRUCTURAL_REVIEW)
        boundary = len(chunks) - normal - oversized

        logger.info(
            "Reviewing: %s (%d chunks: %d normal, %d oversized, %d boundary)",
            pr_file.filename,
            len(chunks),
            normal,
            oversized,
            boundary,
        )

        findings: list[DimensionFinding] = []

        for chunk in chunks:
            chunk_findings = await self._review_chunk(chunk, pr_file)
            findings.extend(chunk_findings)

        if findings:
            logger.info("  → %s: %d findings", pr_file.filename, len(findings))

        return findings

    async def _review_chunk(
        self,
        chunk: CodeChunk,
        pr_file: PRFile,
    ) -> list[DimensionFinding]:
        """评审单个代码块。"""
        findings: list[DimensionFinding] = []

        # Step 1: 规则检查（所有 chunk 都执行，零成本）
        findings.extend(await review_security(chunk))
        findings.extend(await review_bug_risk(chunk))
        findings.extend(await review_performance(chunk))
        findings.extend(await review_code_style(chunk))
        findings.extend(await review_dependency(chunk))

        # Step 2: RAG 规则检索（仅用于 AI 评审路径）
        matched_rules: list[dict[str, Any]] = []
        if chunk.path == ChunkPath.DETAILED_REVIEW and self._knowledge_base is not None:
            try:
                matched_rules = await self._knowledge_base.search(chunk, top_k=5)
            except Exception:
                logger.warning(
                    "Knowledge base search failed for %s/%s",
                    chunk.file_path,
                    chunk.function_name or "?",
                )

        # Step 3: 根据 chunk 大小决定是否执行 AI/结构评审
        if chunk.path == ChunkPath.DETAILED_REVIEW:
            logger.debug(
                "Chunk %s/%s: detailed AI review path (rules=%d)",
                chunk.file_path,
                chunk.function_name or "?",
                len(matched_rules),
            )
            if self._ai is not None:
                logger.info("  AI review: %s/%s ...", chunk.file_path, chunk.function_name or "?")
                ai_findings = await self._ai_reviewer.review_chunk(
                    chunk,
                    patch=pr_file.patch,
                    matched_rules=matched_rules,
                )
                findings.extend(ai_findings)
        elif chunk.path == ChunkPath.STRUCTURAL_REVIEW:
            logger.debug(
                "Chunk %s/%s: structural review path (oversized)",
                chunk.file_path,
                chunk.function_name or "?",
            )
            structure_findings = await review_structure(chunk)
            findings.extend(structure_findings)
        else:
            logger.debug(
                "Chunk %s/%s: boundary review path",
                chunk.file_path,
                chunk.function_name or "?",
            )
            structure_findings = await review_structure(chunk)
            findings.extend(structure_findings)

        return findings
