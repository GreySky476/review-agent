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
