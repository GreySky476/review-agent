"""检查点器工厂。"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver


def create_checkpointer() -> MemorySaver:
    """创建检查点器。

    Phase 1 使用 MemorySaver（进程内内存），
    Phase 2 可切换至 PostgresSaver 实现持久化中断恢复。
    """
    return MemorySaver()
