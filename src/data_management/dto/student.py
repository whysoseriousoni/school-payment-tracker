from datetime import date
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from data_management.dto.common import DTO, blank_to_none, clean_name, not_in_future, one_of
from data_management.dto.guardian import GuardianLinkInput, GuardianLinkRead
from statics import CLASSES, SECTIONS, STUDENT_CATEGORY, USER_IDENTIFIER_TYPES, StudentStatus


class IdentifierInput(DTO):
    """Full number (encrypted at rest) and/or just the last 4 digits."""

    identifier_type: str = "AADHAR"
    full_number: Optional[str] = None
    last_4_digits: Optional[str] = None

    @field_validator("identifier_type")
    @classmethod
    def _type(cls, value: str) -> str:
        return one_of(value, USER_IDENTIFIER_TYPES, "Identifier type")

    @field_validator("full_number")
    @classmethod
    def _full(cls, value: Optional[str]) -> Optional[str]:
        from data_management.services.identifier_crypto import normalise_aadhaar

        value = blank_to_none(value)
        return normalise_aadhaar(value) if value else None

    @field_validator("last_4_digits")
    @classmethod
    def _last4(cls, value: Optional[str]) -> Optional[str]:
        value = blank_to_none(value)
        if value is not None and not (len(value) == 4 and value.isdigit()):
            raise ValueError("Last 4 digits must be exactly 4 numbers")
        return value

    @model_validator(mode="after")
    def _consistent(self):
        if self.full_number:
            if self.last_4_digits and self.last_4_digits != self.full_number[-4:]:
                raise ValueError("Last 4 digits do not match the full number")
            self.last_4_digits = self.full_number[-4:]
        if not self.last_4_digits:
            raise ValueError("Enter the full number or at least the last 4 digits")
        return self


class StudentBase(DTO):
    name: str
    date_of_birth: Optional[date] = None
    category: str
    date_of_join: date
    class_joined: str
    admission_no: Optional[str] = Field(default=None, max_length=30)
    notes: Optional[str] = None

    _name = field_validator("name")(clean_name)
    _dates = field_validator("date_of_birth", "date_of_join")(not_in_future)
    _notes = field_validator("notes", "admission_no")(blank_to_none)

    @field_validator("category")
    @classmethod
    def _category(cls, value: str) -> str:
        return one_of(value, STUDENT_CATEGORY, "Category")

    @field_validator("class_joined")
    @classmethod
    def _class_joined(cls, value: str) -> str:
        return one_of(value, CLASSES, "Class joined")

    @model_validator(mode="after")
    def _birth_before_join(self):
        if self.date_of_birth and self.date_of_birth >= self.date_of_join:
            raise ValueError("Date of birth must be before the date of joining")
        return self


class EnrollmentInput(DTO):
    academic_year_id: int
    student_class: str
    section: str
    roll_no: Optional[int] = Field(default=None, gt=0)

    @field_validator("student_class")
    @classmethod
    def _class(cls, value: str) -> str:
        return one_of(value, CLASSES, "Class")

    @field_validator("section")
    @classmethod
    def _section(cls, value: str) -> str:
        return one_of(value, SECTIONS, "Section")


class StudentCreate(StudentBase):
    enrollment: EnrollmentInput
    van_monthly_paise: Optional[int] = Field(default=None, ge=0, description="None = no van")
    identifier: Optional[IdentifierInput] = None
    guardians: List[GuardianLinkInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def _one_primary(self):
        primaries = sum(1 for link in self.guardians if link.is_primary)
        if primaries > 1:
            raise ValueError("Only one guardian can be the primary contact")
        if self.guardians and primaries == 0:
            self.guardians[0].is_primary = True
        return self


class StudentUpdate(StudentBase):
    admission_no: str = Field(min_length=1, max_length=30)


class EnrollmentUpdate(DTO):
    section: str
    roll_no: Optional[int] = Field(default=None, gt=0)

    @field_validator("section")
    @classmethod
    def _section(cls, value: str) -> str:
        return one_of(value, SECTIONS, "Section")


class StudentLeaving(DTO):
    status: str
    date_of_leaving: date

    _date = field_validator("date_of_leaving")(not_in_future)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        return one_of(value, [StudentStatus.LEFT.value, StudentStatus.PASSED_OUT.value], "Status")


class StudentSearch(DTO):
    text: Optional[str] = None  # name, admission no or numeric student ID
    academic_year_id: Optional[int] = None
    student_class: Optional[str] = None
    section: Optional[str] = None
    category: Optional[str] = None
    status: Optional[str] = None
    limit: int = Field(default=500, ge=1, le=5000)

    _text = field_validator("text", "student_class", "section", "category", "status")(blank_to_none)


class EnrollmentRead(DTO):
    enrollment_id: int
    academic_year_id: int
    academic_year_label: str
    student_class: str
    section: str
    roll_no: Optional[int]
    outcome: Optional[str]

    @property
    def class_section(self) -> str:
        return f"{self.student_class}-{self.section}"


class StudentSearchResult(DTO):
    student_id: int
    admission_no: str
    name: str
    status: str
    category: Optional[str]
    enrollment_id: Optional[int]
    academic_year_label: Optional[str]
    student_class: Optional[str]
    section: Optional[str]
    roll_no: Optional[int]
    guardian_name: Optional[str]
    guardian_mobile: Optional[str]


class StudentProfile(DTO):
    student_id: int
    admission_no: str
    name: str
    date_of_birth: Optional[date]
    category: Optional[str]
    status: str
    date_of_join: Optional[date]
    class_joined: Optional[str]
    date_of_leaving: Optional[date]
    notes: Optional[str]
    identifier_type: Optional[str]
    identifier_last_4: Optional[str]
    has_full_identifier: bool
    enrollments: List[EnrollmentRead]
    guardians: List[GuardianLinkRead]
    has_payments: bool

    def enrollment_for(self, academic_year_id: int) -> Optional[EnrollmentRead]:
        return next((e for e in self.enrollments if e.academic_year_id == academic_year_id), None)

    @property
    def primary_guardian(self) -> Optional[GuardianLinkRead]:
        return next((g for g in self.guardians if g.is_primary), self.guardians[0] if self.guardians else None)
