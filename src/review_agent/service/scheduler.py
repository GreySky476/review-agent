"""数据同步定时调度器。

在 FastAPI 后台任务中运行，定期向 ARQ 队列下发 sync_project_data 任务，
由 ARQ Worker 负责实际的 PR 数据同步操作。

与 service/health.py 的后台周期任务模式相同。
"""

from __future__ import annotations

import asyncio
import logging

from arq import create_pool
from arq.connections import RedisSettings

from review_agent.config.settings import get_settings

logger = logging.getLogger(__name__)

_sync_task: asyncio.Task[None] | None = None


async def _sync_loop(interval_seconds: int) -> None:
    """后台循环：每 N 秒向 ARQ 入队 sync_project_data。"""
    from sqlalchemy import select

    from review_agent.config.database import async_session_factory
    from review_agent.types.orm import ProjectModel

    while True:
        try:
            async with async_session_factory() as db:
                # 查询所有非删除且有仓库配置的项目
                stmt = (
                    select(ProjectModel)
                    .where(
                        ProjectModel.is_deleted.is_(False),
                        ProjectModel.repo_url.isnot(None),
                        ProjectModel.repo_url != "",
                    )
                )
                rows = await db.execute(stmt)
                projects = list(rows.scalars().all())

                if not projects:
                    logger.debug("No active projects to sync")
                    await asyncio.sleep(interval_seconds)
                    continue

                logger.info("Data sync cycle: enqueuing %d projects", len(projects))
                settings = get_settings()
                pool = await create_pool(RedisSettings.from_dsn(settings.arq_redis_url))
                for project in projects:
                    try:
                        await pool.enqueue_job("sync_project_data", project.id)
                    except Exception:
                        logger.exception(
                            "Failed to enqueue sync for project %s", project.id,
                        )
                await pool.close()
        except Exception:
            logger.exception("Data sync cycle failed")
        await asyncio.sleep(interval_seconds)


def start_sync_scheduler(interval_minutes: int = 5) -> None:
    """启动数据同步调度器。

    在 FastAPI 应用启动时调用（lifespan），在事件循环中运行一个后台协程，
    每隔 interval_minutes 分钟向 ARQ 队列下发一次全项目同步任务。

    Args:
        interval_minutes: 同步间隔（分钟），默认 5 分钟。
    """
    global _sync_task  # noqa: PLW0603
    if _sync_task is not None and not _sync_task.done():
        logger.warning("Sync scheduler already running, skipping")
        return

    interval_seconds = max(60, interval_minutes * 60)
    _sync_task = asyncio.create_task(_sync_loop(interval_seconds))
    logger.info("Started data sync scheduler (interval=%dm)", interval_minutes)


# ── 主动心跳定时调度 ──────────────────────────────────────


_health_task: asyncio.Task[None] | None = None


async def _health_check_loop(interval_seconds: int) -> None:
    """后台循环：定期执行平台连通性检测并同步项目 webhook 状态。"""
    from review_agent.config.database import async_session_factory
    from review_agent.service.health import run_all_checks

    while True:
        try:
            async with async_session_factory() as session:  # type: ignore[arg-type]
                await run_all_checks(session, webhook_check=True)
                await session.commit()
        except Exception:
            logger.exception("Health check cycle failed")
        await asyncio.sleep(interval_seconds)


def start_health_check_scheduler(interval_minutes: int = 15) -> None:
    """启动主动心跳定时调度器。

    在 FastAPI 应用启动时调用，定期向 ARQ 队列下发 health check 任务，
    由 ARQ Worker 执行平台连通性检测和项目状态同步。

    Args:
        interval_minutes: 检测间隔（分钟），默认 15 分钟。
    """
    global _health_task  # noqa: PLW0603
    if _health_task is not None and not _health_task.done():
        logger.warning("Health check scheduler already running, skipping")
        return

    interval_seconds = max(60, interval_minutes * 60)
    _health_task = asyncio.create_task(_health_check_loop(interval_seconds))
    logger.info("Started health check scheduler (interval=%dm)", interval_minutes)


# ── Stale Review 回收调度 ──────────────────────────────────

_recovery_task: asyncio.Task[None] | None = None


async def _recovery_loop(interval_seconds: int) -> None:
    """后台循环：定期扫描并回收超时的 PENDING/RUNNING 评审。"""
    from review_agent.config.database import async_session_factory
    from review_agent.config.settings import get_settings
    from review_agent.repo.review import ReviewRepo
    from review_agent.service.error_logger import log_error

    while True:
        try:
            settings = get_settings()
            timeout = settings.stale_review_timeout_minutes
            async with async_session_factory() as db:
                review_repo = ReviewRepo(db)
                stale = await review_repo.list_stale(timeout_minutes=timeout)
                if stale:
                    ids = [r.id for r in stale]
                    count = await review_repo.batch_mark_failed(
                        ids,
                        error_message="Auto-recovered: review timeout exceeded",
                    )
                    await db.commit()
                    logger.info(
                        "Recovery cycle: marked %d stale reviews as FAILED",
                        count,
                    )
                    for r in stale:
                        await log_error(
                            error_type="pipeline_crashed",
                            error_message=(
                                f"Auto-recovered stale review {r.id[:8]} "
                                f"(status={r.status.value}, "
                                f"created={r.create_time.isoformat()})"
                            ),
                            project_id=r.project_id,
                            review_id=r.id,
                            recovered=True,
                        )
                else:
                    logger.debug("Recovery cycle: no stale reviews found")
        except Exception:
            logger.exception("Stale review recovery cycle failed")
        await asyncio.sleep(interval_seconds)


def start_recovery_scheduler(interval_minutes: int = 5) -> None:
    """启动 Stale Review 回收调度器。

    在 FastAPI 应用启动时调用（lifespan），在事件循环中运行一个后台协程，
    每隔 interval_minutes 分钟扫描一次超时的 PENDING/RUNNING 评审并标记为 FAILED。

    Args:
        interval_minutes: 扫描间隔（分钟），默认 5 分钟。
    """
    global _recovery_task  # noqa: PLW0603
    if _recovery_task is not None and not _recovery_task.done():
        logger.warning("Recovery scheduler already running, skipping")
        return

    interval_seconds = max(60, interval_minutes * 60)
    _recovery_task = asyncio.create_task(_recovery_loop(interval_seconds))
    logger.info("Started stale review recovery scheduler (interval=%dm)", interval_minutes)
