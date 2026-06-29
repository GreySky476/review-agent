"""drop_review_unique_constraint_add_indexes

Revision ID: 001
Revises: 3d6967064f94
Create Date: 2026-06-29 23:59:59.000000

说明：
- 删除 reviews 表 (project_id, pr_number, head_sha) 唯一约束
- 添加 (project_id, head_sha) 和 (project_id, pr_number) 索引
- 不再限制同 SHA 只能有一条评审记录，改为业务层并发控制
"""

from collections.abc import Sequence

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "001"
down_revision: str | Sequence[str] | None = "3d6967064f94"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "c3d4e5f6a7b8"


def upgrade() -> None:
    op.drop_constraint("uq_review_project_pr_sha", "reviews", type_="unique")
    op.create_index("ix_reviews_project_head_sha", "reviews", ["project_id", "head_sha"])
    op.create_index("ix_reviews_project_pr", "reviews", ["project_id", "pr_number"])


def downgrade() -> None:
    op.drop_index("ix_reviews_project_pr", table_name="reviews")
    op.drop_index("ix_reviews_project_head_sha", table_name="reviews")
    op.create_unique_constraint(
        "uq_review_project_pr_sha",
        "reviews",
        ["project_id", "pr_number", "head_sha"],
    )
