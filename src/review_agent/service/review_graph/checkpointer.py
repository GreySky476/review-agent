"""检查点器工厂。

提供 MemorySaver（进程内内存）和 PostgresSaver（持久化）两种检查点器。
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver


def create_checkpointer() -> MemorySaver:
    """创建内存检查点器。

    适用于开发/测试环境，进程重启后检查点丢失。
    """
    return MemorySaver()


def create_postgres_checkpointer():
    """创建 Postgres 持久化检查点器的 async context manager。

    适用于生产环境，支持 Worker 中断恢复。
    需在 ``async with`` 块内使用，首次调用会自动 setup 检查点表。

    Usage::

        async with create_postgres_checkpointer() as saver:
            await saver.setup()
            graph = build_review_graph(..., checkpointer=saver)
            ...

    Returns:
        AsyncPostgresSaver 的 async context manager。
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from review_agent.config.settings import get_settings

    settings = get_settings()
    # AsyncPostgresSaver 使用 psycopg，不支持 SQLAlchemy 的 +asyncpg 协议后缀
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return AsyncPostgresSaver.from_conn_string(pg_url)
