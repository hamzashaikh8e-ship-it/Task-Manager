"""Add analytics and gamification ledger tables.

Revision ID: 0009_analytics_gamification
Revises: 0008_reminders_notifications_focus
"""
from alembic import op
import sqlalchemy as sa
from app.models.entities import GUID
revision = "0009_analytics_gamification"
down_revision = "0008_reminders_notifications_focus"
branch_labels = None
depends_on = None

def upgrade():
    op.create_table("user_stats",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("total_xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("current_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("longest_streak", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_activity_date", sa.Date()),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", name="uq_user_stats_owner"))
    op.create_index("ix_user_stats_owner_id", "user_stats", ["owner_id"])
    op.create_table("achievements",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("slug", sa.String(64), nullable=False, unique=True),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("description", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False))
    op.create_index("ix_achievements_slug", "achievements", ["slug"])
    op.create_table("user_achievements",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("achievement_id", GUID(), sa.ForeignKey("achievements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("unlocked_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "achievement_id", name="uq_user_achievement"))
    op.create_index("ix_user_achievements_owner_id", "user_achievements", ["owner_id"])
    op.create_index("ix_user_achievements_achievement_id", "user_achievements", ["achievement_id"])
    op.create_table("point_events",
        sa.Column("id", GUID(), primary_key=True),
        sa.Column("owner_id", GUID(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(160), nullable=False),
        sa.Column("source_type", sa.String(32), nullable=False),
        sa.Column("source_id", sa.String(64), nullable=False),
        sa.Column("points", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("owner_id", "event_key", name="uq_point_event_owner_key"))
    op.create_index("ix_point_events_owner_id", "point_events", ["owner_id"])
    op.create_index("ix_point_events_source_type", "point_events", ["source_type"])
    op.create_index("ix_point_events_created_at", "point_events", ["created_at"])

def downgrade():
    op.drop_table("point_events")
    op.drop_table("user_achievements")
    op.drop_table("achievements")
    op.drop_table("user_stats")
