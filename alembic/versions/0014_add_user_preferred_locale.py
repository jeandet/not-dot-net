"""Add preferred locale to users.

Revision ID: 0014
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("user", sa.Column("preferred_locale", sa.String(5), nullable=True))


def downgrade() -> None:
    op.drop_column("user", "preferred_locale")
