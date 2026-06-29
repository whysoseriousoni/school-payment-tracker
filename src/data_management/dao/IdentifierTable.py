
from typing import List, Optional
from sqlmodel import Field, SQLModel

from helper.HashMixin import HashMixin


class IdentifierTable(HashMixin, SQLModel, table=True):
    __table_args__ = {"extend_existing": True}
    id: Optional[str] = Field(default=None, primary_key=True)
    identifier_type: str = Field(default=None)
    identifier_value_aes: str = Field(default=None)
    last_4_digit_of_identifier: str = Field(default=None)
    nounce: str = Field(default=None)
    tag: str = Field(default=None)
