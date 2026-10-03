from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class StudentGuardian(TimestampMixin, table=True):
    """Many-to-many link: one guardian can have several students (siblings) and vice versa."""

    __tablename__ = "student_guardian"

    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(foreign_key="student.id")
    guardian_id: int = Field(foreign_key="guardian.id")
    relation_type: str
    is_primary: bool = Field(default=False)
