"""Tests for webhook_security module."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from fakeredis import FakeRedis as _SyncFakeRedis

from review_agent.service.webhook_security import (
    RedisRateLimiter,
    verify_platform_token,
)


class _AsyncFakeRedis:
    def __init__(self) -> None:
        self._redis = _SyncFakeRedis()

    async def eval(self, script: str, numkeys: int, *args: str) -> int:  # noqa: A003
        return self._redis.eval(script, numkeys, *args)

    async def aclose(self) -> None:
        self._redis.close()


class TestRedisRateLimiter:
    @pytest.mark.asyncio
    async def test_basic_rate_limiting(self) -> None:
        limiter = RedisRateLimiter(max_requests=3, window_seconds=60)
        fake_redis = _AsyncFakeRedis()
        with patch(
            "review_agent.service.webhook_security._AsyncRedis.from_url",
            return_value=fake_redis,
        ):
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is False

    @pytest.mark.asyncio
    async def test_different_ips_independent(self) -> None:
        limiter = RedisRateLimiter(max_requests=2, window_seconds=60)
        fake_redis = _AsyncFakeRedis()
        with patch(
            "review_agent.service.webhook_security._AsyncRedis.from_url",
            return_value=fake_redis,
        ):
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is False
            assert await limiter.check("192.168.1.2") is True
            assert await limiter.check("192.168.1.2") is True
            assert await limiter.check("192.168.1.2") is False

    @pytest.mark.asyncio
    async def test_window_expires(self) -> None:
        limiter = RedisRateLimiter(max_requests=2, window_seconds=1)
        fake_redis = _AsyncFakeRedis()
        with patch(
            "review_agent.service.webhook_security._AsyncRedis.from_url",
            return_value=fake_redis,
        ):
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is True
            assert await limiter.check("192.168.1.1") is False
            import asyncio

            await asyncio.sleep(1.1)
            assert await limiter.check("192.168.1.1") is True

    @pytest.mark.asyncio
    async def test_redis_error_fallback(self) -> None:
        from review_agent.service import webhook_security
        from review_agent.service.webhook_security import check_rate_limit

        old = webhook_security._limiter
        webhook_security._limiter = None
        try:
            with patch(
                "review_agent.service.webhook_security.get_settings",
            ) as ms:
                ms.return_value.webhook_rate_limiter_backend = "redis"
                ms.return_value.redis_url = "redis://invalid:6379/0"
                result = await check_rate_limit("192.168.1.1")
                assert result is True
        finally:
            webhook_security._limiter = old

    @pytest.mark.asyncio
    async def test_memory_backend(self) -> None:
        from review_agent.service import webhook_security
        from review_agent.service.webhook_security import check_rate_limit

        old = webhook_security._limiter
        webhook_security._limiter = None
        try:
            with patch(
                "review_agent.service.webhook_security.get_settings",
            ) as ms:
                ms.return_value.webhook_rate_limiter_backend = "memory"
                result = await check_rate_limit("192.168.1.1")
                assert result is True
        finally:
            webhook_security._limiter = old


class TestVerifyPlatformToken:
    """Tests for verify_platform_token (GitLab/Gitee token verification)."""

    def test_matching_tokens_return_true(self) -> None:
        """Matching tokens should return True."""
        assert verify_platform_token("secret123", "secret123") is True

    def test_mismatched_tokens_return_false(self) -> None:
        """Mismatched tokens should return False."""
        assert verify_platform_token("secret123", "wrong") is False

    def test_empty_secret_and_token(self) -> None:
        """Empty secret vs empty token should match."""
        assert verify_platform_token("", "") is True

    def test_empty_secret_nonempty_token(self) -> None:
        """Empty secret vs non-empty token should not match."""
        assert verify_platform_token("", "token") is False

    def test_nonempty_secret_empty_token(self) -> None:
        """Non-empty secret vs empty token should not match."""
        assert verify_platform_token("secret", "") is False

    def test_case_sensitive(self) -> None:
        """Token comparison is case-sensitive."""
        assert verify_platform_token("MySecret", "mysecret") is False

    def test_whitespace_sensitive(self) -> None:
        """Token comparison is whitespace-sensitive."""
        assert verify_platform_token("secret ", "secret") is False
