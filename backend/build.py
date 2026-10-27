"""Apply database migrations during Vercel's build, not function startup."""

from app.core.migrations import run_database_migrations


def main() -> None:
    run_database_migrations()


if __name__ == "__main__":
    main()
