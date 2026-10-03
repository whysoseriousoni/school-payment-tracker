from datetime import date
from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class Payment(TimestampMixin, table=True):
    """
    A receipt. The amount is spread over fee dues through PaymentAllocation.
    Payments are never edited or deleted - they are voided with a reason.
    """

    __tablename__ = "payment"

    id: Optional[int] = Field(default=None, primary_key=True)
    receipt_no: str = Field(unique=True)
    student_id: int = Field(foreign_key="student.id")
    enrollment_id: int = Field(foreign_key="student_enrollment.id")
    paid_on: date
    amount_paise: int
    payment_method: str
    payment_notes: Optional[str] = None
    billing_name: Optional[str] = None
    notes: Optional[str] = None
    amount_in_words: str
    collected_by: Optional[str] = None
    is_voided: bool = Field(default=False)
    void_reason: Optional[str] = None
    voided_on: Optional[NaiveDatetime] = None
    voided_by: Optional[str] = None
