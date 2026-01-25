from typing import List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, select
from datetime import datetime, date

from data_management.sql_manager import get_engine
from helper.utils import sqlmodel_to_df

if TYPE_CHECKING:
    from data_management.BillingDetail import BillingDetail

class Student(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    student_id: Optional[int] = Field(default=None, primary_key=True)
    student_name: str = Field(default=None)
    date_of_birth: Optional[date] = Field(default=None)
    current_class: str = Field(
        default="UPDATE CURRENT CLASS", description="Updated every once year"
    )

    date_of_joining: Optional[date] = Field(
        default=None, description="First Date of joining the school"
    )

    # Last Date of relieve
    date_of_relieve: Optional[date] = Field(
        default=None, description="Last Date of relieving the school"
    )
    # Promoted to next standard
    lkg_date_of_join: Optional[date] = Field(default=None)
    ukg_date_of_join: Optional[date] = Field(default=None)
    class_1_date_of_join: Optional[date] = Field(default=None)
    class_2_date_of_join: Optional[date] = Field(default=None)
    class_3_date_of_join: Optional[date] = Field(default=None)
    class_4_date_of_join: Optional[date] = Field(default=None)
    class_5_date_of_join: Optional[date] = Field(default=None)
    class_6_date_of_join: Optional[date] = Field(default=None)
    class_7_date_of_join: Optional[date] = Field(default=None)
    class_8_date_of_join: Optional[date] = Field(default=None)
    class_9_date_of_join: Optional[date] = Field(default=None)
    class_10_date_of_join: Optional[date] = Field(default=None)

    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    modified_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )
    bills: List["BillingDetail"] = Relationship(back_populates="student")
