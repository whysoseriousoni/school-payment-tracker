"""
Ordered registry of schema migrations.

To add a migration: create mNNN_description.py with VERSION, NAME and
upgrade(conn, log), then append it to MIGRATIONS. Never edit a migration that
has already been applied to a real database.
"""
from data_management.migrations import (
    m001_core_schema,
    m002_import_prototype_data,
    m003_settings_and_identifier_fingerprint,
    m004_fee_plans_and_flexible_payment,
)

MIGRATIONS = [
    m001_core_schema,
    m002_import_prototype_data,
    m003_settings_and_identifier_fingerprint,
    m004_fee_plans_and_flexible_payment,
]
