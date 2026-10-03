"""
Central application settings.

Every path is resolved from the project root, so the app behaves the same no
matter which folder it is launched from. Paths can be overridden with
environment variables (useful for tests, Docker volumes, or a second install).
"""
import os
from pathlib import Path
from zoneinfo import ZoneInfo

PROJECT_ROOT: Path = Path(__file__).resolve().parent.parent

DATA_DIR: Path = Path(os.environ.get("SPT_DATA_DIR", PROJECT_ROOT / "data_store"))
DB_PATH: Path = Path(os.environ.get("SPT_DB_PATH", DATA_DIR / "database.db"))
BACKUP_DIR: Path = Path(os.environ.get("SPT_BACKUP_DIR", DATA_DIR / "backups"))
LOG_DIR: Path = Path(os.environ.get("SPT_LOG_DIR", PROJECT_ROOT / "logs"))

# Needs the `tzdata` package on Windows.
TIMEZONE = ZoneInfo("Asia/Kolkata")

# School operation year runs June -> May; financial year runs April -> March.
ACADEMIC_YEAR_START_MONTH: int = 6
FINANCIAL_YEAR_START_MONTH: int = 4

RECEIPT_PREFIX: str = "RCPT"

# Encryption key for Aadhaar numbers. Keep it OUT of data_store so database
# backups never contain the key. Back this file up separately and safely.
SECRETS_DIR: Path = Path(os.environ.get("SPT_SECRETS_DIR", PROJECT_ROOT / "secrets"))
IDENTIFIER_KEY_PATH: Path = SECRETS_DIR / "identifier.key"

# A month's fee becomes overdue on this day of the month.
FEE_DUE_DAY: int = int(os.environ.get("SPT_FEE_DUE_DAY", "10"))

# Automatic backups.
AUTO_BACKUP_INTERVAL_DAYS: int = 7
AUTO_BACKUP_KEEP: int = 12

# Optional e-mail delivery of backups (leave SPT_SMTP_HOST unset to disable).
SMTP_HOST = os.environ.get("SPT_SMTP_HOST", "")
SMTP_PORT = int(os.environ.get("SPT_SMTP_PORT", "587"))
SMTP_USER = os.environ.get("SPT_SMTP_USER", "")
SMTP_PASSWORD = os.environ.get("SPT_SMTP_PASSWORD", "")
SMTP_SENDER = os.environ.get("SPT_SMTP_SENDER", SMTP_USER)
BACKUP_EMAIL_TO = os.environ.get("SPT_BACKUP_EMAIL_TO", "")
