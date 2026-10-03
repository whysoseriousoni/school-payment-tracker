import sqlite3
from pathlib import Path

import pytest

from data_management.migrations.runner import run_pending_migrations

FIXTURES = Path(__file__).parent / "fixtures"


def _connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@pytest.fixture
def prototype_db(tmp_path) -> Path:
    """A database in the original prototype shape, holding the real prototype rows."""
    path = tmp_path / "prototype.db"
    conn = sqlite3.connect(path)
    conn.executescript((FIXTURES / "prototype_database.sql").read_text(encoding="utf-8"))
    conn.close()
    return path


@pytest.fixture
def migrated_db(prototype_db, tmp_path) -> Path:
    run_pending_migrations(db_path=prototype_db, backup_dir=tmp_path / "backups")
    return prototype_db


@pytest.fixture
def fresh_db(tmp_path) -> Path:
    path = tmp_path / "fresh.db"
    run_pending_migrations(db_path=path, backup_dir=tmp_path / "backups")
    return path


@pytest.fixture
def connect():
    connections = []

    def _open(path: Path) -> sqlite3.Connection:
        conn = _connect(path)
        connections.append(conn)
        return conn

    yield _open
    for conn in connections:
        conn.close()


@pytest.fixture
def app_db(migrated_db, tmp_path, monkeypatch):
    """Services pointed at a migrated copy of the prototype data, with a throwaway encryption key."""
    from data_management.sql_manager import get_database_path, set_database_path

    monkeypatch.setenv("SPT_IDENTIFIER_KEY_PATH", str(tmp_path / "secrets" / "identifier.key"))
    monkeypatch.delenv("SPT_IDENTIFIER_KEY", raising=False)
    previous = get_database_path()
    set_database_path(migrated_db)
    yield migrated_db
    set_database_path(previous)


@pytest.fixture
def fresh_app_db(fresh_db, tmp_path, monkeypatch):
    from data_management.sql_manager import get_database_path, set_database_path

    monkeypatch.setenv("SPT_IDENTIFIER_KEY_PATH", str(tmp_path / "secrets" / "identifier.key"))
    previous = get_database_path()
    set_database_path(fresh_db)
    yield fresh_db
    set_database_path(previous)
