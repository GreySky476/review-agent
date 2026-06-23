# Clean Commit Template

清理指定 SHA 的 commit 和 review 数据（数据污染时使用）。

## 用法

```bash
uv run python scripts/clean_commit.py <sha>
```

## 脚本

```python
import asyncio
import sys

from review_agent.config.database import async_session_factory
from review_agent.types.orm import CommitModel, FindingModel, ReviewModel, PullRequestModel
from sqlalchemy import delete, select

SHA = sys.argv[1] if len(sys.argv) > 1 else "<sha>"

async def main():
    async with async_session_factory() as db:
        # 查询 reviews
        reviews = await db.execute(
            select(ReviewModel).where(ReviewModel.head_sha.like(f"{SHA}%"))
        )
        review_rows = list(reviews.scalars().all())
        review_ids = [r.id for r in review_rows]
        print(f"found {len(review_rows)} review(s): {[r.id[:8] for r in review_rows]}")

        # 先解除 pull_requests 的外键引用
        for rid in review_ids:
            prs = await db.execute(
                select(PullRequestModel).where(PullRequestModel.last_review_id == rid)
            )
            for pr in list(prs.scalars().all()):
                print(f"  unlinking review from PR #{pr.pr_number}")
                pr.last_review_id = None
            await db.flush()

        # 删除 findings
        if review_ids:
            del_findings = await db.execute(
                delete(FindingModel).where(FindingModel.review_id.in_(review_ids))
            )
            print(f"deleted {del_findings.rowcount} findings")
            # 删除 reviews
            del_reviews = await db.execute(
                delete(ReviewModel).where(ReviewModel.head_sha.like(f"{SHA}%"))
            )
            print(f"deleted {del_reviews.rowcount} reviews")
        # 删除 commits
        del_commits = await db.execute(
            delete(CommitModel).where(CommitModel.sha.like(f"{SHA}%"))
        )
        print(f"deleted {del_commits.rowcount} commits")
        await db.commit()
        print("done. records cleaned.")

asyncio.run(main())
```
