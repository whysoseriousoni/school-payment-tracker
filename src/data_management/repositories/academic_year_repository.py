from typing import List, Optional

from sqlmodel import Session, select

from data_management.dao import AcademicYear


def get(session: Session, year_id: int) -> Optional[AcademicYear]:
    return session.get(AcademicYear, year_id)


def get_current(session: Session) -> Optional[AcademicYear]:
    return session.exec(select(AcademicYear).where(AcademicYear.is_current == True)).first()  # noqa: E712


def get_by_label(session: Session, label: str) -> Optional[AcademicYear]:
    return session.exec(select(AcademicYear).where(AcademicYear.label == label)).first()


def list_all(session: Session) -> List[AcademicYear]:
    return list(session.exec(select(AcademicYear).order_by(AcademicYear.start_date.desc())))
