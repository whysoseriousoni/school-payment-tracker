from typing import List, Optional

from sqlalchemy import text
from sqlmodel import Session, select

from data_management.dao import Guardian, StudentEnrollment, StudentGuardian
from data_management.dto.student import StudentSearch

_SEARCH_SQL = """
SELECT s.id AS student_id, s.admission_no, s.name, s.status, s.category,
       e.id AS enrollment_id, y.label AS academic_year_label, e.student_class, e.section, e.roll_no,
       g.name AS guardian_name, g.mobile_number AS guardian_mobile
  FROM student s
  LEFT JOIN student_enrollment e ON e.student_id = s.id AND e.academic_year_id = :year_id
  LEFT JOIN academic_year y ON y.id = e.academic_year_id
  LEFT JOIN student_guardian sg ON sg.student_id = s.id AND sg.is_primary = 1
  LEFT JOIN guardian g ON g.id = sg.guardian_id
 WHERE (:year_id IS NULL OR e.id IS NOT NULL)
   AND (:student_class IS NULL OR e.student_class = :student_class)
   AND (:section IS NULL OR e.section = :section)
   AND (:category IS NULL OR s.category = :category)
   AND (:status IS NULL OR s.status = :status)
   AND (:text IS NULL
        OR s.name LIKE '%' || :text || '%'
        OR s.admission_no = :text COLLATE NOCASE
        OR CAST(s.id AS TEXT) = :text
        OR g.mobile_number = :text)
 ORDER BY CASE WHEN e.student_class IS NULL THEN 99 ELSE 0 END,
          e.student_class, e.section, COALESCE(e.roll_no, 100000), s.name
 LIMIT :limit
"""

_ENROLLMENTS_SQL = """
SELECT e.id AS enrollment_id, e.academic_year_id, y.label AS academic_year_label,
       e.student_class, e.section, e.roll_no, e.outcome
  FROM student_enrollment e JOIN academic_year y ON y.id = e.academic_year_id
 WHERE e.student_id = :student_id
 ORDER BY y.start_date DESC
"""


def search(session: Session, criteria: StudentSearch) -> List[dict]:
    params = criteria.model_dump()
    params["year_id"] = params.pop("academic_year_id")
    return [dict(row) for row in session.execute(text(_SEARCH_SQL), params).mappings()]


def enrollments_of(session: Session, student_id: int) -> List[dict]:
    return [dict(row) for row in session.execute(text(_ENROLLMENTS_SQL), {"student_id": student_id}).mappings()]


def enrollment_for(session: Session, student_id: int, academic_year_id: int) -> Optional[StudentEnrollment]:
    return session.exec(
        select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id, StudentEnrollment.academic_year_id == academic_year_id
        )
    ).first()


def guardian_links_of(session: Session, student_id: int) -> List[dict]:
    rows = session.exec(
        select(StudentGuardian, Guardian)
        .join(Guardian, Guardian.id == StudentGuardian.guardian_id)
        .where(StudentGuardian.student_id == student_id)
        .order_by(StudentGuardian.is_primary.desc(), Guardian.name)
    ).all()
    return [
        {"link_id": link.id, "guardian_id": guardian.id, "name": guardian.name,
         "mobile_number": guardian.mobile_number, "relation_type": link.relation_type, "is_primary": link.is_primary}
        for link, guardian in rows
    ]


def has_payments(session: Session, student_id: int) -> bool:
    return session.execute(
        text("SELECT 1 FROM payment WHERE student_id = :id LIMIT 1"), {"id": student_id}
    ).first() is not None


def next_admission_number(session: Session, year_label: str) -> str:
    """ADM/2026-27/0001 style; continues after the highest number used this year."""
    prefix = f"ADM/{year_label}/"
    row = session.execute(
        text("SELECT MAX(CAST(substr(admission_no, :start) AS INTEGER)) FROM student WHERE admission_no LIKE :pattern"),
        {"start": len(prefix) + 1, "pattern": prefix + "%"},
    ).first()
    return f"{prefix}{(row[0] or 0) + 1:04d}"


def used_roll_numbers(session: Session, academic_year_id: int, student_class: str, section: str) -> List[int]:
    return [
        row[0] for row in session.execute(
            text("SELECT roll_no FROM student_enrollment WHERE academic_year_id = :y AND student_class = :c"
                 " AND section = :s AND roll_no IS NOT NULL"),
            {"y": academic_year_id, "c": student_class, "s": section},
        )
    ]
