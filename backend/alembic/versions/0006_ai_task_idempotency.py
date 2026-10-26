"""Add an owner-scoped idempotency key for retried task creates.

Revision ID: 0006_ai_task_idempotency
Revises: 0005_normalize_weekday_indices
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_ai_task_idempotency"
down_revision = "0005_normalize_weekday_indices"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("idempotency_key", sa.String(length=128), nullable=True))
        batch.create_unique_constraint(
            "uq_task_owner_idempotency_key", ["owner_id", "idempotency_key"]
        )


def downgrade():
    with op.batch_alter_table("tasks") as batch:
        batch.drop_constraint("uq_task_owner_idempotency_key", type_="unique")
        batch.drop_column("idempotency_key")
