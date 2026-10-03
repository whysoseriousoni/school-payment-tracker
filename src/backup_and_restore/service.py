"""
Backup and restore.

Two formats:
  * .db snapshot  - exact copy (SQLite online backup API); the safest restore.
  * Excel export  - every table on its own sheet, readable by humans.

Every restore validates the file first, takes a "pre_restore" snapshot of the
current data, and applies everything in one transaction.
"""
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from io import BytesIO
from pathlib import Path
from typing import Dict, List, Optional

import pandas as pd

from config import settings
from data_management.migrations import MIGRATIONS
from data_management.migrations.runner import run_pending_migrations
from data_management.sql_manager import backup_database, dispose_engines, get_database_path
from data_management.services.errors import BusinessRuleError
from helper.clock import now_ist
from helper.logger import get_logger

logger = get_logger(__name__)

META_SHEET = "_meta"
AUTO_LABEL = "weekly"

# Parent tables first: the order used for inserting during an Excel restore.
TABLE_ORDER = [
    "academic_year", "identifier", "student", "guardian", "student_guardian", "student_enrollment",
    "fee_structure", "student_fee_due", "receipt_counter", "payment", "payment_allocation",
    "app_user", "app_setting",
]
_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f"


@dataclass
class BackupFile:
    name: str
    path: Path
    size_kb: float
    created: datetime


@dataclass
class RestoreResult:
    rows: Dict[str, int] = field(default_factory=dict)
    safety_backup: Optional[Path] = None


def latest_schema_version() -> int:
    return MIGRATIONS[-1].VERSION


def backup_dir() -> Path:
    return Path(settings.BACKUP_DIR)


# ---------- .db snapshots ----------

def create_backup(label: str = "manual") -> Path:
    return backup_database(label=label, destination_dir=backup_dir())


def list_backups() -> List[BackupFile]:
    folder = backup_dir()
    if not folder.exists():
        return []
    files = [
        BackupFile(name=path.name, path=path, size_kb=round(path.stat().st_size / 1024, 1),
                   created=datetime.fromtimestamp(path.stat().st_mtime))
        for path in folder.glob("*.db")
    ]
    return sorted(files, key=lambda item: item.created, reverse=True)


def _automatic_backups() -> List[BackupFile]:
    return [item for item in list_backups() if f"_{AUTO_LABEL}_" in item.name]


def prune_automatic_backups(keep: int = settings.AUTO_BACKUP_KEEP) -> int:
    removed = 0
    for item in _automatic_backups()[keep:]:
        item.path.unlink(missing_ok=True)
        removed += 1
    return removed


def run_scheduled_backup_if_due(now: Optional[datetime] = None) -> Optional[Path]:
    """Weekly backup: runs when the last automatic one is older than the interval."""
    now = now or datetime.now()
    recent = _automatic_backups()
    if recent and now - recent[0].created < timedelta(days=settings.AUTO_BACKUP_INTERVAL_DAYS):
        return None
    path = create_backup(AUTO_LABEL)
    prune_automatic_backups()
    if email_configured():
        try:
            send_backup_email([path], subject_suffix="weekly")
        except Exception:  # e-mail failure must never lose the local backup
            logger.exception("Weekly backup e-mail failed")
    return path


# ---------- Excel export ----------

def _table_names(conn: sqlite3.Connection) -> List[str]:
    existing = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    return [table for table in TABLE_ORDER if table in existing]


def export_excel_backup() -> bytes:
    conn = sqlite3.connect(get_database_path())
    try:
        version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0]
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            tables = _table_names(conn)
            meta = pd.DataFrame({"key": ["schema_version", "exported_on", "tables"],
                                 "value": [str(version), now_ist().isoformat(sep=" "), ",".join(tables)]})
            meta.to_excel(writer, sheet_name=META_SHEET, index=False)
            for table in tables:
                frame = pd.read_sql_query(f'SELECT * FROM "{table}"', conn)
                frame.to_excel(writer, sheet_name=table, index=False)
        return buffer.getvalue()
    finally:
        conn.close()


# ---------- restore ----------

