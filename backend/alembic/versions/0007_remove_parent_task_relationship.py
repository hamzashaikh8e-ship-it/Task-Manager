"""Remove parent-task links while preserving all task records.

Existing subtasks remain as ordinary tasks with every non-parent field intact.
Revision ID: 0007_remove_parent_task_relationship
Revises: 0006_ai_task_idempotency
"""
from alembic import op

revision = "0007_remove_parent_task_relationship"
down_revision = "0006_ai_task_idempotency"
branch_labels = None
depends_on = None


def upgrade():
    # SQLite batch mode recreates the table, retaining all rows and values except
    # the obsolete relationship column. PostgreSQL executes the same DDL safely.
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_parent_task_id")
        batch.drop_constraint("fk_tasks_parent_task_id_tasks", type_="foreignkey")
        batch.drop_column("parent_task_id")


def downgrade():
    # Relationships are intentionally not restored: the migration preserves
    # task records but irreversibly removes the old parent-child associations.
    from app.models.entities import GUID
    import sqlalchemy as sa
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("parent_task_id", GUID(), nullable=True))
        batch.create_foreign_key("fk_tasks_parent_task_id_tasks", "tasks", ["parent_task_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_tasks_parent_task_id", ["parent_task_id"])
