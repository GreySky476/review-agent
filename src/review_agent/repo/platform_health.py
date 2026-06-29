"""PlatformHealth Repository。"""

from __future__ import annotations

from typing import Any

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.enums import Platform
from review_agent.types.orm import PlatformHealthModel


class PlatformHealthRepo(BaseRepository[PlatformHealthModel]):  # type: ignore[misc]
    """平台连通性心跳状态 CRUD。"""

    @property
    def _model(self) -> type[PlatformHealthModel]:
        return PlatformHealthModel  # type: ignore[no-any-return]

    async def upsert(
        self,
        platform: Platform,
        status: str,
        latency_ms: int = 0,
        error_message: str | None = None,
    ) -> PlatformHealthModel:
        """插入或更新平台连通性状态。"""
        stmt = select(PlatformHealthModel).where(
            PlatformHealthModel.platform == platform,
        )
        result = await self._db.execute(stmt)
        instance = result.scalar_one_or_none()
        if instance:
            instance.status = status
            instance.latency_ms = latency_ms
            instance.error_message = error_message
        else:
            instance = PlatformHealthModel(
                platform=platform,
                status=status,
                latency_ms=latency_ms,
                error_message=error_message,
            )
            self._db.add(instance)
        await self._db.flush()
        return instance

    async def get_by_platform(self, platform: Platform) -> PlatformHealthModel | None:
        """按平台查询最新状态。"""
        stmt = select(PlatformHealthModel).where(
            PlatformHealthModel.platform == platform,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_all(self) -> list[dict[str, Any]]:
        """获取所有平台状态列表。"""
        stmt = select(PlatformHealthModel)
        result = await self._db.execute(stmt)
        rows = result.scalars().all()
        return [
            {
                "platform": r.platform,
                "status": r.status,
                "latency_ms": r.latency_ms,
                "error_message": r.error_message,
                "last_checked_at": (r.update_time.isoformat() if r.update_time else None),
            }
            for r in rows
        ]
