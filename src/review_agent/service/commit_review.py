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
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any

from review_agent.config.settings import get_settings
from review_agent.service.ai.base import AIProvider
from review_agent.service.ai.types import AICompletionRequest, AIMessage
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
from review_agent.service.git.base import GitProvider, PRFile
from review_agent.service.publisher import Publisher
from review_agent.types.enums import ChunkPath, FindingCategory, FindingSeverity

logger = logging.getLogger(__name__)


@dataclass
class CommitReviewResult:
    """一次 commit 评审的完整结果。"""

    findings: list[DimensionFinding] = field(default_factory=list)
    score: int = 100
    summary_markdown: str = ""


# 边界 Token 常量（与 settings 联动，但提供默认值）
_DETAILED_MAX = 1500
_OVERSIZED_MIN = 2000


class CommitReviewService:
    """Commit 评审编排服务。"""

    def __init__(
        self,
        git_provider: GitProvider,
        ai_provider: AIProvider | None = None,
    ) -> None:
        self._git = git_provider
        self._ai = ai_provider
        self._settings = get_settings()
        self._publisher = Publisher()
        self._skip_extensions: set[str] = {
            ext.strip() for ext in self._settings.review_skip_extensions.split(",") if ext.strip()
        }
        self._semaphore = asyncio.Semaphore(self._settings.review_max_concurrency)

    async def review_commit(
        self,
        repo_name: str,
        sha: str,
        files: list[PRFile],
    ) -> CommitReviewResult:
        """编排一次 commit 的完整评审（文件级并发）。

        Args:
            repo_name: 仓库全名（如 "owner/repo"）。
            sha: commit SHA。
            files: 该 commit 变更的文件列表。

        Returns:
            评审结果（findings + 分数 + 摘要 markdown）。
        """
        # 筛选出需要评审的文件
        target_files = [f for f in files if not self._should_skip_file(f.filename)]

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

        # 生成摘要
        summary = self._publisher.generate_summary(deduped, score)

        return CommitReviewResult(
            findings=deduped,
            score=score,
            summary_markdown=summary,
        )

    def _should_skip_file(self, filename: str) -> bool:
        """根据文件扩展名判断是否跳过评审。"""
        ext = filename.rsplit(".", 1)[-1] if "." in filename else ""
        return f".{ext}" in self._skip_extensions

    async def _review_file(
        self,
        repo_name: str,
        sha: str,
        pr_file: PRFile,
    ) -> list[DimensionFinding]:
        """评审单个文件。"""
        # 已删除的文件不需要评审
        if pr_file.status == "removed":
            return []

        source_code = await self._git.get_file_content(repo_name, pr_file.filename, sha)
        if not source_code:
            logger.warning("Failed to fetch content: %s@%s:%s", repo_name, sha, pr_file.filename)
            return []

        chunks = await chunk_file(pr_file.filename, source_code)
        findings: list[DimensionFinding] = []

        for chunk in chunks:
            chunk_findings = await self._review_chunk(chunk, pr_file)
            findings.extend(chunk_findings)

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

        # Step 2: 根据 chunk 大小决定是否执行 AI/结构评审
        if chunk.path == ChunkPath.DETAILED_REVIEW:
            # Normal chunk (≤1500 tokens) → AI + 规则
            if self._ai is not None:
                ai_findings = await self._ai_review_chunk(chunk, pr_file)
                findings.extend(ai_findings)
        elif chunk.path == ChunkPath.STRUCTURAL_REVIEW:
            # 超大 chunk (>2000 tokens) → 结构评审 + 规则，跳过 AI
            structure_findings = await review_structure(chunk)
            findings.extend(structure_findings)
        else:
            # 边界 chunk (1500-2000 tokens) → 规则 + 结构评审，跳过 AI
            structure_findings = await review_structure(chunk)
            findings.extend(structure_findings)

        return findings

    async def _ai_review_chunk(
        self,
        chunk: CodeChunk,
        pr_file: PRFile,
    ) -> list[DimensionFinding]:
        """使用 AI 评审单个代码块。

        构造 prompt 包含函数源码 + patch diff，请求 AI 返回结构化 findings。
        """
        if self._ai is None:
            return []

        # 构建 prompt
        system_prompt = (
            "你是一位资深代码评审专家。请审查下方的代码变更，"
            "找出其中的正确性缺陷、安全风险、错误处理遗漏和逻辑错误。\n\n"
            "以 JSON 数组格式返回结果，不要包含其他内容：\n"
            '```json\n'
            '[\n'
            '  {\n'
            '    "severity": "critical|warning|info",\n'
            '    "title": "简短标题",\n'
            '    "description": "问题详细描述",\n'
            '    "suggestion": "修复建议",\n'
            '    "line": <行号或 null>\n'
            '  }\n'
            ']\n'
            '```\n'
            "如果没有发现问题，返回空数组 []。"
        )

        # 构建用户 prompt：函数代码 + diff
        user_parts = [f"## 函数源码（{chunk.file_path}）\n```\n{chunk.source_code}\n```"]
        if pr_file.patch:
            user_parts.append(f"## Diff\n```diff\n{pr_file.patch}\n```")
        user_prompt = "\n\n".join(user_parts)

        request = AICompletionRequest(
            model=self._settings.ai_model_name,
            messages=[
                AIMessage(role="system", content=system_prompt),
                AIMessage(role="user", content=user_prompt),
            ],
            temperature=0.1,
            max_tokens=2048,
            timeout_seconds=self._settings.ai_request_timeout,
        )

        try:
            response = await self._ai.complete(request)
            return self._parse_ai_response(response.content, chunk)
        except Exception as exc:
            logger.warning(
                "AI review failed for %s:%s: %s",
                chunk.file_path,
                chunk.function_name,
                exc,
            )
            return []

    def _parse_ai_response(self, content: str, chunk: CodeChunk) -> list[DimensionFinding]:
        """从 AI 响应中解析 findings。

        支持两种格式：
        1. 被 ```json ... ``` 包裹的 JSON
        2. 纯 JSON 数组
        """
        # 尝试提取 JSON 块
        json_match = re.search(r"```(?:json)?\s*(\[[\s\S]*?\])\s*```", content)
        json_str = json_match.group(1) if json_match else content.strip()

        # 尝试解析为 JSON
        try:
            raw_findings: list[dict[str, Any]] = json.loads(json_str)
        except json.JSONDecodeError:
            # 如果内容本身就是一个 JSON 数组（没有 markdown 包裹）
            try:
                raw_findings = json.loads(content.strip())
            except json.JSONDecodeError:
                logger.warning("Failed to parse AI response as JSON: %.100s", content)
                return []

        if not isinstance(raw_findings, list):
            return []

        findings: list[DimensionFinding] = []
        for item in raw_findings:
            if not isinstance(item, dict):
                continue
            severity_str = item.get("severity", "info")
            severity = {
                "critical": FindingSeverity.CRITICAL,
                "warning": FindingSeverity.WARNING,
                "info": FindingSeverity.INFO,
            }.get(severity_str, FindingSeverity.INFO)

            findings.append(
                DimensionFinding(
                    category=FindingCategory.BUG,
                    severity=severity,
                    title=item.get("title", "未命名问题"),
                    description=item.get("description", ""),
                    suggestion=item.get("suggestion", ""),
                    file_path=chunk.file_path,
                    line_start=item.get("line"),
                )
            )

        return findings
