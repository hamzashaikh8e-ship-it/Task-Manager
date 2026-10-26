"""Add task reminders, in-app notifications, and focus sessions.

Revision ID: 0008_reminders_notifications_focus
Revises: 0007_remove_parent_task_relationship
"""
from alembic import op
import sqlalchemy as sa
from app.models.entities import GUID
revision="0008_reminders_notifications_focus"
down_revision="0007_remove_parent_task_relationship"
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("reminder_enabled",sa.Boolean(),nullable=False,server_default=sa.false()))
        batch.add_column(sa.Column("reminder_lead_minutes",sa.Integer(),nullable=False,server_default="30"))
    op.create_table("reminders",
        sa.Column("id",GUID(),primary_key=True),sa.Column("owner_id",GUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("task_id",GUID(),sa.ForeignKey("tasks.id",ondelete="CASCADE"),nullable=False),sa.Column("due_at",sa.DateTime(),nullable=False),
        sa.Column("status",sa.String(16),nullable=False,server_default="PENDING"),sa.Column("delivered_at",sa.DateTime()),sa.Column("updated_at",sa.DateTime(),nullable=False),
        sa.UniqueConstraint("task_id",name="uq_reminder_task"))
    op.create_index("ix_reminders_owner_id","reminders",["owner_id"]);op.create_index("ix_reminders_task_id","reminders",["task_id"]);op.create_index("ix_reminders_due_at","reminders",["due_at"]);op.create_index("ix_reminders_status","reminders",["status"])
    op.create_table("notifications",
        sa.Column("id",GUID(),primary_key=True),sa.Column("owner_id",GUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("task_id",GUID(),sa.ForeignKey("tasks.id",ondelete="SET NULL")),sa.Column("reminder_id",GUID(),sa.ForeignKey("reminders.id",ondelete="SET NULL")),
        sa.Column("dedupe_key",sa.String(200),nullable=False),sa.Column("title",sa.String(200),nullable=False),sa.Column("message",sa.String(500),nullable=False),
        sa.Column("created_at",sa.DateTime(),nullable=False),sa.Column("read_at",sa.DateTime()),sa.UniqueConstraint("owner_id","dedupe_key",name="uq_notification_owner_dedupe"))
    op.create_index("ix_notifications_owner_id","notifications",["owner_id"]);op.create_index("ix_notifications_task_id","notifications",["task_id"]);op.create_index("ix_notifications_reminder_id","notifications",["reminder_id"]);op.create_index("ix_notifications_created_at","notifications",["created_at"]);op.create_index("ix_notifications_read_at","notifications",["read_at"])
    op.create_table("focus_sessions",
        sa.Column("id",GUID(),primary_key=True),sa.Column("owner_id",GUID(),sa.ForeignKey("users.id",ondelete="CASCADE"),nullable=False),
        sa.Column("task_id",GUID(),sa.ForeignKey("tasks.id",ondelete="SET NULL")),sa.Column("kind",sa.String(10),nullable=False),sa.Column("status",sa.String(16),nullable=False),
        sa.Column("planned_minutes",sa.Integer(),nullable=False),sa.Column("elapsed_seconds",sa.Integer(),nullable=False,server_default="0"),sa.Column("started_at",sa.DateTime(),nullable=False),
        sa.Column("paused_at",sa.DateTime()),sa.Column("ended_at",sa.DateTime()),sa.Column("created_at",sa.DateTime(),nullable=False),
        sa.CheckConstraint("kind IN ('FOCUS','BREAK')",name="ck_focus_session_kind"),sa.CheckConstraint("status IN ('ACTIVE','PAUSED','COMPLETED','CANCELLED')",name="ck_focus_session_status"),sa.CheckConstraint("planned_minutes BETWEEN 1 AND 240",name="ck_focus_planned_minutes"),sa.CheckConstraint("elapsed_seconds >= 0",name="ck_focus_elapsed_seconds"))
    op.create_index("ix_focus_sessions_owner_id","focus_sessions",["owner_id"]);op.create_index("ix_focus_sessions_task_id","focus_sessions",["task_id"]);op.create_index("ix_focus_sessions_status","focus_sessions",["status"]);op.create_index("ix_focus_sessions_created_at","focus_sessions",["created_at"])

def downgrade():
    op.drop_table("focus_sessions");op.drop_table("notifications");op.drop_table("reminders")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_column("reminder_lead_minutes");batch.drop_column("reminder_enabled")
