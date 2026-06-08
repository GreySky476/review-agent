"""WebhookEvent Repository。"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import WebhookEventModel


class WebhookEventRepo(BaseRepository[WebhookEventModel]):  # type: ignore[misc]
    """Webhook 事件仓库 CRUD。"""

    @property
    def _model(self) -> type[WebhookEventModel]:
        return WebhookEventModel  # type: ignore[no-any-return]

    async def exists_in_window(self, event_id: str, window_seconds: int = 60) -> bool:
        """检查事件 ID 在去重窗口内是否已存在。

        Args:
            event_id: 平台侧的事件 ID。
            window_seconds: 去重窗口（秒）。

        Returns:
            已存在返回 True。
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=window_seconds)
        stmt = select(WebhookEventModel).where(
            WebhookEventModel.event_id == event_id,
            WebhookEventModel.create_time >= cutoff,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none() is not None

    async def create_from_payload(
        self,
        project_id: str,
        platform: str,
        event_id: str,
        action: str,
        pr_number: int,
        raw_payload: str,
    ) -> WebhookEventModel:
        """从 Webhook 请求创建事件记录。"""
        return await self.create(
            id=str(uuid4()),
            project_id=project_id,
            platform=platform,
            event_id=event_id,
            action=action,
            pr_number=pr_number,
            raw_payload=raw_payload,
        )
