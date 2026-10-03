from datetime import date
from typing import List, Optional

from pydantic import Field, NaiveDatetime, field_validator, model_validator

from data_management.dto.common import DTO, blank_to_none, clean_name, not_in_future, one_of
from statics import PAYMENT_METHODS


class AllocationInput(DTO):
    fee_due_id: int
    amount_paise: int = Field(gt=0)


class PaymentCreate(DTO):
    student_id: int
    enrollment_id: int
    paid_on: date
    payment_method: str
    billing_name: str
    payment_notes: Optional[str] = None
    notes: Optional[str] = None
    allocations: List[AllocationInput] = Field(min_length=1)

    _billing_name = field_validator("billing_name")(clean_name)
    _paid_on = field_validator("paid_on")(not_in_future)
    _texts = field_validator("payment_notes", "notes")(blank_to_none)

    @field_validator("payment_method")
    @classmethod
    def _method(cls, value: str) -> str:
        return one_of(value, PAYMENT_METHODS, "Payment method")

    @model_validator(mode="after")
    def _distinct_dues(self):
        ids = [allocation.fee_due_id for allocation in self.allocations]
        if len(ids) != len(set(ids)):
            raise ValueError("Each fee can appear only once in a payment")
        return self

    @property
    def amount_paise(self) -> int:
        return sum(allocation.amount_paise for allocation in self.allocations)


class VoidRequest(DTO):
    payment_id: int
    reason: str = Field(min_length=3, max_length=300)


class AllocationRead(DTO):
    fee_due_id: int
    label: str
    amount_paise: int


class PaymentRead(DTO):
    id: int
    receipt_no: str
    student_id: int
    student_name: str
    admission_no: str
    enrollment_id: int
    academic_year_label: str
    student_class: str
    section: str
    paid_on: date
    amount_paise: int
    amount_in_words: str
    payment_method: str
    payment_notes: Optional[str]
    billing_name: Optional[str]
    notes: Optional[str]
    collected_by: Optional[str]
    is_voided: bool
    void_reason: Optional[str]
    voided_on: Optional[NaiveDatetime]
    voided_by: Optional[str]
    inserted_on: NaiveDatetime
    allocations: List[AllocationRead]
