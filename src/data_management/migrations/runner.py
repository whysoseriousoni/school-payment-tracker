"""
Minimal, dependency-free migration runner.

Each migration is a Python module exposing:
    VERSION: int        unique, increasing
    NAME: str           short description
    upgrade(conn, log)  applies the change using a sqlite3 connection

Guarantees:
  * A backup of the database is taken before any pending migration runs.
  * Each migration runs inside its own transaction and is rolled back on error.
  * `PRAGMA foreign_key_check` must pass before a migration is committed.
  * Applied versions are recorded in `schema_migrations`, so re-running is a no-op.
"""
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Callable, List, Optional, Union

from data_management.sql_manager import backup_database, get_database_path
from helper.clock import now_ist
from helper.logger import get_logger

logger = get_logger(__name__)

LogFn = Callable[[str], None]


class MigrationError(RuntimeError):
    """Raised when a migration fails; the database is left at the previous version."""


@dataclass(frozen=True)
class AppliedMigration:
    version: int
    name: str
    messages: List[str]


def execute_script(conn: sqlite3.Connection, script: str) -> None:
    """
    Run a multi-statement SQL script inside the current transaction.
    (`sqlite3.executescript` would COMMIT first, breaking atomicity.)
    Handles statements containing ';' such as CREATE TRIGGER ... END;
    """
    buffer = ""
    for line in script.splitlines(keepends=True):
        if not buffer and line.strip().startswith("--"):
            continue
        buffer += line
        if sqlite3.complete_statement(buffer):
            conn.execute(buffer)
            buffer = ""
    if buffer.strip():
        raise MigrationError(f"Incomplete SQL statement in script: {buffer.strip()[:120]}")


def _ensure_version_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        "CREATE TABLE IF NOT EXISTS schema_migrations ("
        " version INTEGER PRIMARY KEY,"
        " name TEXT NOT NULL,"
        " applied_on TEXT NOT NULL)"
    )


def applied_versions(conn: sqlite3.Connection) -> List[int]:
    _ensure_version_table(conn)
    return [row[0] for row in conn.execute("SELECT version FROM schema_migrations ORDER BY version")]


def _has_user_tables(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table'"
        " AND name NOT LIKE 'sqlite_%' AND name <> 'schema_migrations'"
    ).fetchone()
    return row[0] > 0


def _registered_migrations() -> List[ModuleType]:
    from data_management.migrations import MIGRATIONS

    versions = [module.VERSION for module in MIGRATIONS]
    if versions != sorted(set(versions)):
        raise MigrationError(f"Migration versions must be unique and increasing: {versions}")
    return list(MIGRATIONS)


def run_pending_migrations(
    db_path: Optional[Union[str, Path]] = None,
    backup_dir: Optional[Union[str, Path]] = None,
) -> List[AppliedMigration]:
    """Apply every migration not yet recorded. Returns what was applied."""
    if sqlite3.sqlite_version_info < (3, 35, 0):  # UPSERT ... RETURNING is used for receipt numbers
        raise MigrationError(f"SQLite 3.35 or newer is required; this Python has {sqlite3.sqlite_version}. "
                             "Install a current Python 3.10.x release.")
    db_path = Path(db_path or get_database_path())
    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path, isolation_level=None)  # explicit transactions below
    conn.row_factory = sqlite3.Row
    try:
        # Foreign keys are verified explicitly with foreign_key_check before commit;
        # keeping enforcement off allows table rebuilds inside a migration.
        conn.execute("PRAGMA foreign_keys = OFF")
        done = set(applied_versions(conn))
        pending = [module for module in _registered_migrations() if module.VERSION not in done]
        if not pending:
            return []

        if _has_user_tables(conn):
            backup_database(
                label=f"pre_migration_v{pending[0].VERSION:03d}",
                destination_dir=backup_dir,
                db_path=db_path,
            )

        applied: List[AppliedMigration] = []
        for module in pending:
            applied.append(_apply_one(conn, module))
        return applied
    finally:
        conn.close()


def _apply_one(conn: sqlite3.Connection, module: ModuleType) -> AppliedMigration:
    messages: List[str] = []

    def log(message: str) -> None:
        messages.append(message)
        logger.info("[migration %03d] %s", module.VERSION, message)

    logger.info("Applying migration %03d: %s", module.VERSION, module.NAME)
    conn.execute("BEGIN IMMEDIATE")
    try:
        module.upgrade(conn, log)
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            details = [tuple(row) for row in violations[:10]]
            raise MigrationError(f"Foreign key violations after migration: {details}")
        conn.execute(
            "INSERT INTO schema_migrations (version, name, applied_on) VALUES (?, ?, ?)",
            (module.VERSION, module.NAME, now_ist().strftime("%Y-%m-%d %H:%M:%S.%f")),
        )
        conn.execute("COMMIT")
    except Exception as error:
        conn.execute("ROLLBACK")
        logger.exception("Migration %03d failed and was rolled back", module.VERSION)
        if isinstance(error, MigrationError):
            raise
        raise MigrationError(f"Migration {module.VERSION:03d} ({module.NAME}) failed: {error}") from error
    return AppliedMigration(version=module.VERSION, name=module.NAME, messages=messages)
