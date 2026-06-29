"""Integration tests for ARQ queue operations.

Tests cover: enqueue_pr_review, enqueue_commit_review, and error handling.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest


@pytest.mark.asyncio
@pytest.mark.integration
class TestEnqueuePrReview:
    """PR 评审入队测试。"""

    async def test_enqueue_pr_review_returns_task_id(self) -> None:
        """enqueue_pr_review 成功时应返回 task_id。"""
        from review_agent.service.queue import enqueue_pr_review

        mock_job = MagicMock()
        mock_job.job_id = "task-abc-123"

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_redis = MagicMock()
            mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
            mock_redis.close = AsyncMock()
            mock_create_pool.return_value = mock_redis

            task_id = await enqueue_pr_review(
                project_id="proj-1",
                repo_name="test/repo",
                sha="abc123def456789",
                pr_number=42,
                all_files=[{"filename": "main.py", "status": "modified", "patch": "..."}],
                review_id="review-1",
            )

            assert task_id == "task-abc-123"
            mock_redis.enqueue_job.assert_awaited_once()
            mock_redis.close.assert_awaited_once()

    async def test_enqueue_pr_review_with_incremental_context(self) -> None:
        """带增量上下文的 enqueue_pr_review 应正确传递参数。"""
        from review_agent.service.queue import enqueue_pr_review

        mock_job = MagicMock()
        mock_job.job_id = "task-inc-456"

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_redis = MagicMock()
            mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
            mock_redis.close = AsyncMock()
            mock_create_pool.return_value = mock_redis

            task_id = await enqueue_pr_review(
                project_id="proj-2",
                repo_name="test/repo",
                sha="def456789abc",
                pr_number=99,
                all_files=[{"filename": "lib.py", "status": "added", "patch": "+new code"}],
                review_id="review-2",
                previous_review_id="prev-review-1",
                last_reviewed_sha="abc123def456",
                previous_file_paths=["main.py"],
                previous_reviewed_files=[{"filename": "main.py", "reviewed": True}],
            )

            assert task_id == "task-inc-456"
            # Verify enqueue_job was called with the incremental parameters
            call_args = mock_redis.enqueue_job.call_args
            assert call_args[0][0] == "run_review"
            assert call_args[0][1] == "proj-2"  # project_id
            assert call_args[0][2] == "test/repo"  # repo_name
            assert call_args[0][3] == "def456789abc"  # sha
            assert call_args[0][4] == 99  # pr_number

    async def test_enqueue_pr_review_handles_failure(self) -> None:
        """当 Redis 不可用时，enqueue_pr_review 应返回 None。"""
        from review_agent.service.queue import enqueue_pr_review

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_create_pool.side_effect = RuntimeError("Connection refused")

            task_id = await enqueue_pr_review(
                project_id="proj-3",
                repo_name="test/repo",
                sha="fail1234567",
                pr_number=1,
                all_files=[],
            )

            assert task_id is None


@pytest.mark.asyncio
@pytest.mark.integration
class TestEnqueueCommitReview:
    """Commit 评审入队测试。"""

    async def test_enqueue_commit_review_returns_task_id(self) -> None:
        """enqueue_commit_review 成功时应返回 task_id。"""
        from review_agent.service.queue import enqueue_commit_review

        mock_job = MagicMock()
        mock_job.job_id = "task-commit-789"

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_redis = MagicMock()
            mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
            mock_redis.close = AsyncMock()
            mock_create_pool.return_value = mock_redis

            task_id = await enqueue_commit_review(
                project_id="proj-1",
                repo_name="test/repo",
                sha="abc123def456",
                changed_files=[
                    {"filename": "app.py", "status": "modified", "patch": "@@ -1 +1 @@"}
                ],
                review_id="review-commit-1",
            )

            assert task_id == "task-commit-789"
            mock_redis.enqueue_job.assert_awaited_once()
            mock_redis.close.assert_awaited_once()

    async def test_enqueue_commit_review_with_skip_levels(self) -> None:
        """带 skip_levels 的 commit review 入队。"""
        from review_agent.service.queue import enqueue_commit_review

        mock_job = MagicMock()
        mock_job.job_id = "task-skip-999"

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_redis = MagicMock()
            mock_redis.enqueue_job = AsyncMock(return_value=mock_job)
            mock_redis.close = AsyncMock()
            mock_create_pool.return_value = mock_redis

            task_id = await enqueue_commit_review(
                project_id="proj-2",
                repo_name="test/repo",
                sha="skip1234567",
                changed_files=[
                    {"filename": "old.py", "status": "modified", "patch": "@@ -5 +5 @@"}
                ],
                review_id="review-skip-1",
                skip_levels="style,performance",
            )

            assert task_id == "task-skip-999"
            call_args = mock_redis.enqueue_job.call_args
            assert call_args[0][0] == "run_commit_review"

    async def test_enqueue_commit_review_handles_failure(self) -> None:
        """当 Redis 不可用时，enqueue_commit_review 应返回 None。"""
        from review_agent.service.queue import enqueue_commit_review

        with (
            patch(
                "review_agent.service.queue.create_pool",
                new_callable=AsyncMock,
            ) as mock_create_pool,
        ):
            mock_create_pool.side_effect = RuntimeError("Connection refused")

            task_id = await enqueue_commit_review(
                project_id="proj-fail",
                repo_name="test/repo",
                sha="fail9999999",
                changed_files=[{"filename": "doomed.py", "status": "modified"}],
            )

            assert task_id is None
