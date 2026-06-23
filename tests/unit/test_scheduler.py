"""Tests for recovery scheduler."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from review_agent.service.scheduler import _recovery_loop, start_recovery_scheduler


class TestStartRecoveryScheduler:
    def test_starts_background_task(self) -> None:
        """start_recovery_scheduler 应启动后台协程。"""
        with patch("review_agent.service.scheduler.asyncio.create_task") as mock_create:
            start_recovery_scheduler(interval_minutes=5)
            mock_create.assert_called_once()

    def test_does_not_start_twice(self) -> None:
        """重复调用不应创建第二个任务。"""
        import review_agent.service.scheduler as sched

        sched._recovery_task = MagicMock()
        sched._recovery_task.done.return_value = False

        with patch("review_agent.service.scheduler.asyncio.create_task") as mock_create:
            start_recovery_scheduler(interval_minutes=5)
            mock_create.assert_not_called()


class TestRecoveryLoop:
    """_recovery_loop 内部逻辑的集成测试（mock 外部依赖）。"""

    @pytest.mark.asyncio
    async def test_recovery_cycle_with_stale_reviews(self) -> None:
        """有超时评审时，应标记为 FAILED 并记录错误日志。"""
        stale_mock = MagicMock()
        stale_mock.id = "review-test-1"
        stale_mock.project_id = "proj-1"
        stale_mock.status.value = "PENDING"
        stale_mock.create_time.isoformat.return_value = "2026-06-23T00:00:00"

        mock_repo = MagicMock()
        mock_repo.list_stale = AsyncMock(return_value=[stale_mock])
        mock_repo.batch_mark_failed = AsyncMock(return_value=1)

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session
        mock_session.commit = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.stale_review_timeout_minutes = 30

        with (
            patch("review_agent.config.database.async_session_factory") as mock_factory,
            patch("review_agent.config.settings.get_settings", return_value=mock_settings),
            patch("review_agent.repo.review.ReviewRepo", return_value=mock_repo),
            patch("review_agent.service.error_logger.log_error", new_callable=AsyncMock),
            patch(
                "review_agent.service.scheduler.asyncio.sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            mock_factory.return_value = mock_session

            with pytest.raises(KeyboardInterrupt):
                await _recovery_loop(interval_seconds=60)

            mock_repo.list_stale.assert_awaited_once()
            mock_repo.batch_mark_failed.assert_awaited_once_with(
                ["review-test-1"],
                error_message="Auto-recovered: review timeout exceeded",
            )
            mock_session.commit.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_recovery_cycle_no_stale(self) -> None:
        """无超时评审时不应调用 batch_mark_failed。"""
        mock_repo = MagicMock()
        mock_repo.list_stale = AsyncMock(return_value=[])
        mock_repo.batch_mark_failed = AsyncMock()

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session

        mock_settings = MagicMock()
        mock_settings.stale_review_timeout_minutes = 30

        with (
            patch("review_agent.config.database.async_session_factory") as mock_factory,
            patch("review_agent.config.settings.get_settings", return_value=mock_settings),
            patch("review_agent.repo.review.ReviewRepo", return_value=mock_repo),
            patch(
                "review_agent.service.scheduler.asyncio.sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            mock_factory.return_value = mock_session

            with pytest.raises(KeyboardInterrupt):
                await _recovery_loop(interval_seconds=60)

            mock_repo.list_stale.assert_awaited_once()
            mock_repo.batch_mark_failed.assert_not_called()

    @pytest.mark.asyncio
    async def test_recovery_cycle_handles_exception(self) -> None:
        """list_stale 抛出异常时不应中断循环。"""
        mock_repo = MagicMock()
        mock_repo.list_stale = AsyncMock(side_effect=ValueError("DB error"))

        mock_session = AsyncMock()
        mock_session.__aenter__.return_value = mock_session

        mock_settings = MagicMock()
        mock_settings.stale_review_timeout_minutes = 30

        with (
            patch("review_agent.config.database.async_session_factory") as mock_factory,
            patch("review_agent.config.settings.get_settings", return_value=mock_settings),
            patch("review_agent.repo.review.ReviewRepo", return_value=mock_repo),
            patch(
                "review_agent.service.scheduler.asyncio.sleep",
                side_effect=KeyboardInterrupt,
            ),
        ):
            mock_factory.return_value = mock_session

            with pytest.raises(KeyboardInterrupt):
                await _recovery_loop(interval_seconds=60)

            mock_repo.list_stale.assert_awaited_once()
