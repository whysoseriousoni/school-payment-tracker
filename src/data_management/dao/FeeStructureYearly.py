from datetime import datetime
from typing import List, Optional
from zoneinfo import ZoneInfo
from sqlmodel import Field, SQLModel

from helper.HashMixin import HashMixin


class GuardianDetails(HashMixin, SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)   
    student_class: str = Field(default="", nullable=False)
    
    
    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    updated_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )
    