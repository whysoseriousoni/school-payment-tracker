from datetime import date
from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin
from statics import StudentStatus


class Student(TimestampMixin, table=True):
    """Permanent student identity. Class, section and roll number live on StudentEnrollment."""

    __tablename__ = "student"

    id: Optional[int] = Field(default=None, primary_key=True)
    admission_no: str = Field(unique=True)
    name: str = Field(index=True)
    date_of_birth: Optional[date] = None
    category: Optional[str] = None
    status: str = Field(default=StudentStatus.ACTIVE.value)
    date_of_join: Optional[date] = None
    class_joined: Optional[str] = None
    date_of_leaving: Optional[date] = None
    identifier_id: Optional[int] = Field(default=None, foreign_key="identifier.id", unique=True)
    notes: Optional[str] = None
