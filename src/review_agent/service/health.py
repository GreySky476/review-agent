"""平台连通性心跳检测服务。

定期检查 GitHub / Gitee 等平台 API 是否可连通，
同时巡检所有活跃项目的 Webhook 连接状态，
记录状态（connected / error）、延迟和错误信息到数据库，
供管理后台展示。

检测在 FastAPI 后台任务中运行，不依赖 ARQ Worker。
"""

from __future__ import annotations

import asyncio
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


async def check_project_webhooks(session: object) -> None:
    """巡检所有活跃项目的 Webhook 连接状态。

    对 webhook_enabled=True 的项目，通过 GitHub API 验证
    webhook 是否仍有效配置，并更新状态。
    """
    from sqlalchemy import select

    from review_agent.service.git.github_provider import GitHubProvider
    from review_agent.types.orm import ProjectModel

    logger.info("Starting project webhook health checks...")
    try:
        # 查询所有有 repo_url 的非删除项目（无论 webhook_enabled 状态）
        stmt = select(ProjectModel).where(
            ProjectModel.is_deleted.is_(False),
            ProjectModel.repo_url.isnot(None),
            ProjectModel.repo_url != "",
        )
        rows = await session.execute(stmt)  # type: ignore[arg-type]
        projects = rows.scalars().all()

        if not projects:
            logger.debug("No projects with repo_url configured")
            return

        logger.info("Checking webhooks for %d projects", len(projects))
        semaphore = asyncio.Semaphore(5)  # 最多 5 个并发

        # 共享一个 GitHubProvider 实例（复用连接池，减少 SSL 重试日志）
        git = GitHubProvider()
        public_url = get_settings().public_url

        async def _check_one(project: object) -> None:
            async with semaphore:
                p = project  # type: ignore[var-annotated]
                repo_name = _extract_owner_repo(p.repo_url)  # type: ignore[attr-defined]
                if not repo_name:
                    return
                try:
                    webhook_url = f"{public_url}/webhook/{p.platform}"  # type: ignore[attr-defined]
                    result = await git.check_webhook(repo_name, webhook_url)
                    old_enabled = p.webhook_enabled  # type: ignore[attr-defined]
                    new_enabled = result["found"]
                    if old_enabled != new_enabled:
                        p.webhook_enabled = new_enabled  # type: ignore[attr-defined]
                        logger.info(
                            "Webhook health: %s → webhook_enabled=%s (was %s)",
                            repo_name,
                            new_enabled,
                            old_enabled,
                        )
                except Exception as exc:
                    logger.debug("Webhook check skipped for %s: %s", repo_name, exc)

        await asyncio.gather(*[_check_one(p) for p in projects], return_exceptions=True)
        await session.flush()  # type: ignore[arg-type]
        changed = sum(1 for p in projects if p.webhook_enabled)  # type: ignore[attr-defined]
        logger.info(
            "Webhook health done: %d projects checked, %d connected",
            len(projects),
            changed,
        )
    except Exception as exc:
        logger.error("Project webhook health check failed: %s", exc)


def _extract_owner_repo(repo_url: str) -> str | None:
    """从 repo_url 提取 owner/repo。"""
    parts = repo_url.rstrip("/").split("/")
    if len(parts) >= 2:
        return "/".join(parts[-2:]).removesuffix(".git")
    return None


async def run_all_checks(session: object, webhook_check: bool = True) -> None:
    """并发执行所有平台的连通性检测（含可选的 Webhook 巡检）。"""
    logger.info("Starting platform health checks...")
    tasks = [
        check_github(session),
        check_gitee(session),
    ]
    if webhook_check:
        tasks.append(check_project_webhooks(session))
    await asyncio.gather(*tasks, return_exceptions=True)


# ── 后台周期任务 ──────────────────────────────────────────


_periodic_task: asyncio.Task[None] | None = None


async def _periodic_health_check(
    platform_interval: int,
    webhook_interval: int,
) -> None:
    """后台循环：定期执行平台 + Webhook 连通性检测。"""
    from review_agent.config.database import async_session_factory

    cycles = 0
    webhook_cycles = max(1, webhook_interval // platform_interval)
    while True:
        cycles += 1
        try:
            async with async_session_factory() as session:  # type: ignore[arg-type]
                await run_all_checks(session, webhook_check=(cycles % webhook_cycles == 0))
                await session.commit()
        except Exception:
            logger.exception("Periodic health check failed")
        await asyncio.sleep(platform_interval)


def start_periodic_health_check(
    interval_minutes: int = 15,
) -> None:
    """启动后台健康检查周期任务。

    在 FastAPI 应用启动时调用，在事件循环中运行一个后台协程，
    每隔 interval_minutes 分钟执行一次所有平台的连通性检测。

    Args:
        interval_minutes: 检测间隔（分钟）。
    """
    global _periodic_task  # noqa: PLW0603
    if _periodic_task is not None and not _periodic_task.done():
        logger.warning("Periodic health check already running, skipping")
        return

    settings = get_settings()
    platform_seconds = max(60, interval_minutes * 60)
    webhook_seconds = max(60, settings.webhook_health_interval_minutes * 60)
    _periodic_task = asyncio.create_task(
        _periodic_health_check(platform_seconds, webhook_seconds),
    )
    logger.info(
        "Started periodic health check (platform=%dm webhook=%dm)",
        interval_minutes,
        settings.webhook_health_interval_minutes,
    )
