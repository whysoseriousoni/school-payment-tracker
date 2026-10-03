from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class StudentFeeDue(TimestampMixin, table=True):
    """
    An amount a student owes for one enrollment (term).
    Tuition and van: one annual row each, from the assigned fee plan, or a custom
    amount with `override_reason`. One-off fees (books, uniform, ...): no plan.
    """

    __tablename__ = "student_fee_due"

    id: Optional[int] = Field(default=None, primary_key=True)
    enrollment_id: int = Field(foreign_key="student_enrollment.id")
    fee_type: str
    fee_plan_id: Optional[int] = Field(default=None, foreign_key="fee_plan.id")
    description: Optional[str] = None
    override_reason: Optional[str] = None
    amount_due_paise: int
