"""Add a nullable display name to accounts."""

import sqlalchemy as sa
from alembic import op

revision = "0001_add_display_name"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("accounts", sa.Column("display_name", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("accounts", "display_name")
