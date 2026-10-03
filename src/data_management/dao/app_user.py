from typing import Optional

from pydantic import NaiveDatetime
from sqlmodel import Field

from data_management.dao.base import TimestampMixin


class AppUser(TimestampMixin, table=True):
    """Login account. `password_hash` is bcrypt; plain passwords are never stored."""

    __tablename__ = "app_user"

    id: Optional[int] = Field(default=None, primary_key=True)
    username: str = Field(unique=True)
    password_hash: str
    role: str  # UserRole
    is_active: bool = Field(default=True)
    last_login_on: Optional[NaiveDatetime] = None
