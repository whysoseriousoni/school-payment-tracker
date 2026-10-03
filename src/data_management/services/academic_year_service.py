from typing import List, Optional

from sqlalchemy import update

from data_management.dao import AcademicYear
from data_management.dto.academic_year import AcademicYearCreate, AcademicYearRead
from data_management.repositories import academic_year_repository as repo
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper.clock import today_ist
from helper.school_calendar import academic_year_bounds, academic_year_label, academic_year_start_for


def list_years() -> List[AcademicYearRead]:
    with session_scope() as session:
        return [AcademicYearRead.model_validate(year) for year in repo.list_all(session)]


def get_year(year_id: int) -> AcademicYearRead:
    with session_scope() as session:
        year = repo.get(session, year_id)
        if year is None:
            raise NotFoundError(f"Academic year {year_id} not found")
        return AcademicYearRead.model_validate(year)


def get_current_year() -> Optional[AcademicYearRead]:
    with session_scope() as session:
        year = repo.get_current(session)
        return AcademicYearRead.model_validate(year) if year else None


def create_year(data: AcademicYearCreate) -> AcademicYearRead:
    label = academic_year_label(data.start_year)
    start, end = academic_year_bounds(data.start_year)
    with session_scope() as session:
        if repo.get_by_label(session, label):
            raise BusinessRuleError(f"Academic year {label} already exists")
        if data.make_current:
            session.execute(update(AcademicYear).values(is_current=False))
        year = AcademicYear(label=label, start_date=start, end_date=end, is_current=data.make_current)
        session.add(year)
        session.flush()
        return AcademicYearRead.model_validate(year)


def set_current_year(year_id: int) -> None:
    with session_scope() as session:
        if repo.get(session, year_id) is None:
            raise NotFoundError(f"Academic year {year_id} not found")
        session.execute(update(AcademicYear).values(is_current=False))
        session.flush()
        session.execute(update(AcademicYear).where(AcademicYear.id == year_id).values(is_current=True))


def ensure_current_year() -> AcademicYearRead:
    """First run: make sure the academic year containing today exists and is current."""
    current = get_current_year()
    if current:
        return current
    start_year = academic_year_start_for(today_ist())
    with session_scope() as session:
        existing = repo.get_by_label(session, academic_year_label(start_year))
    if existing:
        set_current_year(existing.id)
        return get_year(existing.id)
    return create_year(AcademicYearCreate(start_year=start_year, make_current=True))
