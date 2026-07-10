from typing import List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, select
from datetime import datetime, date

from data_management.sql_manager import get_engine
from helper.HashMixin import HashMixin
from helper.utils import sqlmodel_to_df

if TYPE_CHECKING:
    from data_management.dao.BillingDetail import BillingDetail

class Student(HashMixin, SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    __tablename__ = 'student'

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    date_of_birth: Optional[date] = Field(default=None)
    current_class: str = Field(
        default="UPDATE CURRENT CLASS", description="Updated every once year"
    )

    date_of_join: Optional[date] = Field(
        default=None, description="First Date of joining the school"
    )

    identifier_id: Optional[str] = Field(default="")
    identifier_type: Optional[str] = Field(default="")
    last_4_digit_of_identifier: Optional[str] = Field(default=None)

    category: Optional[str] = Field(default="")
    class_joined: Optional[str] = Field(default="")

    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )

    last_updated: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )
    
    # bills: List["BillingDetail"] = Relationship(back_populates="student")
