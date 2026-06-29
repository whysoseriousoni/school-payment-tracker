from typing import List, Optional, TYPE_CHECKING
from zoneinfo import ZoneInfo
from sqlmodel import Field, Relationship, SQLModel, Session, create_engine, select
from datetime import datetime, date

from data_management.sql_manager import get_engine
from helper.HashMixin import HashMixin
from helper.utils import sqlmodel_to_df

if TYPE_CHECKING:
    from data_management.dao.BillingDetail import BillingDetail

class StudentAnnalFee(HashMixin, SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[int] = Field(default=None, primary_key=True)
    student_id: int = Field(nullable=False)
    
    date_of_birth: Optional[date] = Field(default=None)
    student_class: str = Field(
        default="UPDATE CURRENT CLASS", description="Updated every once year"
    )
    
    fee_amount: Optional[float] = Field(nullable=False)

    payment_start_date: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
    
    payment_end_date: Optional[datetime] = Field(
        default_factory=lambda: datetime.now(tz=ZoneInfo("Asia/Kolkata")),
    )
