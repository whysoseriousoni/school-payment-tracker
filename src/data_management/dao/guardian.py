from typing import Optional

from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class Guardian(TimestampMixin, table=True):
    """A parent / guardian. Linked to one or more students through StudentGuardian."""

    __tablename__ = "guardian"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str
    mobile_number: Optional[str] = Field(default=None, index=True)
    year_of_birth: Optional[int] = None
