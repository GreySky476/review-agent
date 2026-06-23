"""add rule.embedding, rule.embedding_model, rule.project_id

Revision ID: a1b2c3d4e5f6
Revises: 899e3377030d
Create Date: 2026-06-12 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: str | Sequence[str] | None = "899e3377030d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("rules", sa.Column("embedding", sa.Text(), nullable=True))
    op.add_column("rules", sa.Column("embedding_model", sa.String(64), nullable=True))
    op.add_column("rules", sa.Column("project_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_rules_project_id",
        "rules",
        "projects",
        ["project_id"],
        ["id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint("fk_rules_project_id", "rules", type_="foreignkey")
    op.drop_column("rules", "project_id")
    op.drop_column("rules", "embedding_model")
    op.drop_column("rules", "embedding")
