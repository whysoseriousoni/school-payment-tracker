from datetime import date
from typing import Optional

from pydantic import Field, field_validator

from data_management.dto.common import DTO, blank_to_none, one_of
from helper.school_calendar import month_label
from statics import CLASSES, FEE_TYPE_LABELS, ONE_OFF_FEE_TYPES, RECURRING_FEE_TYPES, FeeType


def due_label(fee_type: str, fee_month: Optional[date], description: Optional[str]) -> str:
    """'Tuition Fee - Jun 2026' / 'Book Fee - Class 3 books'."""
    try:
        type_label = FEE_TYPE_LABELS[FeeType(fee_type)]
    except ValueError:
        type_label = fee_type
    if fee_month:
        return f"{type_label} - {month_label(fee_month)}"
    return f"{type_label} - {description}" if description else type_label


class FeeStructureInput(DTO):
    academic_year_id: int
    student_class: str
    fee_type: str
    monthly_amount_paise: int = Field(ge=0)

    @field_validator("student_class")
    @classmethod
    def _class(cls, value: str) -> str:
        return one_of(value, CLASSES, "Class")

    @field_validator("fee_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return one_of(value, [t.value for t in RECURRING_FEE_TYPES], "Fee type")


class FeeStructureRead(DTO):
    id: int
    academic_year_id: int
    student_class: str
    fee_type: str
    monthly_amount_paise: int
    is_active: bool


class OneOffDueCreate(DTO):
    enrollment_id: int
    fee_type: str
    description: Optional[str] = None
    amount_paise: int = Field(gt=0)

    _description = field_validator("description")(blank_to_none)

    @field_validator("fee_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return one_of(value, [t.value for t in ONE_OFF_FEE_TYPES], "Fee type")


class VanChange(DTO):
    enrollment_id: int
    from_month: date
    monthly_amount_paise: int = Field(gt=0)


class FeeDueRead(DTO):
    fee_due_id: int
    enrollment_id: int
    fee_type: str
    fee_month: Optional[date]
    description: Optional[str]
    amount_due_paise: int
    amount_paid_paise: int
    balance_paise: int

    @property
    def label(self) -> str:
        return due_label(self.fee_type, self.fee_month, self.description)

    @property
    def status(self) -> str:
        if self.balance_paise == 0:
            return "Paid"
        return "Part paid" if self.amount_paid_paise else "Unpaid"
