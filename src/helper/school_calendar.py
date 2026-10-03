"""
School calendar rules: academic years (June -> May), fee months and class
progression. Pure functions with no database access, so they are easy to test
and reuse in services, migrations and reports.
"""
from datetime import date
from typing import List, Optional, Tuple

from config.settings import ACADEMIC_YEAR_START_MONTH
from statics import CLASSES


def academic_year_start_for(on_date: date) -> int:
    """Calendar year in which the academic year containing `on_date` started."""
    if on_date.month >= ACADEMIC_YEAR_START_MONTH:
        return on_date.year
    return on_date.year - 1


def academic_year_label(start_year: int) -> str:
    """2026 -> '2026-27'."""
    return f"{start_year}-{(start_year + 1) % 100:02d}"


def academic_year_bounds(start_year: int) -> Tuple[date, date]:
    """First and last day of the academic year that starts in `start_year`."""
    start = date(start_year, ACADEMIC_YEAR_START_MONTH, 1)
    next_start = date(start_year + 1, ACADEMIC_YEAR_START_MONTH, 1)
    return start, date.fromordinal(next_start.toordinal() - 1)


def fee_months(start_year: int) -> List[date]:
    """The 12 fee months of an academic year, as first-of-month dates (Jun -> May)."""
    months = []
    for offset in range(12):
        month_index = ACADEMIC_YEAR_START_MONTH - 1 + offset
        months.append(date(start_year + month_index // 12, month_index % 12 + 1, 1))
    return months


def month_label(month: date) -> str:
    """date(2026, 6, 1) -> 'Jun 2026'."""
    return month.strftime("%b %Y")


def next_class(current_class: str) -> Optional[str]:
    """Class a student is promoted to; None after the final class (passed out)."""
    if current_class not in CLASSES:
        raise ValueError(f"Unknown class: {current_class!r}")
    position = CLASSES.index(current_class)
    if position == len(CLASSES) - 1:
        return None
    return CLASSES[position + 1]


def financial_year_bounds(start_year: int) -> Tuple[date, date]:
    """Financial year April `start_year` -> March `start_year + 1`."""
    return date(start_year, 4, 1), date(start_year + 1, 3, 31)
