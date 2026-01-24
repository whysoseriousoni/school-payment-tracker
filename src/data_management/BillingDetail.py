from typing import List, Optional
from sqlmodel import Field, Relationship, SQLModel
from datetime import datetime


class BillingDetail(SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    bill_id: Optional[int] = Field(
        primary_key=True,
        nullable=False,
        
    )
    student_id: Optional[int] = Field(default=None, foreign_key="student.student_id")
    student_name: str = Field(default=None)
    bill_date: Optional[datetime] = Field(
        default=datetime.now().date(),
    )
    bill_type: str = Field(
        default="DEFAULT_BILL_TYPE",
    )
    bill_amount: float = Field(
        default=None, 
    )
    billing_amount_in_words: str = Field(default=None)
    inserted_date: Optional[datetime] = Field(
        default=datetime.now().date(),
    )
    modified_date: Optional[datetime] = Field(
        default=datetime.now().date(),
    )