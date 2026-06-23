"""add PullRequestModel.last_reviewed_sha, last_review_id

Revision ID: b2c3d4e5f6a7
Revises: a1b2c3d4e5f6
Create Date: 2026-06-14 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "b2c3d4e5f6a7"
down_revision: str | Sequence[str] | None = "a1b2c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("pull_requests", sa.Column("last_reviewed_sha", sa.String(64), nullable=True))
    op.add_column(
        "pull_requests",
        sa.Column("last_review_id", sa.String(36), sa.ForeignKey("reviews.id"), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("pull_requests", "last_review_id")
    op.drop_column("pull_requests", "last_reviewed_sha")
