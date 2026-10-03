import re
from datetime import date
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from data_management.dto.common import DTO, blank_to_none, one_of
from statics import ANNUAL_FEE_TYPES, CLASSES, FEE_TYPE_LABELS, ONE_OFF_FEE_TYPES, STUDENT_CATEGORY, FeeType


def fee_type_label(fee_type: str) -> str:
    try:
        return FEE_TYPE_LABELS[FeeType(fee_type)]
    except ValueError:
        return fee_type


def due_label(fee_type: str, description: Optional[str] = None, plan_code: Optional[str] = None) -> str:
    """'Tuition Fee (UKG-FEE-1)' / 'Book Fee - Class 3 books'."""
    label = fee_type_label(fee_type)
    if plan_code:
        return f"{label} ({plan_code})"
    return f"{label} - {description}" if description else label


# ---------- plans ----------

class FeePlanInput(DTO):
    academic_year_id: int
    code: str = Field(min_length=2, max_length=30)
    fee_type: str
    student_class: Optional[str] = None
    category: Optional[str] = None
    annual_amount_paise: int = Field(ge=0)
    is_default: bool = False
    is_active: bool = True
    description: Optional[str] = None

    _texts = field_validator("student_class", "category", "description")(blank_to_none)

    @field_validator("code")
    @classmethod
    def _code(cls, value: str) -> str:
        value = value.strip().upper()
        if not re.fullmatch(r"[A-Z0-9][A-Z0-9_\-]*", value):
            raise ValueError("Code may contain only letters, numbers, '-' and '_' (e.g. UKG-FEE-1)")
        return value

    @field_validator("fee_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return one_of(value, [t.value for t in ANNUAL_FEE_TYPES], "Fee type")

    @field_validator("student_class")
    @classmethod
    def _class(cls, value: Optional[str]) -> Optional[str]:
        return one_of(value, CLASSES, "Class")

    @field_validator("category")
    @classmethod
    def _category(cls, value: Optional[str]) -> Optional[str]:
        return one_of(value, STUDENT_CATEGORY, "Category")

    @model_validator(mode="after")
    def _rules(self):
        if self.fee_type == FeeType.TUITION.value and not self.student_class:
            raise ValueError(f"{self.code}: a tuition plan needs a class")
        if self.is_default and not self.is_active:
            raise ValueError(f"{self.code}: an inactive plan cannot be the default")
        return self


class FeePlanRead(DTO):
    id: int
    academic_year_id: int
    code: str
    fee_type: str
    student_class: Optional[str]
    category: Optional[str]
    annual_amount_paise: int
    is_default: bool
    is_active: bool
    description: Optional[str]
    students_assigned: int = 0

    @property
    def label(self) -> str:
        scope = self.student_class or "any class"
        if self.category:
            scope += f", {self.category}"
        return f"{self.code} - {fee_type_label(self.fee_type)} - {scope}"


class PlanSaveResult(DTO):
    plan: FeePlanRead
    dues_updated: int = 0
    dues_skipped: List[str] = Field(default_factory=list)  # students who already paid more than the new amount


# ---------- milestones ----------

class MilestoneInput(DTO):
    due_date: date
    cumulative_percent: int = Field(ge=1, le=100)


class MilestoneSet(DTO):
    academic_year_id: int
    milestones: List[MilestoneInput]

    @model_validator(mode="after")
    def _increasing(self):
        ordered = sorted(self.milestones, key=lambda m: m.due_date)
        if len({m.due_date for m in ordered}) != len(ordered):
            raise ValueError("Each milestone date can be used only once")
        percents = [m.cumulative_percent for m in ordered]
        if percents != sorted(percents) or len(set(percents)) != len(percents):
            raise ValueError("Percentages must increase with each later date (e.g. 50% by Oct, 100% by Mar)")
        self.milestones = ordered
        return self


class MilestoneRead(DTO):
    id: int
    due_date: date
    cumulative_percent: int


# ---------- assignment ----------

class FeeAssignment(DTO):
    """Assign an annual fee to one enrollment: a plan, or a custom amount with a reason."""

    enrollment_id: int
    fee_type: str
    fee_plan_id: Optional[int] = None
    custom_amount_paise: Optional[int] = Field(default=None, ge=0)
    reason: Optional[str] = None

    _reason = field_validator("reason")(blank_to_none)

    @field_validator("fee_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return one_of(value, [t.value for t in ANNUAL_FEE_TYPES], "Fee type")

    @model_validator(mode="after")
    def _plan_or_custom(self):
        if (self.fee_plan_id is None) == (self.custom_amount_paise is None):
            raise ValueError("Choose a fee plan or enter a custom amount (not both)")
        if self.custom_amount_paise is not None and not self.reason:
            raise ValueError("Give a reason for the custom amount")
        return self


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

    @model_validator(mode="after")
    def _custom_needs_description(self):
        if self.fee_type == FeeType.CUSTOM.value and not self.description:
            raise ValueError("Describe the custom fee")
        return self


# ---------- ledger ----------

class FeeDueRead(DTO):
    fee_due_id: int
    enrollment_id: int
    fee_type: str
    fee_plan_id: Optional[int]
    plan_code: Optional[str]
    description: Optional[str]
    override_reason: Optional[str]
    amount_due_paise: int
    amount_paid_paise: int
    balance_paise: int
    created_on: date

    @property
    def is_annual(self) -> bool:
        return self.fee_type in [t.value for t in ANNUAL_FEE_TYPES]

    @property
    def label(self) -> str:
        label = due_label(self.fee_type, self.description, self.plan_code)
        if self.is_annual and not self.plan_code:
            label += " (custom)"
        return label

    @property
    def status(self) -> str:
        if self.balance_paise == 0:
            return "Paid"
        return "Part paid" if self.amount_paid_paise else "Unpaid"


class AssignmentRow(DTO):
    """One student's annual fees for a term (fee assignment screen)."""

    enrollment_id: int
    student_id: int
    admission_no: str
    name: str
    student_class: str
    section: str
    roll_no: Optional[int]
    category: Optional[str]
    tuition_plan: Optional[str]
    tuition_paise: Optional[int]
    tuition_paid_paise: int
    van_plan: Optional[str]
    van_paise: Optional[int]
