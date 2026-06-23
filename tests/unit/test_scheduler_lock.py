"""Tests for scheduler distributed lock (_acquire_scheduler_lock)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from review_agent.service.scheduler import _acquire_scheduler_lock


class TestAcquireSchedulerLock:
    """_acquire_scheduler_lock 返回值逻辑测试。"""

    @pytest.mark.asyncio
    async def test_lock_acquired_successfully(self) -> None:
        """SETNX 返回 1 时应返回 True 并设置过期时间。"""
        mock_redis = AsyncMock()
        mock_redis.setnx = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch(
                "review_agent.service.scheduler.get_settings",
                return_value=mock_settings,
            ),
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
        ):
            result = await _acquire_scheduler_lock("sync")

        assert result is True
        mock_redis.setnx.assert_awaited_once_with("lock:scheduler:sync", "1")
        mock_redis.expire.assert_awaited_once_with("lock:scheduler:sync", 120)
        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_held_by_another_replica(self) -> None:
        """SETNX 返回 0 时应返回 False（锁被其他副本持有）。"""
        mock_redis = AsyncMock()
        mock_redis.setnx = AsyncMock(return_value=0)
        mock_redis.aclose = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch(
                "review_agent.service.scheduler.get_settings",
                return_value=mock_settings,
            ),
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
        ):
            result = await _acquire_scheduler_lock("health")

        assert result is False
        mock_redis.setnx.assert_awaited_once_with("lock:scheduler:health", "1")
        mock_redis.expire.assert_not_called()
        mock_redis.aclose.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_lock_redis_unavailable(self) -> None:
        """Redis 不可用时（异常）应返回 True 并继续执行。"""
        with (
            patch(
                "review_agent.service.scheduler.get_settings",
                side_effect=RuntimeError("Redis config unavailable"),
            ),
        ):
            result = await _acquire_scheduler_lock("recovery")

        assert result is True

    @pytest.mark.asyncio
    async def test_lock_custom_ttl(self) -> None:
        """自定义 TTL 应传递给 expire。"""
        mock_redis = AsyncMock()
        mock_redis.setnx = AsyncMock(return_value=1)
        mock_redis.expire = AsyncMock()
        mock_redis.aclose = AsyncMock()

        mock_settings = MagicMock()
        mock_settings.redis_url = "redis://localhost:6379/0"

        with (
            patch(
                "review_agent.service.scheduler.get_settings",
                return_value=mock_settings,
            ),
            patch("redis.asyncio.Redis.from_url", return_value=mock_redis),
        ):
            result = await _acquire_scheduler_lock("sync", ttl_seconds=60)

        assert result is True
        mock_redis.expire.assert_awaited_once_with("lock:scheduler:sync", 60)
        mock_redis.aclose.assert_awaited_once()
