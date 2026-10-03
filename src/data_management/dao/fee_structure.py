from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class FeeStructure(TimestampMixin, table=True):
    """Monthly amount for a recurring fee (tuition / van default) per class per academic year."""

    __tablename__ = "fee_structure"

    id: Optional[int] = Field(default=None, primary_key=True)
    academic_year_id: int = Field(foreign_key="academic_year.id")
    student_class: str
    fee_type: str  # FeeType.TUITION or FeeType.VAN
    monthly_amount_paise: int
    is_active: bool = Field(default=True)
