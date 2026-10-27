from sqlalchemy import create_engine, inspect

from app.core.migrations import run_database_migrations


def test_database_migrations_create_schema_and_are_idempotent(tmp_path):
    database_path = tmp_path / "migration-test.db"
    migration_engine = create_engine(f"sqlite:///{database_path}")

    try:
        run_database_migrations(migration_engine)
        tables = set(inspect(migration_engine).get_table_names())
        assert {"alembic_version", "users", "tasks", "focus_sessions", "point_events"} <= tables

        run_database_migrations(migration_engine)
        with migration_engine.connect() as connection:
            revision = connection.exec_driver_sql("SELECT version_num FROM alembic_version").scalar_one()
        assert revision == "0010_auth_sessions"
    finally:
        migration_engine.dispose()