def _column_types(conn: sqlite3.Connection, table: str) -> Dict[str, str]:
    return {row[1]: (row[2] or "").upper() for row in conn.execute(f'PRAGMA table_info("{table}")')}


def _to_db_value(value, column_type: str):
    if value is None or (isinstance(value, float) and pd.isna(value)) or value is pd.NaT:
        return None
    if isinstance(value, str) and value == "":
        return None
    if column_type == "INTEGER":
        if isinstance(value, bool):
            return int(value)
        number = float(value)
        if not number.is_integer():
            raise BusinessRuleError(f"Expected a whole number, found {value!r}")
        return int(number)
    if column_type == "DATE" and hasattr(value, "strftime"):
        return value.strftime("%Y-%m-%d")
    if column_type == "DATETIME" and hasattr(value, "strftime"):
        return value.strftime(_DATETIME_FORMAT)
    if hasattr(value, "item"):
        value = value.item()
    return str(value) if column_type in ("TEXT", "DATE", "DATETIME") else value


def _records(frame: pd.DataFrame, types: Dict[str, str]) -> List[dict]:
    frame = frame.astype(object).where(frame.notna(), None)
    return [{column: _to_db_value(value, types[column]) for column, value in row.items()}
            for row in frame.to_dict("records")]


def _insert(conn: sqlite3.Connection, table: str, record: dict) -> None:
    columns = ", ".join(f'"{column}"' for column in record)
    placeholders = ", ".join("?" for _ in record)
    conn.execute(f'INSERT INTO "{table}" ({columns}) VALUES ({placeholders})', list(record.values()))


def restore_from_excel(content: bytes) -> RestoreResult:
    try:
        sheets = pd.read_excel(BytesIO(content), sheet_name=None, dtype=object)
    except Exception as error:
        raise BusinessRuleError(f"Could not read the Excel file: {error}") from error
    if META_SHEET not in sheets:
        raise BusinessRuleError("This is not a backup exported by this application (no _meta sheet)")
    meta = dict(zip(sheets[META_SHEET]["key"].astype(str), sheets[META_SHEET]["value"].astype(str)))
    if meta.get("schema_version") != str(latest_schema_version()):
        raise BusinessRuleError(
            f"Backup schema version {meta.get('schema_version')} does not match this application "
            f"({latest_schema_version()}). Restore a .db backup instead - it is upgraded automatically.")

    conn = sqlite3.connect(get_database_path(), isolation_level=None)
    try:
        tables = _table_names(conn)
        missing = [table for table in tables if table not in sheets]
        if missing:
            raise BusinessRuleError(f"Backup is missing sheets: {', '.join(missing)}")
        types = {table: _column_types(conn, table) for table in tables}
        for table in tables:
            unknown = set(sheets[table].columns) - set(types[table])
            if unknown:
                raise BusinessRuleError(f"Sheet {table} has unknown columns: {', '.join(sorted(unknown))}")
        data = {table: _records(sheets[table], types[table]) for table in tables}
    finally:
        conn.close()

    result = RestoreResult(safety_backup=create_backup("pre_restore"))
    dispose_engines()
    conn = sqlite3.connect(get_database_path(), isolation_level=None)
    try:
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.execute("BEGIN IMMEDIATE")
        # Payments are normally undeletable; lift that rule only inside this transaction.
        guard_sql = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'trigger' AND name = 'trg_payment_no_delete'").fetchone()
        conn.execute("DROP TRIGGER IF EXISTS trg_payment_no_delete")
        for table in reversed(tables):
            conn.execute(f'DELETE FROM "{table}"')
        allocations_by_payment: Dict[int, List[dict]] = {}
        for record in data.get("payment_allocation", []):
            allocations_by_payment.setdefault(record["payment_id"], []).append(record)
        for table in tables:
            if table == "payment_allocation":
                continue
            if table == "payment":
                # Replay receipts in creation order: insert, allocate, then void - so every
                # money-integrity trigger checks the restored history exactly as it happened.
                for record in sorted(data[table], key=lambda r: r["id"]):
                    void_fields = {k: record[k] for k in ("is_voided", "void_reason", "voided_on", "voided_by")}
                    _insert(conn, table, {**record, "is_voided": 0, "void_reason": None,
                                          "voided_on": None, "voided_by": None})
                    for allocation in allocations_by_payment.get(record["id"], []):
                        _insert(conn, "payment_allocation", allocation)
                    if void_fields["is_voided"]:
                        conn.execute("UPDATE payment SET is_voided = 1, void_reason = ?, voided_on = ?, voided_by = ?"
                                     " WHERE id = ?", (void_fields["void_reason"], void_fields["voided_on"],
                                                       void_fields["voided_by"], record["id"]))
                result.rows["payment_allocation"] = len(data.get("payment_allocation", []))
            else:
                for record in data[table]:
                    _insert(conn, table, record)
            result.rows[table] = len(data[table])
        if guard_sql:
            conn.execute(guard_sql[0])
        violations = conn.execute("PRAGMA foreign_key_check").fetchall()
        if violations:
            raise BusinessRuleError(f"Backup has broken references, e.g. {[tuple(v) for v in violations[:3]]}")
        conn.execute("COMMIT")
    except sqlite3.IntegrityError as error:
        conn.execute("ROLLBACK")
        raise BusinessRuleError(f"Backup data failed validation and was not restored: {error}") from error
    except Exception:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    logger.info("Restored from Excel backup: %s", result.rows)
    return result


