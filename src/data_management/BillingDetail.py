from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, SQLModel
from datetime import datetime

if TYPE_CHECKING:
    from data_management.Student import Student


class BillingDetail(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(
        primary_key=True,
        nullable=False,
    )
    
    student_id: Optional[int] = Field(default=None, foreign_key="student.id")
    
    student_class: str = Field(
        nullable=False
    )
    
    notes: str = Field(default="")
    
    paid_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    
    amount_paid: float = Field(
        nullable=False,
    )
    
    payment_method: str = Field(default="")
    payment_notes: str = Field(default="")
    
    amount_in_words: str = Field(nullable=False)
    
    balance_amount_to_pay: float = Field(nullable=False)
    
    
    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    updated_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )

    # student: Optional["Student"] = Relationship(back_populates="bills")
