from datetime import date

from pydantic import Field

from data_management.dto.common import DTO


class AcademicYearCreate(DTO):
    start_year: int = Field(ge=2000, le=2100, description="Calendar year in which June falls")
    make_current: bool = False


class AcademicYearRead(DTO):
    id: int
    label: str
    start_date: date
    end_date: date
    is_current: bool
