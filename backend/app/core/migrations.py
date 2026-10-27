"""Run Alembic migrations against the configured database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text

from app.core.database import engine as configured_engine


_POSTGRES_MIGRATION_LOCK = 1_207_338_067


def run_database_migrations(engine=None) -> None:
    """Upgrade to Alembic head, serializing concurrent PostgreSQL cold starts.

    The same connection holds a session-level advisory lock and is passed into
    Alembic, so parallel Vercel function instances cannot race schema changes.
    """
    migration_root = Path(__file__).resolve().parents[2]
    config = Config(str(migration_root / "alembic.ini"))
    config.set_main_option("script_location", str(migration_root / "alembic"))

    database_engine = engine or configured_engine
    with database_engine.connect() as connection:
        is_postgres = connection.dialect.name == "postgresql"
        if is_postgres:
            connection.execute(
                text("SELECT pg_advisory_lock(:lock_key)"),
                {"lock_key": _POSTGRES_MIGRATION_LOCK},
            )
            connection.commit()

        try:
            config.attributes["connection"] = connection
            command.upgrade(config, "head")
        finally:
            if is_postgres:
                if connection.in_transaction():
                    connection.rollback()
                connection.execute(
                    text("SELECT pg_advisory_unlock(:lock_key)"),
                    {"lock_key": _POSTGRES_MIGRATION_LOCK},
                )
                connection.commit()
