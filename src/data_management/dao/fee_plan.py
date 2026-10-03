from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class FeePlan(TimestampMixin, table=True):
    """
    A named annual fee for a term, e.g. UKG-FEE-1 = Rs 10,000 or UKG-DG1-1 = Rs 5,000.
    Tuition plans belong to a class (and optionally a category); van plans apply to any class.
    """

    __tablename__ = "fee_plan"

    id: Optional[int] = Field(default=None, primary_key=True)
    academic_year_id: int = Field(foreign_key="academic_year.id")
    code: str
    fee_type: str  # FeeType.TUITION or FeeType.VAN
    student_class: Optional[str] = None
    category: Optional[str] = None  # None = any category
    annual_amount_paise: int
    is_default: bool = Field(default=False)
    is_active: bool = Field(default=True)
    description: Optional[str] = None
