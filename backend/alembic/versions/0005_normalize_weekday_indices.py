"""Normalize saved working-hour weekdays to Monday=0 through Sunday=6.

Revision ID: 0005_normalize_weekday_indices
Revises: 0004_daily_planner
"""
from alembic import op
import sqlalchemy as sa

revision = "0005_normalize_weekday_indices"
down_revision = "0004_daily_planner"
branch_labels = None
depends_on = None


def upgrade():
    # The first planner UI version persisted JavaScript's Sunday=0 convention.
    # Convert those rows to Python date.weekday() while preserving the weekday
    # the user selected. Fixed commitments and plans are unaffected.
    op.execute(sa.text("""
        UPDATE availability_blocks
        SET weekday = CASE weekday
            WHEN 0 THEN 6
            WHEN 1 THEN 0
            WHEN 2 THEN 1
            WHEN 3 THEN 2
            WHEN 4 THEN 3
            WHEN 5 THEN 4
            WHEN 6 THEN 5
            ELSE weekday
        END
        WHERE kind = 'WORKING_HOURS' AND weekday BETWEEN 0 AND 6
    """))


def downgrade():
    op.execute(sa.text("""
        UPDATE availability_blocks
        SET weekday = CASE weekday
            WHEN 0 THEN 1
            WHEN 1 THEN 2
            WHEN 2 THEN 3
            WHEN 3 THEN 4
            WHEN 4 THEN 5
            WHEN 5 THEN 6
            WHEN 6 THEN 0
            ELSE weekday
        END
        WHERE kind = 'WORKING_HOURS' AND weekday BETWEEN 0 AND 6
    """))
