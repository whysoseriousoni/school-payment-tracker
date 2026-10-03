from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class StudentEnrollment(TimestampMixin, table=True):
    """One row per student per academic year: class, section, roll number and year outcome."""

    __tablename__ = "student_enrollment"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    academic_year_id: int = Field(foreign_key="academic_year.id")
    student_class: str
    section: str
    roll_no: Optional[int] = None
    outcome: Optional[str] = None  # EnrollmentOutcome; NULL while the year is in progress
