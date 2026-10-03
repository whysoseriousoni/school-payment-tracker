from datetime import date
from typing import List, Optional

from sqlalchemy import text
from sqlmodel import Session

_PAYMENT_SQL = """
SELECT p.*, s.name AS student_name, s.admission_no, y.label AS academic_year_label,
       e.student_class, e.section
  FROM payment p
  JOIN student s ON s.id = p.student_id
  JOIN student_enrollment e ON e.id = p.enrollment_id
  JOIN academic_year y ON y.id = e.academic_year_id
 WHERE (:payment_id IS NULL OR p.id = :payment_id)
   AND (:receipt_no IS NULL OR p.receipt_no = :receipt_no COLLATE NOCASE)
   AND (:student_id IS NULL OR p.student_id = :student_id)
   AND (:enrollment_id IS NULL OR p.enrollment_id = :enrollment_id)
   AND (:date_from IS NULL OR p.paid_on >= :date_from)
   AND (:date_to IS NULL OR p.paid_on <= :date_to)
 ORDER BY p.paid_on DESC, p.id DESC
 LIMIT :limit
"""

_ALLOCATIONS_SQL = """
SELECT a.payment_id, a.fee_due_id, a.amount_paise, d.fee_type, d.description, fp.code AS plan_code
  FROM payment_allocation a
  JOIN student_fee_due d ON d.id = a.fee_due_id
  LEFT JOIN fee_plan fp ON fp.id = d.fee_plan_id
 WHERE a.payment_id IN ({ids})
 ORDER BY CASE d.fee_type WHEN 'TUITION' THEN 0 WHEN 'VAN' THEN 1 ELSE 2 END, d.id
"""


def find(session: Session, payment_id: Optional[int] = None, receipt_no: Optional[str] = None,
         student_id: Optional[int] = None, enrollment_id: Optional[int] = None,
         date_from: Optional[date] = None, date_to: Optional[date] = None, limit: int = 1000) -> List[dict]:
    params = {
        "payment_id": payment_id, "receipt_no": receipt_no, "student_id": student_id, "enrollment_id": enrollment_id,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None, "limit": limit,
    }
    return [dict(row) for row in session.execute(text(_PAYMENT_SQL), params).mappings()]


def allocations_for(session: Session, payment_ids: List[int]) -> List[dict]:
    if not payment_ids:
        return []
    placeholders = ", ".join(f":p{index}" for index in range(len(payment_ids)))
    params = {f"p{index}": value for index, value in enumerate(payment_ids)}
    return [dict(row) for row in session.execute(text(_ALLOCATIONS_SQL.format(ids=placeholders)), params).mappings()]


def next_receipt_number(session: Session, academic_year_id: int) -> int:
    """Atomic increment (SQLite UPSERT ... RETURNING takes the write lock immediately)."""
    return session.execute(
        text(
            "INSERT INTO receipt_counter (academic_year_id, last_number) VALUES (:y, 1) "
            "ON CONFLICT(academic_year_id) DO UPDATE SET last_number = last_number + 1 RETURNING last_number"
        ),
        {"y": academic_year_id},
    ).scalar_one()
