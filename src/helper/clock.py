"""
Single source of "now" for the application.

SQLite has no timezone-aware datetime type, so every timestamp is stored as
naive Indian Standard Time. Always use these helpers instead of
`datetime.now()` so stored values stay consistent.
"""
from datetime import date, datetime

from config.settings import TIMEZONE


def now_ist() -> datetime:
    """Current IST time as a naive datetime (safe to store in SQLite)."""
    return datetime.now(tz=TIMEZONE).replace(tzinfo=None)


def today_ist() -> date:
    """Current IST date."""
    return now_ist().date()
