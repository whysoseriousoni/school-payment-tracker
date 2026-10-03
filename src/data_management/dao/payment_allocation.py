from typing import Optional

from sqlmodel import Field, SQLModel


class PaymentAllocation(SQLModel, table=True):
    """How much of a payment went to a particular fee due. Immutable once written."""

    __tablename__ = "payment_allocation"

    id: Optional[int] = Field(default=None, primary_key=True)
    payment_id: int = Field(foreign_key="payment.id")
    fee_due_id: int = Field(foreign_key="student_fee_due.id")
    amount_paise: int
