"""Command line entry point:  python -m data_management.migrations"""
import sys

from data_management.migrations.runner import MigrationError, run_pending_migrations
from helper.logger import configure_logging


def main() -> int:
    configure_logging()
    try:
        applied = run_pending_migrations()
    except MigrationError as error:
        print(f"Migration failed, database unchanged: {error}", file=sys.stderr)
        return 1
    if not applied:
        print("Database is up to date.")
    for migration in applied:
        print(f"Applied {migration.version:03d} - {migration.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
