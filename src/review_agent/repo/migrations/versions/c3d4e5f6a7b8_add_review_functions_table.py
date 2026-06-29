"""add_review_functions_table

Revision ID: c3d4e5f6a7b8
Revises: acc0de4340ba
Create Date: 2026-06-24 00:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c3d4e5f6a7b8"
down_revision: str | Sequence[str] | None = "acc0de4340ba"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "review_functions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "review_id",
            sa.String(36),
            sa.ForeignKey("reviews.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("file_path", sa.String(1024), nullable=False),
        sa.Column("function_name", sa.String(255), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("sha", sa.String(64), nullable=False),
        sa.Column("max_severity", sa.String(16), nullable=True),
        sa.Column("finding_count", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column(
            "create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "update_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "review_id",
            "file_path",
            "function_name",
            "start_line",
            name="uq_review_func",
        ),
    )
    op.create_index(
        "idx_rf_file_func",
        "review_functions",
        ["file_path", "function_name"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("idx_rf_file_func", table_name="review_functions")
    op.drop_table("review_functions")
