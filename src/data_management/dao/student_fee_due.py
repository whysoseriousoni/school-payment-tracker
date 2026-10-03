from datetime import date
from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class StudentFeeDue(TimestampMixin, table=True):
    """
    An amount a student owes for one enrollment.
    Recurring fees (tuition, van) have one row per month with `fee_month` set to
    the 1st of that month; one-off fees (books, uniform, custom) have no month.
    """

    __tablename__ = "student_fee_due"

    id: Optional[int] = Field(default=None, primary_key=True)
    enrollment_id: int = Field(foreign_key="student_enrollment.id")
    fee_type: str
    fee_month: Optional[date] = None
    description: Optional[str] = None
    amount_due_paise: int
