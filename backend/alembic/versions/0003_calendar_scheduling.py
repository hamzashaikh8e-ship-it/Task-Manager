"""Add scheduled task intervals for the calendar.

Revision ID: 0003_calendar_scheduling
Revises: 0002_task_management
"""
import sqlalchemy as sa
from alembic import op

revision = "0003_calendar_scheduling"
down_revision = "0002_task_management"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tasks", sa.Column("scheduled_start", sa.DateTime(), nullable=True))
    op.add_column("tasks", sa.Column("scheduled_end", sa.DateTime(), nullable=True))
    op.create_index("ix_tasks_scheduled_start", "tasks", ["scheduled_start"])


def downgrade():
    op.drop_index("ix_tasks_scheduled_start", table_name="tasks")
    op.drop_column("tasks", "scheduled_end")
    op.drop_column("tasks", "scheduled_start")
