from datetime import date
from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class AcademicYear(TimestampMixin, table=True):
    """A school operation year, June -> May (e.g. '2026-27')."""

    __tablename__ = "academic_year"

    id: Optional[int] = Field(default=None, primary_key=True)
    label: str = Field(unique=True)
    start_date: date
    end_date: date
    is_current: bool = Field(default=False)
