from typing import Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime

from helper.HashMixin import HashMixin

if TYPE_CHECKING:
    from data_management.dao.Student import Student


class BillingDetail(HashMixin, SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    __tablename__ = 'billing_details'
    id: Optional[int] = Field(
        primary_key=True,
        nullable=False,
    )
    
    student_id: Optional[int] = Field(default=None, foreign_key="student.id")
    
    student_class: str = Field(
        nullable=False
    )
    
    billing_name: str = Field(nullable=False) # Added
    
    notes: str = Field(default="") # 
    
    paid_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    ) # Added
    
    amount_paid: float = Field(nullable=False) # Added
    
    payment_method: str = Field(nullable=False) # Added
    billing_type: str = Field(nullable=False) # Added
    payment_notes: str = Field(nullable=False)
    
    amount_in_words: str = Field(nullable=False) # Added
    
    balance_amount_to_pay: float = Field(nullable=False)
    
     
    inserted_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    updated_on: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
        sa_column_kwargs={"onupdate": lambda: datetime.now(ZoneInfo("Asia/Kolkata"))},
    )

    # student: Optional["Student"] = Relationship(back_populates="billingdetail",)
