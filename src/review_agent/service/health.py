"""平台连通性心跳检测服务。

定期检查 GitHub / Gitee 等平台 API 是否可连通，
同时巡检所有活跃项目的 Webhook 连接状态，
记录状态（connected / error）、延迟和错误信息到数据库，
供管理后台展示。

检测在 FastAPI 后台任务中运行，不依赖 ARQ Worker。
"""

from __future__ import annotations

import logging
import time

import httpx

from review_agent.config.settings import get_settings
from review_agent.repo.platform_health import PlatformHealthRepo
from review_agent.types.enums import Platform

logger = logging.getLogger(__name__)


# ── 检测逻辑 ──────────────────────────────────────────────


async def _check_single_platform(
    session: object,
    platform: Platform,
    url: str,
    headers: dict[str, str] | None = None,
    timeout: int = 10,
) -> None:
    """检测单个平台的 API 连通性并写入数据库。"""
    repo = PlatformHealthRepo(session)  # type: ignore[arg-type]
    start = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.get(url, headers=headers)
            latency = int((time.monotonic() - start) * 1000)

            if resp.status_code == 200:
                await repo.upsert(platform, "connected", latency_ms=latency)
                logger.info("Health check OK: %s (%dms)", platform, latency)
            else:
                err = f"HTTP {resp.status_code}: {resp.text[:200]}"
                await repo.upsert(
                    platform,
                    "error",
                    latency_ms=latency,
                    error_message=err,
                )
                logger.warning(
                    "Health check failed: %s HTTP %s (%dms)",
                    platform,
                    resp.status_code,
                    latency,
                )
    except httpx.TimeoutException:
        latency = int((time.monotonic() - start) * 1000)
        await repo.upsert(platform, "error", latency_ms=latency, error_message="Request timed out")
        logger.warning("Health check timeout: %s (%dms)", platform, latency)
    except httpx.RequestError as exc:
        latency = int((time.monotonic() - start) * 1000)
        await repo.upsert(platform, "error", latency_ms=latency, error_message=str(exc))
        logger.warning("Health check error: %s - %s", platform, exc)


async def check_github(session: object) -> None:
    """检测 GitHub API 连通性。"""
    settings = get_settings()
    if settings.github_token:
        await _check_single_platform(
            session,
            Platform.GITHUB,
            "https://api.github.com/user",
            headers={
                "Authorization": f"Bearer {settings.github_token}",
                "Accept": "application/vnd.github.v3+json",
                "User-Agent": "review-agent",
            },
        )
    else:
        await _check_single_platform(
            session,
            Platform.GITHUB,
            "https://api.github.com/zen",
            headers={"User-Agent": "review-agent"},
        )


async def check_gitee(session: object) -> None:
    """检测 Gitee API 连通性。"""
    settings = get_settings()
    if settings.github_token:
        await _check_single_platform(
            session,
            Platform.GITEE,
            "https://gitee.com/api/v5/user",
            headers={"Authorization": f"Bearer {settings.github_token}"},
            timeout=10,
        )
    else:
        await _check_single_platform(
            session,
            Platform.GITEE,
            "https://gitee.com/api/v5/gitignore",
            timeout=10,
        )


async def run_all_checks(session: object, webhook_check: bool = True) -> None:
    """执行平台连通性检测，并根据结果同步项目 webhook 状态。"""
    logger.info("Starting platform health checks...")
    await check_github(session)
    await check_gitee(session)

    if not webhook_check:
        return

    # 状态变化检测：只有平台状态发生切换时才同步项目
    from sqlalchemy import select, update

    from review_agent.repo.platform_health import PlatformHealthRepo
    from review_agent.types.orm import ProjectModel

    health_repo = PlatformHealthRepo(session)  # type: ignore[arg-type]
    for platform_val, platform_enum in [("github", Platform.GITHUB), ("gitee", Platform.GITEE)]:
        health = await health_repo.get(platform_enum)
        if health is None:
            continue
        is_connected = health.status == "connected"

        # 只查 ID 和 webhook_enabled，判断是否全部已同步
        result = await session.execute(  # type: ignore[arg-type]
            select(ProjectModel.id, ProjectModel.webhook_enabled).where(
                ProjectModel.is_deleted.is_(False),
                ProjectModel.platform == platform_val,
            )
        )
        rows = result.all()
        if not rows:
            continue

        # 所有项目已处于目标状态则跳过
        all_synced = all(enabled == is_connected for _, enabled in rows)
        if all_synced:
            logger.debug(
                "Health sync skipped: all %d %s projects already in target state",
                len(rows),
                platform_val,
            )
            continue

        # 只更新状态不一致的项目
        changed = 0
        for pid, enabled in rows:
            if enabled != is_connected:
                await session.execute(  # type: ignore[arg-type]
                    update(ProjectModel)
                    .where(ProjectModel.id == pid)
                    .values(webhook_enabled=is_connected)
                )
                changed += 1
        await session.flush()  # type: ignore[arg-type]
        logger.info(
            "Health sync: %d/%d %s projects updated to webhook_enabled=%s",
            changed,
            len(rows),
            platform_val,
            is_connected,
        )
    logger.info("Health check done")
