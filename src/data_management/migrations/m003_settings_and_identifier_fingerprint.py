"""
Migration 003 - school settings and duplicate-safe identifiers.

* app_setting: key/value settings editable from the Admin page (school name,
  address, phone shown on receipts and reports).
* identifier.fingerprint: keyed HMAC of the full number, so the same Aadhaar
  cannot be registered twice without ever storing it in plain text.
"""
import sqlite3

from data_management.migrations.runner import LogFn, execute_script

VERSION = 3
NAME = "settings and identifier fingerprint"

SCHEMA_SQL = """
CREATE TABLE app_setting (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL,
    updated_on  DATETIME NOT NULL
);

ALTER TABLE identifier ADD COLUMN fingerprint TEXT;
CREATE UNIQUE INDEX ux_identifier_fingerprint ON identifier (fingerprint) WHERE fingerprint IS NOT NULL;
"""


def upgrade(conn: sqlite3.Connection, log: LogFn) -> None:
    execute_script(conn, SCHEMA_SQL)
    log("Created app_setting and identifier.fingerprint")
