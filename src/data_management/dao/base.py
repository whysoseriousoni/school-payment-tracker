"""Shared base classes for table models."""
from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

from helper.clock import now_ist


class TableBase(SQLModel):
    """
    Base for every table model. `extend_existing` lets Streamlit's hot reload
    re-import a model module without "Table ... is already defined" errors.
    """

    __table_args__ = {"extend_existing": True}


class TimestampMixin(TableBase):
    """inserted_on / updated_on, stored as naive IST."""

    inserted_on: NaiveDatetime = Field(default_factory=now_ist, nullable=False)
    updated_on: NaiveDatetime = Field(
        default_factory=now_ist,
        nullable=False,
        sa_column_kwargs={"onupdate": now_ist},
    )