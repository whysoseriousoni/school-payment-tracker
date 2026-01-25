from typing import List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime

if TYPE_CHECKING:
    from data_management.Student import Student


class BillingDetail(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    bill_id: Optional[int] = Field(
        primary_key=True,
        nullable=False,
    )
    student_id: Optional[int] = Field(default=None, foreign_key="student.student_id")
    student_name: str = Field(default=None)
    bill_date: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    bill_type: str = Field(
        default="DEFAULT_BILL_TYPE",
    )
    bill_amount: float = Field(
        default=None,
    )
    billing_amount_in_words: str = Field(default=None)
    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    modified_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )

    student: Optional["Student"] = Relationship(back_populates="bills")
