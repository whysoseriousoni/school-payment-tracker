from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

from data_management.dao.base import TableBase
from helper.clock import now_ist


class AppSetting(TableBase, table=True):
    """Key/value application settings (school name, address, ...)."""

    __tablename__ = "app_setting"

    key: str = Field(primary_key=True)
    value: str
    updated_on: NaiveDatetime = Field(
        default_factory=now_ist, nullable=False, sa_column_kwargs={"onupdate": now_ist}
    )
