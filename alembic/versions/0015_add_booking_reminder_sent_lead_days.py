"""Add booking reminder sent lead-day markers.

Revision ID: 0015
Revises: 0013
"""
import sqlalchemy as sa
from alembic import op


revision = "0015"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("booking", sa.Column("reminder_sent_lead_days", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("booking", "reminder_sent_lead_days")