def _validate_db_file(path: Path) -> int:
    try:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise BusinessRuleError("The backup file is damaged (integrity check failed)")
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if "schema_migrations" not in tables:
                raise BusinessRuleError("This is not a backup made by this application")
            version = conn.execute("SELECT MAX(version) FROM schema_migrations").fetchone()[0] or 0
        finally:
            conn.close()
    except sqlite3.DatabaseError as error:
        raise BusinessRuleError(f"Not a valid database file: {error}") from error
    if version > latest_schema_version():
        raise BusinessRuleError("This backup is from a newer version of the application; update the app first")
    return version


def restore_from_db_file(content: bytes) -> RestoreResult:
    with tempfile.TemporaryDirectory() as folder:
        uploaded = Path(folder) / "uploaded.db"
        uploaded.write_bytes(content)
        _validate_db_file(uploaded)
        result = RestoreResult(safety_backup=create_backup("pre_restore"))
        dispose_engines()
        source = sqlite3.connect(uploaded)
        target = sqlite3.connect(get_database_path())
        try:
            with target:
                source.backup(target)
        finally:
            source.close()
            target.close()
    run_pending_migrations(db_path=get_database_path(), backup_dir=backup_dir())
    conn = sqlite3.connect(get_database_path())
    try:
        result.rows = {table: conn.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                       for table in _table_names(conn)}
    finally:
        conn.close()
    logger.info("Restored from .db backup: %s", result.rows)
    return result


# ---------- e-mail ----------

def email_configured() -> bool:
    return bool(settings.SMTP_HOST and settings.BACKUP_EMAIL_TO)


def send_backup_email(paths: List[Path], subject_suffix: str = "manual") -> None:
    import smtplib
    from email.message import EmailMessage

    if not email_configured():
        raise BusinessRuleError("E-mail is not configured (set SPT_SMTP_HOST and SPT_BACKUP_EMAIL_TO)")
    message = EmailMessage()
    message["Subject"] = f"School payment tracker backup ({subject_suffix}) {now_ist():%d %b %Y %H:%M}"
    message["From"] = settings.SMTP_SENDER or settings.SMTP_USER
    message["To"] = settings.BACKUP_EMAIL_TO
    message.set_content("Attached: database backup. Keep it safe; restore it from Admin > Backup & Restore.")
    for path in paths:
        message.add_attachment(Path(path).read_bytes(), maintype="application", subtype="octet-stream",
                               filename=Path(path).name)
    with smtplib.SMTP(settings.SMTP_HOST, settings.SMTP_PORT, timeout=60) as server:
        server.starttls()
        if settings.SMTP_USER:
            server.login(settings.SMTP_USER, settings.SMTP_PASSWORD)
        server.send_message(message)
    logger.info("Backup e-mailed to %s", settings.BACKUP_EMAIL_TO)
