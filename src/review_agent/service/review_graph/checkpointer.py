"""检查点器工厂。

提供 MemorySaver（进程内内存）和 PostgresSaver（持久化）两种检查点器。
"""

from __future__ import annotations

from contextlib import AbstractAsyncContextManager
from typing import TYPE_CHECKING

from langgraph.checkpoint.memory import MemorySaver
from langgraph.checkpoint.serde.jsonplus import JsonPlusSerializer

if TYPE_CHECKING:
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


def _make_serializer() -> JsonPlusSerializer:
    """创建配置了自定义类型白名单的序列化器。

    LangGraph 的 jsonplus 序列化器默认不允许反序列化未注册的自定义类型。
    此处注册流水线中使用的所有自定义类型，避免运行时 WARNING 和未来版本的错误。
    """
    modules = [
        ("review_agent.service.git.base", "PRFile"),
        ("review_agent.service.chunking", "CodeChunk"),
        ("review_agent.types.enums", "ChunkPath"),
        ("review_agent.types.enums", "FindingCategory"),
        ("review_agent.types.enums", "FindingSeverity"),
        ("review_agent.service.dimensions.base", "DimensionFinding"),
    ]
    return JsonPlusSerializer(allowed_msgpack_modules=modules)


def create_checkpointer() -> MemorySaver:
    """创建内存检查点器。

    适用于开发/测试环境，进程重启后检查点丢失。
    """
    serde = _make_serializer()
    return MemorySaver(serde=serde)


def create_postgres_checkpointer() -> AbstractAsyncContextManager[AsyncPostgresSaver]:
    """创建 Postgres 持久化检查点器的 async context manager。

    适用于生产环境，支持 Worker 中断恢复。
    需在 ``async with`` 块内使用，首次调用会自动 setup 检查点表。

    Usage::

        async with create_postgres_checkpointer() as saver:
            await saver.setup()
            graph = build_review_graph(..., checkpointer=saver)
            ...

    Returns:
        Async context manager yielding an AsyncPostgresSaver instance.
    """
    from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

    from review_agent.config.settings import get_settings

    settings = get_settings()
    # AsyncPostgresSaver 使用 psycopg，不支持 SQLAlchemy 的 +asyncpg 协议后缀
    pg_url = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    return AsyncPostgresSaver.from_conn_string(pg_url)
