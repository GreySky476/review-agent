"""异步错误日志记录工具。

设计目标：在任意位置（LangGraph 节点、Service 方法、Provider 等没有 DB session 的上下文）
都能记录错误到 ReviewErrorLog 表。

工作原理：
1. log_error() 启动一个 asyncio.create_task 后台写入
2. 调用方无需持有 DB session，不会被阻塞
3. 后台 Task 用全局 set 持有引用，防止 GC 回收
4. 超长字段自动截断，防止数据库行过大
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from review_agent.config.database import async_session_factory
from review_agent.repo.review_error import ReviewErrorRepo
from review_agent.types.error_types import ErrorType

logger = logging.getLogger(__name__)

# 持有后台 Task 引用，防止 asyncio 在事件循环迭代时 GC 回收
_background_tasks: set[asyncio.Task[Any]] = set()

_MAX_MESSAGE_LENGTH = 2000
_MAX_DETAIL_LENGTH = 5000


async def log_error(
    error_type: str,
    error_message: str,
    error_detail: str | None = None,
    project_id: str | None = None,
    review_id: str | None = None,
    recovered: bool = False,
) -> None:
    """异步记录错误日志到数据库。

    可在任何位置安全调用，无需 DB session。

    Args:
        error_type: 错误类型（ErrorType 枚举值）。
        error_message: 错误描述（自动截断至 2000 字符）。
        error_detail: 详细错误信息/traceback（自动截断至 5000 字符）。
        project_id: 关联项目 ID（可选）。
        review_id: 关联评审 ID（可选）。
        recovered: 是否已自动恢复（用于恢复追踪）。
    """
    # 落回到 UNKNOWN
    if error_type not in list(ErrorType):
        error_type = ErrorType.UNKNOWN

    truncated_message = (error_message or "")[:_MAX_MESSAGE_LENGTH]
    truncated_detail = (error_detail or "")[:_MAX_DETAIL_LENGTH] if error_detail else None

    task = asyncio.create_task(
        _write_error_log(
            error_type=error_type,
            error_message=truncated_message,
            error_detail=truncated_detail,
            project_id=project_id,
            review_id=review_id,
            recovered=recovered,
        ),
    )
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


async def _write_error_log(
    error_type: str,
    error_message: str,
    error_detail: str | None,
    project_id: str | None,
    review_id: str | None,
    recovered: bool,
) -> None:
    """后台写入 ReviewErrorLog。内部函数，不直接调用。"""
    try:
        async with async_session_factory() as db:
            repo = ReviewErrorRepo(db)
            await repo.create(
                error_type=error_type,
                error_message=error_message,
                error_detail=error_detail,
                project_id=project_id,
                review_id=review_id,
                recovered=recovered,
                frequency=1,
            )
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to write ReviewErrorLog: %s", exc)
