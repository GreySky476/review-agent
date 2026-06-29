"""Webhook 安全加固工具。

提供：
- GitHub Webhook IP 白名单验证
- API 速率限制（per-IP 滑动窗口）
- Payload 大小限制

设计原则：
1. IP 列表从 https://api.github.com/meta 实时获取，缓存 24 小时
2. 获取失败时静默放行（防止 GitHub API 不可用导致服务中断）
3. 线程安全缓存，避免并发请求时重复 fetch
4. 速率限制在内存中维护，服务重启后重置
"""

from __future__ import annotations

import asyncio
import ipaddress
import logging
import time
from typing import Any

import httpx
from redis.asyncio import Redis as _AsyncRedis

from review_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

_GITHUB_META_URL = "https://api.github.com/meta"
_CACHE_TTL_SECONDS = 86400  # 24 小时

# ── 速率限制 ──────────────────────────────────────────────

_MAX_REQUESTS_PER_WINDOW = 30
_WINDOW_SECONDS = 60
_MAX_PAYLOAD_BYTES = 5 * 1024 * 1024  # 5 MB


class GitHubIPChecker:
    """GitHub Webhook IP 白名单检查器。

    用法::

        checker = GitHubIPChecker()
        if not await checker.is_github_ip(client_ip):
            raise HTTPException(status_code=403)
    """

    def __init__(self) -> None:
        self._hook_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] | None = None
        self._last_fetch: float = 0
        self._fetch_lock = asyncio.Lock()

    async def _fetch_github_ips(self) -> list[str] | None:
        """从 GitHub API 获取 Webhook 来源 IP 范围。"""
        try:
            settings = get_settings()
            headers: dict[str, str] = {"User-Agent": "review-agent"}
            if settings.github_token:
                headers["Authorization"] = f"Bearer {settings.github_token}"

            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.get(_GITHUB_META_URL, headers=headers)
                resp.raise_for_status()
                data: dict[str, Any] = resp.json()
                hooks: list[str] = data.get("hooks", [])
                if not isinstance(hooks, list):
                    logger.warning("Unexpected GitHub meta response format")
                    return None
                logger.info("Fetched %d GitHub webhook CIDR ranges", len(hooks))
                return hooks
        except httpx.TimeoutException:
            logger.warning("GitHub meta API timed out, skipping IP whitelist fetch")
            return None
        except httpx.RequestError as exc:
            logger.warning("GitHub meta API request failed: %s, skipping IP whitelist fetch", exc)
            return None
        except (ValueError, KeyError) as exc:
            logger.warning("Failed to parse GitHub meta response: %s", exc)
            return None

    def _parse_networks(
        self,
        cidr_list: list[str],
    ) -> list[ipaddress.IPv4Network | ipaddress.IPv6Network]:
        """将 CIDR 字符串列表解析为网络对象列表。"""
        networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        for cidr in cidr_list:
            try:
                networks.append(ipaddress.ip_network(cidr, strict=False))
            except ValueError as exc:
                logger.debug("Skipping invalid CIDR '%s': %s", cidr, exc)
        return networks

    async def _ensure_loaded(self) -> bool:
        """确保 IP 列表已加载（带缓存过期逻辑）。

        Returns:
            True 表示成功加载（或缓存有效），False 表示无法获取。
        """
        now = time.monotonic()
        if self._hook_networks is not None and (now - self._last_fetch) < _CACHE_TTL_SECONDS:
            return True

        async with self._fetch_lock:
            # 双重检查：防止在锁等待期间已被其他协程加载
            if self._hook_networks is not None and (now - self._last_fetch) < _CACHE_TTL_SECONDS:
                return True

            cidr_list = await self._fetch_github_ips()
            if cidr_list is None:
                # 获取失败，保留上次缓存（如果尚未过期）
                if self._hook_networks is not None:
                    logger.info("Using stale GitHub IP cache (age=%.0fs)", now - self._last_fetch)
                    return True
                return False

            self._hook_networks = self._parse_networks(cidr_list)
            self._last_fetch = time.monotonic()
            logger.info("GitHub IP whitelist loaded: %d networks", len(self._hook_networks))
            return True

    async def is_github_ip(self, ip_str: str) -> bool:
        """判断给定 IP 是否属于 GitHub Webhook 来源范围。

        Args:
            ip_str: 客户端 IP 地址字符串（如 "192.30.252.0"）。

        Returns:
            True 表示 IP 在 GitHub 白名单中，或无法获取白名单时放行。
            False 表示 IP 不在白名单中。
        """
        loaded = await self._ensure_loaded()
        if not loaded or self._hook_networks is None:
            logger.warning(
                "GitHub IP whitelist unavailable, ALLOWING request (degraded security mode)"
            )
            return True

        try:
            addr = ipaddress.ip_address(ip_str)
        except ValueError:
            logger.warning("Invalid client IP address: %s", ip_str)
            return False

        return any(addr in network for network in self._hook_networks)


# 全局单例
_checker: GitHubIPChecker | None = None


