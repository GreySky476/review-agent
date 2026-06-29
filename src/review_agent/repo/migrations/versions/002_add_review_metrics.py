"""add_review_metrics

Revision ID: 002
Revises: 001
Create Date: 2026-06-30 01:30:00.000000

说明：
- 创建 review_ai_calls 表，记录每次 AI 调用的 token 消耗和耗时
- ReviewModel 追加 7 个汇总指标字段（summary_markdown, total_prompt_tokens, ...）
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "002"
down_revision: str | Sequence[str] | None = "001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = "c3d4e5f6a7b8"


def upgrade() -> None:
    # 创建 review_ai_calls 表
    op.create_table(
        "review_ai_calls",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "review_id", sa.String(36), sa.ForeignKey("reviews.id"), nullable=False, index=True
        ),
        sa.Column("batch_idx", sa.Integer(), nullable=False),
        sa.Column("model", sa.String(64), nullable=False),
        sa.Column("prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("completion_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("total_tokens", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("duration_ms", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("status", sa.String(32), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()
        ),
    )

    # ReviewModel 追加汇总指标字段
    op.add_column("reviews", sa.Column("summary_markdown", sa.Text(), nullable=True))
    op.add_column(
        "reviews",
        sa.Column("total_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reviews",
        sa.Column("total_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "reviews", sa.Column("ai_call_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column("reviews", sa.Column("pipeline_duration_ms", sa.Integer(), nullable=True))
    op.add_column(
        "reviews", sa.Column("chunk_count", sa.Integer(), nullable=False, server_default="0")
    )
    op.add_column(
        "reviews", sa.Column("file_count", sa.Integer(), nullable=False, server_default="0")
    )


def downgrade() -> None:
    op.drop_column("reviews", "file_count")
    op.drop_column("reviews", "chunk_count")
    op.drop_column("reviews", "pipeline_duration_ms")
    op.drop_column("reviews", "ai_call_count")
    op.drop_column("reviews", "total_completion_tokens")
    op.drop_column("reviews", "total_prompt_tokens")
    op.drop_column("reviews", "summary_markdown")
    op.drop_table("review_ai_calls")
