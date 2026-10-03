"""
Single source of "now" for the application.

SQLite has no timezone-aware datetime type, so every timestamp is stored as
naive Indian Standard Time. Always use these helpers instead of
`datetime.now()` so stored values stay consistent (and tests can freeze time).
"""
from datetime import date, datetime
from typing import Optional

from config.settings import TIMEZONE

_frozen: Optional[datetime] = None


def now_ist() -> datetime:
    """Current IST time as a naive datetime (safe to store in SQLite)."""
    if _frozen is not None:
        return _frozen
    return datetime.now(tz=TIMEZONE).replace(tzinfo=None)


def today_ist() -> date:
    """Current IST date."""
    return now_ist().date()


def freeze(moment: Optional[datetime]) -> None:
    """Tests only: pin the clock to `moment` (None restores the real clock)."""
    global _frozen
    _frozen = moment
