"""Add categories, subtask links, and task dependencies.

Revision ID: 0002_task_management
Revises: 0001_initial
"""
import uuid

import sqlalchemy as sa
from alembic import op

from app.models.entities import GUID

revision = "0002_task_management"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "categories",
        sa.Column("id", GUID(), nullable=False),
        sa.Column("owner_id", GUID(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "name", name="uq_category_owner_name"),
    )
    op.create_index("ix_categories_owner_id", "categories", ["owner_id"])
    with op.batch_alter_table("tasks") as batch:
        batch.add_column(sa.Column("parent_task_id", GUID(), nullable=True))
        batch.create_foreign_key("fk_tasks_parent_task_id_tasks", "tasks", ["parent_task_id"], ["id"], ondelete="SET NULL")
        batch.create_index("ix_tasks_parent_task_id", ["parent_task_id"])

    op.create_table(
        "task_dependencies",
        sa.Column("task_id", GUID(), nullable=False),
        sa.Column("depends_on_id", GUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("task_id <> depends_on_id", name="ck_task_dependency_not_self"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["depends_on_id"], ["tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_id", "depends_on_id"),
    )

    connection = op.get_bind()
    legacy_tasks = sa.table(
        "tasks",
        sa.column("owner_id", GUID()),
        sa.column("category", sa.String()),
    )
    category_table = sa.table(
        "categories",
        sa.column("id", GUID()),
        sa.column("owner_id", GUID()),
        sa.column("name", sa.String()),
        sa.column("created_at", sa.DateTime()),
    )
    rows = connection.execute(sa.select(legacy_tasks.c.owner_id, legacy_tasks.c.category).where(legacy_tasks.c.category.isnot(None)).distinct()).fetchall()
    seen = set()
    for owner_id, name in rows:
        key = (owner_id, name.casefold())
        if key in seen:
            continue
        seen.add(key)
        connection.execute(category_table.insert().values(id=uuid.uuid4(), owner_id=owner_id, name=name, created_at=sa.func.now()))


def downgrade():
    op.drop_table("task_dependencies")
    with op.batch_alter_table("tasks") as batch:
        batch.drop_index("ix_tasks_parent_task_id")
        batch.drop_constraint("fk_tasks_parent_task_id_tasks", type_="foreignkey")
        batch.drop_column("parent_task_id")
    op.drop_index("ix_categories_owner_id", table_name="categories")
    op.drop_table("categories")
