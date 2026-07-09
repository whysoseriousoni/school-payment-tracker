from typing import List, Optional, TYPE_CHECKING
from sqlmodel import Field, SQLModel

from helper.HashMixin import HashMixin


class GuardianDetails(HashMixin, SQLModel, table=True):
    __tablename__ = "guardian_details"
    __table_args__ = {"extend_existing": True}
    
    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(default=None)
    relation_type: Optional[str] = Field(default=None)
    mobile_number: str = Field(
        default="",
    )
    year_of_birth: int = Field(
        default=None,
    )
    student_id: Optional[int] = Field(default=None, foreign_key="student.id")