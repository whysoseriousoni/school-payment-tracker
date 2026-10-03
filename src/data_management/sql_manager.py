"""
Database access primitives: engine, sessions and file-level backup.

The schema is owned by the migrations in `data_management/migrations`, never
by `SQLModel.metadata.create_all()`. This module has no Streamlit dependency so
it can be used from scripts, schedulers and tests.
"""
import sqlite3
from contextlib import contextmanager
from functools import lru_cache
from pathlib import Path
from typing import Iterator, Optional, Union

from sqlalchemy import event
from sqlalchemy.engine import Engine
from sqlmodel import Session, create_engine

from config.settings import BACKUP_DIR, DB_PATH
from helper.clock import now_ist
from helper.logger import get_logger

logger = get_logger(__name__)

PathLike = Union[str, Path]


def apply_connection_pragmas(dbapi_connection: sqlite3.Connection) -> None:
    """Settings that SQLite applies per connection, not per database file."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys = ON")
    cursor.execute("PRAGMA busy_timeout = 30000")
    cursor.close()


_engines_created: set = set()


@lru_cache(maxsize=None)
def _engine_for(db_path: str) -> Engine:
    _engines_created.add(db_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(
        f"sqlite:///{db_path}",
        connect_args={"check_same_thread": False, "timeout": 30},
    )
    event.listen(engine, "connect", lambda conn, _record: apply_connection_pragmas(conn))
    return engine


_active_db_path: Path = DB_PATH


def set_database_path(db_path: PathLike) -> None:
    """Point the application at another database file (tests, restore checks)."""
    global _active_db_path
    _active_db_path = Path(db_path)


def get_database_path() -> Path:
    return _active_db_path


def get_engine(db_path: Optional[PathLike] = None) -> Engine:
    """One shared engine per database file (cached for the process lifetime)."""
    return _engine_for(str(Path(db_path or _active_db_path).resolve()))


def dispose_engines() -> None:
    """Close pooled connections (required before replacing the database file)."""
    for engine_path in list(_engine_cache_keys()):
        _engine_for(engine_path).dispose()


def _engine_cache_keys():
    return [key for key in _engines_created]


@contextmanager
def session_scope(db_path: Optional[PathLike] = None) -> Iterator[Session]:
    """Transactional session: commits on success, rolls back and re-raises on error."""
    session = Session(get_engine(db_path), expire_on_commit=False)
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        logger.exception("Database transaction rolled back")
        raise
    finally:
        session.close()


def backup_database(
    label: str = "manual",
    destination_dir: Optional[PathLike] = None,
    db_path: Optional[PathLike] = None,
) -> Path:
    """
    Consistent snapshot of the live database using SQLite's online backup API
    (safe while the app is running). Returns the path of the backup file.
    """
    source_path = Path(db_path or _active_db_path)
    target_dir = Path(destination_dir or BACKUP_DIR)
    target_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{source_path.stem}_{label}_{now_ist():%Y%m%d_%H%M%S_%f}"
    target_path, counter = target_dir / f"{stem}.db", 2
    while target_path.exists():  # never overwrite an earlier backup
        target_path, counter = target_dir / f"{stem}_{counter}.db", counter + 1

    source = sqlite3.connect(source_path)
    destination = sqlite3.connect(target_path)
    try:
        with destination:
            source.backup(destination)
    finally:
        destination.close()
        source.close()
    logger.info("Database backed up to %s", target_path)
    return target_path