async def is_github_request(ip_str: str) -> bool:
    """便捷函数：判断请求是否来自 GitHub。

    使用全局单例，避免重复创建检查器。
    """
    global _checker  # noqa: PLW0603
    if _checker is None:
        _checker = GitHubIPChecker()
    return await _checker.is_github_ip(ip_str)


# ── 速率限制 ──────────────────────────────────────────────


class RateLimiter:
    """内存中的 per-IP 速率限制器（滑动窗口）。

    每个 IP 在时间窗口内允许的最大请求数由 _MAX_REQUESTS_PER_WINDOW 控制。
    每次检查会自动清理过期时间戳，防止内存泄漏。

    用法::

        limiter = RateLimiter()
        if not limiter.check("192.168.1.1"):
            raise HTTPException(status_code=429)
    """

    def __init__(
        self,
        max_requests: int = _MAX_REQUESTS_PER_WINDOW,
        window_seconds: int = _WINDOW_SECONDS,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds
        self._records: dict[str, list[float]] = {}
        self._lock = asyncio.Lock()

    async def check(self, ip: str) -> bool:
        """检查请求是否在限制范围内。

        Args:
            ip: 请求来源 IP 地址。

        Returns:
            True 表示未超限，False 表示已达速率上限。
        """
        now = time.monotonic()
        cutoff = now - self._window_seconds

        async with self._lock:
            timestamps = self._records.get(ip, [])
            # 清理过期记录
            fresh: list[float] = [t for t in timestamps if t > cutoff]
            if len(fresh) >= self._max_requests:
                self._records[ip] = fresh
                return False

            fresh.append(now)
            self._records[ip] = fresh
            return True

    async def cleanup(self) -> None:
        """清理所有过期记录，防止内存泄漏。"""
        now = time.monotonic()
        cutoff = now - self._window_seconds
        async with self._lock:
            expired_keys: list[str] = []
            for ip, timestamps in self._records.items():
                fresh = [t for t in timestamps if t > cutoff]
                if fresh:
                    self._records[ip] = fresh
                else:
                    expired_keys.append(ip)
            for key in expired_keys:
                del self._records[key]


# 全局单例
_limiter: RateLimiter | None = None


class RedisRateLimiter:
    """Redis 后端的 per-IP 速率限制器（滑动窗口，Lua 脚本原子操作）。

    Key 格式: ``ratelimit:{ip}``
    使用 Sorted Set + Lua 脚本实现原子 ZREMRANGEBYSCORE + ZCARD + ZADD。

    用法::

        limiter = RedisRateLimiter()
        if not await limiter.check("192.168.1.1"):
            raise HTTPException(status_code=429)
    """

    _SCRIPT = """
local key = KEYS[1]
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local max_req = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', key, '-inf', now - window)
if redis.call('ZCARD', key) >= max_req then return 0 end
redis.call('ZADD', key, now, now)
redis.call('EXPIRE', key, window)
return 1
"""

    def __init__(
        self,
        max_requests: int = _MAX_REQUESTS_PER_WINDOW,
        window_seconds: int = _WINDOW_SECONDS,
    ) -> None:
        self._max_requests = max_requests
        self._window_seconds = window_seconds

    async def check(self, ip: str) -> bool:
        """检查请求是否在限制范围内。

        Args:
            ip: 请求来源 IP 地址。

        Returns:
            True 表示未超限，False 表示已达速率上限。
        """
        settings = get_settings()
        redis = _AsyncRedis.from_url(settings.redis_url)
        try:
            ok = await redis.eval(
                self._SCRIPT,
                1,
                f"ratelimit:{ip}",
                str(time.time()),
                str(self._window_seconds),
                str(self._max_requests),
            )
            return bool(ok)
        finally:
            await redis.aclose()


async def check_rate_limit(ip: str) -> bool:
    """便捷函数：检查 IP 的速率限制。

    根据 ``webhook_rate_limiter_backend`` 配置选择后端。
    Redis 后端失败时自动回退到内存实现。
    """
    settings = get_settings()
    if settings.webhook_rate_limiter_backend == "redis":
        try:
            return await RedisRateLimiter().check(ip)
        except Exception:
            logger.warning("Redis rate limit failed, falling back to memory")
    global _limiter  # noqa: PLW0603
    if _limiter is None:
        _limiter = RateLimiter()
    return await _limiter.check(ip)


# ── Payload 大小限制 ─────────────────────────────────────


def check_payload_size(content_length: int | None, raw_body: bytes | None = None) -> bool:
    """检查请求体大小是否超出限制。

    Args:
        content_length: Content-Length header 的值（可为 None）。
        raw_body: 原始请求体 bytes（content_length 缺省时使用）。

    Returns:
        True 表示未超限，False 表示超出限制。
    """
    if content_length is not None:
        if content_length > _MAX_PAYLOAD_BYTES:
            logger.warning(
                "Payload too large: Content-Length=%d > %d",
                content_length,
                _MAX_PAYLOAD_BYTES,
            )
            return False
        return True

    # 无 Content-Length 时用实际大小
    if raw_body is not None and len(raw_body) > _MAX_PAYLOAD_BYTES:
        logger.warning(
            "Payload too large: actual_size=%d > %d",
            len(raw_body),
            _MAX_PAYLOAD_BYTES,
        )
        return False

    return True
