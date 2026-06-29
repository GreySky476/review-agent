"""全局测试夹具和配置。"""

import os

# 测试环境必需的全局设置
os.environ.setdefault(
    "REVIEW_AGENT_JWT_SECRET",
    "test-jwt-secret-key-that-is-at-least-32-characters-long",
)
os.environ.setdefault("REVIEW_AGENT_WEBHOOK_IP_WHITELIST_ENABLED", "false")
os.environ.setdefault("REVIEW_AGENT_WEBHOOK_RATE_LIMITER_ENABLED", "false")

from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession


class MockResult:
    """模拟 SQLAlchemy Result，支持 scalars()/scalar()/first() 等链式调用。"""

    def __init__(self, scalars_list: list | None = None, scalar_value=None):
        self._scalars_list = scalars_list or []
        self._scalar_value = scalar_value

    def scalars(self) -> "MockResult":
        return self

    def all(self) -> list:
        return self._scalars_list

    def scalar(self):
        return self._scalar_value

    def scalar_one_or_none(self):
        return self._scalars_list[0] if self._scalars_list else None

    def first(self):
        return self._scalars_list[0] if self._scalars_list else None


@pytest.fixture
def mock_db() -> AsyncSession:
    """返回 mock AsyncSession，execute 返回空结果。"""
    mock = AsyncMock(spec=AsyncSession)

    # 支持 begin_nested() savepoint
    savepoint = AsyncMock()
    savepoint.commit = AsyncMock()
    savepoint.rollback = AsyncMock()
    mock.begin_nested = AsyncMock(return_value=savepoint)

    mock.execute.return_value = MockResult([])
    return mock  # type: ignore
