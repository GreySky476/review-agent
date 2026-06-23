"""异步错误日志记录工具。

设计目标：在任意位置（LangGraph 节点、Service 方法、Provider 等没有 DB session 的上下文）
都能记录错误到 ReviewErrorLog 表。

工作原理：
1. log_error() 启动一个 asyncio.create_task 后台写入
2. 调用方无需持有 DB session，不会被阻塞
3. 后台 Task 用全局 set 持有引用，防止 GC 回收
4. 超长字段自动截断，防止数据库行过大
5. 内存缓冲队列作为降级策略：DB 写入失败时暂存到缓冲中，
   后续成功写入时自动排空，防止 fire-and-forget 错误丢失
"""

from __future__ import annotations

import asyncio
import logging
from collections import deque
from typing import Any

from review_agent.config.database import async_session_factory
from review_agent.repo.review_error import ReviewErrorRepo
from review_agent.types.error_types import ErrorType

logger = logging.getLogger(__name__)

# 持有后台 Task 引用，防止 asyncio 在事件循环迭代时 GC 回收
_background_tasks: set[asyncio.Task[Any]] = set()

_MAX_MESSAGE_LENGTH = 2000
_MAX_DETAIL_LENGTH = 5000

# ── 内存缓冲队列（降级策略） ────────────────────────────────
_BACKUP_BUFFER_MAXLEN = 1000
_backup_buffer: deque[dict[str, Any]] = deque(maxlen=_BACKUP_BUFFER_MAXLEN)
_buffer_lock = asyncio.Lock()
_dropped_count: int = 0


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

    当数据库写入失败时，错误信息会暂存到内存缓冲队列（最大 100 条），
    后续每次写入成功时自动排空缓冲队列。

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
    """后台写入 ReviewErrorLog。内部函数，不直接调用。

    DB 写入成功后自动尝试排空内存缓冲队列，
    写入失败时将当前条目暂存到缓冲队列。
    """
    try:
        async with async_session_factory() as db:
            repo = ReviewErrorRepo(db)
            # 写入当前错误
            await _write_single_record(
                repo=repo,
                error_type=error_type,
                error_message=error_message,
                error_detail=error_detail,
                project_id=project_id,
                review_id=review_id,
                recovered=recovered,
            )
            # 排空缓冲队列
            await _flush_backup_buffer(repo)
            await db.commit()
    except Exception as exc:
        logger.warning("Failed to write ReviewErrorLog: %s", exc)
        # DB 写入失败，暂存到内存缓冲
        await _enqueue_backup(
            error_type=error_type,
            error_message=error_message,
            error_detail=error_detail,
            project_id=project_id,
            review_id=review_id,
            recovered=recovered,
        )


async def _write_single_record(
    repo: ReviewErrorRepo,
    error_type: str,
    error_message: str,
    error_detail: str | None,
    project_id: str | None,
    review_id: str | None,
    recovered: bool,
) -> None:
    """写入单条错误记录到数据库。"""
    await repo.create(
        error_type=error_type,
        error_message=error_message,
        error_detail=error_detail,
        project_id=project_id,
        review_id=review_id,
        recovered=recovered,
        frequency=1,
    )


async def _flush_backup_buffer(repo: ReviewErrorRepo) -> None:
    """排空缓冲队列中的所有积压条目到数据库。"""
    global _dropped_count
    async with _buffer_lock:
        while _backup_buffer:
            entry = _backup_buffer.popleft()
            await repo.create(**entry)

        # 如果之前有丢弃的记录，写入一条汇总日志
        if _dropped_count > 0:
            await repo.create(
                error_type=ErrorType.DB_WRITE_FAILED,
                error_message=(
                    f"Errors dropped ({_dropped_count} entries lost due to buffer overflow)"
                ),
                error_detail=None,
                project_id=None,
                review_id=None,
                recovered=False,
                frequency=_dropped_count,
            )
            _dropped_count = 0


async def _enqueue_backup(
    error_type: str,
    error_message: str,
    error_detail: str | None,
    project_id: str | None,
    review_id: str | None,
    recovered: bool,
) -> None:
    """将错误条目暂存到内存缓冲队列。"""
    global _dropped_count
    async with _buffer_lock:
        entry: dict[str, Any] = {
            "error_type": error_type,
            "error_message": error_message,
            "error_detail": error_detail,
            "project_id": project_id,
            "review_id": review_id,
            "recovered": recovered,
        }
        if len(_backup_buffer) == _backup_buffer.maxlen:
            # 缓冲已满，丢弃最旧的记录
            _dropped_count += 1
        _backup_buffer.append(entry)
