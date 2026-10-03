"""Shared column definitions for table models."""

from pydantic import NaiveDatetime
from sqlmodel import Field, SQLModel

from helper.clock import now_ist


class TimestampMixin(SQLModel):
    """inserted_on / updated_on, stored as naive IST."""

    inserted_on: NaiveDatetime = Field(default_factory=now_ist, nullable=False)
    updated_on: NaiveDatetime = Field(
        default_factory=now_ist,
        nullable=False,
        sa_column_kwargs={"onupdate": now_ist},
    )
