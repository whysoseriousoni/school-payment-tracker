from datetime import date
from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class FeeMilestone(TimestampMixin, table=True):
    """By `due_date`, `cumulative_percent` of each annual fee should have been paid."""

    __tablename__ = "fee_milestone"

    id: Optional[int] = Field(default=None, primary_key=True)
    academic_year_id: int = Field(foreign_key="academic_year.id")
    due_date: date
    cumulative_percent: int
