"""Add booking reminder sent marker.

Revision ID: 0015
Revises: 0013
"""
from alembic import op
import sqlalchemy as sa


revision = "0015"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booking", sa.Column("reminder_sent_at", sa.DateTime(), nullable=True))


def downgrade() -> None:
    op.drop_column("booking", "reminder_sent_at")
