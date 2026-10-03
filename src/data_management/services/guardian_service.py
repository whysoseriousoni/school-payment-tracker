"""Guardians and their links to students (one guardian -> many students)."""
from typing import List, Optional

from sqlalchemy import text, update
from sqlmodel import Session, select

from data_management.dao import Guardian, Student, StudentGuardian
from data_management.dto.guardian import GuardianCreate, GuardianLinkInput, GuardianRead, GuardianUpdate
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope

_LIST_SQL = """
SELECT g.id, g.name, g.mobile_number, g.year_of_birth,
       GROUP_CONCAT(s.name || ' (' || sg.relation_type || ')', ', ') AS students
  FROM guardian g
  LEFT JOIN student_guardian sg ON sg.guardian_id = g.id
  LEFT JOIN student s ON s.id = sg.student_id
 WHERE (:text IS NULL OR g.name LIKE '%' || :text || '%' OR g.mobile_number LIKE '%' || :text || '%')
 GROUP BY g.id
 ORDER BY g.name
 LIMIT 500
"""


def _read(row: dict) -> GuardianRead:
    students = row.pop("students")
    return GuardianRead(**row, students=students.split(", ") if students else [])


def list_guardians(search_text: Optional[str] = None) -> List[GuardianRead]:
    with session_scope() as session:
        rows = session.execute(text(_LIST_SQL), {"text": (search_text or "").strip() or None}).mappings()
        return [_read(dict(row)) for row in rows]


def create_guardian(data: GuardianCreate) -> GuardianRead:
    with session_scope() as session:
        guardian = Guardian(**data.model_dump())
        session.add(guardian)
        session.flush()
        return GuardianRead.model_validate(guardian)


def update_guardian(guardian_id: int, data: GuardianUpdate) -> None:
    with session_scope() as session:
        guardian = session.get(Guardian, guardian_id)
        if guardian is None:
            raise NotFoundError("Guardian not found")
        for field, value in data.model_dump().items():
            setattr(guardian, field, value)
        session.add(guardian)


def delete_guardian(guardian_id: int) -> None:
    with session_scope() as session:
        guardian = session.get(Guardian, guardian_id)
        if guardian is None:
            raise NotFoundError("Guardian not found")
        if session.exec(select(StudentGuardian).where(StudentGuardian.guardian_id == guardian_id)).first():
            raise BusinessRuleError("Unlink this guardian from all students before deleting")
        session.delete(guardian)


def link_in_session(session: Session, student_id: int, link: GuardianLinkInput) -> StudentGuardian:
    if session.get(Student, student_id) is None:
        raise NotFoundError("Student not found")
    if link.guardian_id is not None:
        if session.get(Guardian, link.guardian_id) is None:
            raise NotFoundError("Guardian not found")
        guardian_id = link.guardian_id
    else:
        guardian = Guardian(**link.new_guardian.model_dump())
        session.add(guardian)
        session.flush()
        guardian_id = guardian.id

    existing = session.exec(select(StudentGuardian).where(
        StudentGuardian.student_id == student_id, StudentGuardian.guardian_id == guardian_id)).first()
    if existing:
        raise BusinessRuleError("This guardian is already linked to the student")

    has_primary = session.exec(select(StudentGuardian).where(
        StudentGuardian.student_id == student_id, StudentGuardian.is_primary == True)).first()  # noqa: E712
    make_primary = link.is_primary or has_primary is None
    if make_primary and has_primary:
        session.execute(update(StudentGuardian).where(StudentGuardian.student_id == student_id).values(is_primary=False))
        session.flush()
    row = StudentGuardian(student_id=student_id, guardian_id=guardian_id,
                          relation_type=link.relation_type, is_primary=make_primary)
    session.add(row)
    session.flush()
    return row


def link_guardian(student_id: int, link: GuardianLinkInput) -> None:
    with session_scope() as session:
        link_in_session(session, student_id, link)


def set_primary(link_id: int) -> None:
    with session_scope() as session:
        row = session.get(StudentGuardian, link_id)
        if row is None:
            raise NotFoundError("Link not found")
        session.execute(update(StudentGuardian).where(StudentGuardian.student_id == row.student_id).values(is_primary=False))
        session.flush()
        row.is_primary = True
        session.add(row)


def unlink(link_id: int) -> None:
    with session_scope() as session:
        row = session.get(StudentGuardian, link_id)
        if row is None:
            raise NotFoundError("Link not found")
        student_id, was_primary = row.student_id, row.is_primary
        session.delete(row)
        session.flush()
        if was_primary:
            replacement = session.exec(select(StudentGuardian).where(StudentGuardian.student_id == student_id)).first()
            if replacement:
                replacement.is_primary = True
                session.add(replacement)
