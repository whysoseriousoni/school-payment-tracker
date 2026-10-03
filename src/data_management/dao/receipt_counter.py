from sqlmodel import Field

from data_management.dao.base import TableBase


class ReceiptCounter(TableBase, table=True):
    """Last receipt number issued per academic year (RCPT/2026-27/00001 ...)."""

    __tablename__ = "receipt_counter"

    academic_year_id: int = Field(primary_key=True, foreign_key="academic_year.id")
    last_number: int = Field(default=0)
