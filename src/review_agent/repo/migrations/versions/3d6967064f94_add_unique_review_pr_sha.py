"""add_unique_review_pr_sha

Revision ID: 3d6967064f94
Revises: 021107dc0f72
Create Date: 2026-06-23 22:49:20.100561

说明：
- 清理重复的 PR 评审记录后，对 reviews 表添加 (project_id, pr_number, head_sha) 唯一约束
- 用于防止并发 webhook 重复创建评审
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = '3d6967064f94'
down_revision: str | None = '021107dc0f72'
branch_labels: str | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    conn = op.get_bind()

    # Step 1: 找出重复的记录 ID（同 project_id, pr_number, head_sha 除最新外）
    duplicates = conn.execute(
        sa.text("""
            SELECT id FROM (
                SELECT id, ROW_NUMBER() OVER (
                    PARTITION BY project_id, pr_number, head_sha
                    ORDER BY create_time DESC
                ) AS rn
                FROM reviews
                WHERE pr_number IS NOT NULL
                  AND is_deleted = FALSE
            ) AS dup
            WHERE dup.rn > 1
        """)
    ).fetchall()
    dup_ids = [row[0] for row in duplicates]

    if dup_ids:
        # 先删除 findings 中的外键引用
        conn.execute(
            sa.text("DELETE FROM findings WHERE review_id = ANY(:ids)"),
            {"ids": dup_ids},
        )
        # 删除重复的 reviews
        conn.execute(
            sa.text("DELETE FROM reviews WHERE id = ANY(:ids)"),
            {"ids": dup_ids},
        )

    # Step 2: 添加唯一约束
    op.create_unique_constraint(
        'uq_review_project_pr_sha',
        'reviews',
        ['project_id', 'pr_number', 'head_sha'],
    )


def downgrade() -> None:
    op.drop_constraint('uq_review_project_pr_sha', 'reviews', type_='unique')
