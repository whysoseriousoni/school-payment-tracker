from datetime import date
from typing import List, Optional

from pydantic import Field, field_validator, model_validator

from data_management.dto.common import DTO, clean_name, indian_mobile, one_of
from statics import GUARDIAN_TYPES


def _year_of_birth(value: Optional[int]) -> Optional[int]:
    if value is not None and not 1920 <= value <= date.today().year - 14:
        raise ValueError("Year of birth looks wrong")
    return value


class GuardianCreate(DTO):
    name: str
    mobile_number: Optional[str] = None
    year_of_birth: Optional[int] = None

    _name = field_validator("name")(clean_name)
    _mobile = field_validator("mobile_number")(indian_mobile)
    _yob = field_validator("year_of_birth")(_year_of_birth)


class GuardianUpdate(GuardianCreate):
    pass


class GuardianLinkInput(DTO):
    """Link a student to an existing guardian (guardian_id) or a new one (name ...)."""

    guardian_id: Optional[int] = None
    new_guardian: Optional[GuardianCreate] = None
    relation_type: str
    is_primary: bool = False

    @field_validator("relation_type")
    @classmethod
    def _relation(cls, value: str) -> str:
        return one_of(value, GUARDIAN_TYPES, "Relation")

    @model_validator(mode="after")
    def _exactly_one_source(self):
        if (self.guardian_id is None) == (self.new_guardian is None):
            raise ValueError("Choose an existing guardian or enter a new one (not both)")
        return self


class GuardianLinkRead(DTO):
    link_id: int
    guardian_id: int
    name: str
    mobile_number: Optional[str]
    relation_type: str
    is_primary: bool


class GuardianRead(DTO):
    id: int
    name: str
    mobile_number: Optional[str]
    year_of_birth: Optional[int]
    students: List[str] = Field(default_factory=list)
