from typing import List, Optional

from pydantic import Field, field_validator

from data_management.dto.common import DTO, one_of
from statics import SECTIONS, EnrollmentOutcome

DECISION_OUTCOMES = [EnrollmentOutcome.PROMOTED.value, EnrollmentOutcome.RETAINED.value, EnrollmentOutcome.LEFT.value]


class PromotionCandidate(DTO):
    enrollment_id: int
    student_id: int
    admission_no: str
    name: str
    student_class: str
    section: str
    roll_no: Optional[int]
    next_class: Optional[str]  # None = completes the final class (passes out)


class PromotionDecision(DTO):
    enrollment_id: int
    outcome: str
    target_section: str

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, value: str) -> str:
        return one_of(value, DECISION_OUTCOMES, "Outcome")

    @field_validator("target_section")
    @classmethod
    def _section(cls, value: str) -> str:
        return one_of(value, SECTIONS, "Section")


class PromotionRequest(DTO):
    from_year_id: int
    to_year_id: int
    decisions: List[PromotionDecision] = Field(min_length=1)


class PromotionResult(DTO):
    promoted: int = 0
    retained: int = 0
    left: int = 0
    passed_out: int = 0
