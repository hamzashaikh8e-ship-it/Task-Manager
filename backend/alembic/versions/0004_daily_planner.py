"""Add saved availability and daily plans.

Revision ID: 0004_daily_planner
Revises: 0003_calendar_scheduling
"""
import sqlalchemy as sa
from alembic import op

from app.models.entities import GUID

revision = "0004_daily_planner"
down_revision = "0003_calendar_scheduling"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "availability_blocks",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("local_start", sa.String(length=5), nullable=True),
        sa.Column("local_end", sa.String(length=5), nullable=True),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("kind IN ('WORKING_HOURS', 'COMMITMENT')", name="ck_availability_kind"),
        sa.CheckConstraint("(kind = 'WORKING_HOURS' AND weekday IS NOT NULL AND local_start IS NOT NULL AND local_end IS NOT NULL AND starts_at IS NULL AND ends_at IS NULL) OR (kind = 'COMMITMENT' AND weekday IS NULL AND local_start IS NULL AND local_end IS NULL AND starts_at IS NOT NULL AND ends_at IS NOT NULL)", name="ck_availability_shape"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_availability_blocks_owner_id", "availability_blocks", ["owner_id"])
    op.create_index("ix_availability_blocks_kind", "availability_blocks", ["kind"])
    op.create_index("ix_availability_blocks_starts_at", "availability_blocks", ["starts_at"])

    op.create_table(
        "daily_plans",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("plan_date", sa.Date(), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("available_minutes", sa.Integer(), nullable=True),
        sa.Column("break_minutes", sa.Integer(), nullable=False),
        sa.Column("break_every_minutes", sa.Integer(), nullable=False),
        sa.Column("generated_at", sa.DateTime(), nullable=False),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("status IN ('DRAFT', 'APPROVED')", name="ck_daily_plan_status"),
        sa.CheckConstraint("break_minutes >= 0 AND break_every_minutes >= 0", name="ck_daily_plan_breaks"),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "plan_date", name="uq_daily_plan_owner_date"),
    )
    op.create_index("ix_daily_plans_owner_id", "daily_plans", ["owner_id"])
    op.create_index("ix_daily_plans_plan_date", "daily_plans", ["plan_date"])

    op.create_table(
        "plan_items",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("plan_id", GUID(), nullable=False),
        sa.Column("task_id", GUID(), nullable=True),
        sa.Column("item_type", sa.String(length=20), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("starts_at", sa.DateTime(), nullable=True),
        sa.Column("ends_at", sa.DateTime(), nullable=True),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("item_type IN ('TASK', 'BREAK', 'COMMITMENT', 'UNSCHEDULED')", name="ck_plan_item_type"),
        sa.CheckConstraint("(starts_at IS NULL AND ends_at IS NULL) OR (starts_at IS NOT NULL AND ends_at IS NOT NULL AND starts_at < ends_at)", name="ck_plan_item_interval"),
        sa.ForeignKeyConstraint(["plan_id"], ["daily_plans.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_plan_items_plan_id", "plan_items", ["plan_id"])
    op.create_index("ix_plan_items_task_id", "plan_items", ["task_id"])
    op.create_index("ix_plan_items_item_type", "plan_items", ["item_type"])
    op.create_index("ix_plan_items_starts_at", "plan_items", ["starts_at"])


def downgrade():
    op.drop_table("plan_items")
    op.drop_table("daily_plans")
    op.drop_table("availability_blocks")
