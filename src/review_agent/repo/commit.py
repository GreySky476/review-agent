"""Commit Repository。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import delete, select

from review_agent.repo.base import BaseRepository
from review_agent.types.orm import CommitModel


class CommitRepo(BaseRepository[CommitModel]):  # type: ignore[misc]
    """提交记录 仓库 CRUD。"""

    @property
    def _model(self) -> type[CommitModel]:
        return CommitModel  # type: ignore[no-any-return]

    async def list_by_project(
        self,
        project_id: str,
        *,
        branch: str | None = None,
        author: str | None = None,
        skip: int = 0,
        limit: int = 20,
    ) -> list[CommitModel]:
        """按项目列出提交，可选按分支/作者筛选。"""
        stmt = select(CommitModel).where(
            CommitModel.project_id == project_id,
        )
        if branch:
            stmt = stmt.where(CommitModel.branch == branch)
        if author:
            stmt = stmt.where(CommitModel.author == author)
        stmt = stmt.order_by(CommitModel.create_time.desc()).offset(skip).limit(limit)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_sha(self, project_id: str, sha: str) -> CommitModel | None:
        """按 SHA 查询提交（同 SHA 多行时取最新一条）。"""
        stmt = (
            select(CommitModel)
            .where(
                CommitModel.project_id == project_id,
                CommitModel.sha == sha,
            )
            .order_by(CommitModel.create_time.desc())
            .limit(1)
        )
        result = await self._db.execute(stmt)
        return result.scalars().first()

    async def list_by_pr(self, project_id: str, pr_number: int) -> list[CommitModel]:
        """按 PR 编号查询 commit 列表。"""
        stmt = (
            select(CommitModel)
            .where(
                CommitModel.project_id == project_id,
                CommitModel.pr_number == pr_number,
            )
            .order_by(CommitModel.create_time.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def bulk_upsert(
        self, project_id: str, pr_number: int, commits: list[dict[str, Any]]
    ) -> None:
        """先删后插，批量写入 PR 的 commit 数据。"""
        # 先删旧记录
        delete_stmt = delete(CommitModel).where(
            CommitModel.project_id == project_id,
            CommitModel.pr_number == pr_number,
        )
        await self._db.execute(delete_stmt)
        # 再批量插入新记录
        for c in commits:
            # 解析实际 commit 作者日期
            raw_date = c.get("date")
            committed_at: datetime | None = None
            if raw_date:
                try:
                    committed_at = datetime.fromisoformat(raw_date)
                except (ValueError, TypeError):
                    committed_at = None
            record = CommitModel(
                project_id=project_id,
                sha=c["sha"],
                author=c.get("author"),
                message=c.get("message", ""),
                branch=None,
                pr_number=pr_number,
                is_reviewed=False,
                additions=c.get("additions", 0),
                deletions=c.get("deletions", 0),
                files_changed=c.get("files_changed", 0),
                committed_at=committed_at,
            )
            self._db.add(record)
        await self._db.flush()
