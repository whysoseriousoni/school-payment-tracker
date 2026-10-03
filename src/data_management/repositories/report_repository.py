"""Read-only queries returning DataFrames for analytics and Excel reports (amounts in paise)."""
from datetime import date
from typing import Optional

import pandas as pd
from sqlalchemy import text
from sqlmodel import Session

_DUES_SQL = """
SELECT v.fee_due_id, v.enrollment_id, v.student_id, v.academic_year_id, v.student_class, v.section,
       v.fee_type, v.fee_month, v.description, v.amount_due_paise, v.amount_paid_paise, v.balance_paise,
       substr(d.inserted_on, 1, 10) AS created_on
  FROM v_fee_due_status v JOIN student_fee_due d ON d.id = v.fee_due_id
 WHERE v.academic_year_id = :year_id
"""

_ENROLLMENTS_SQL = """
SELECT e.id AS enrollment_id, e.student_id, e.academic_year_id, e.student_class, e.section, e.roll_no, e.outcome,
       s.admission_no, s.name, s.category, s.status,
       g.name AS guardian_name, g.mobile_number AS guardian_mobile
  FROM student_enrollment e
  JOIN student s ON s.id = e.student_id
  LEFT JOIN student_guardian sg ON sg.student_id = s.id AND sg.is_primary = 1
  LEFT JOIN guardian g ON g.id = sg.guardian_id
 WHERE e.academic_year_id = :year_id
"""

_PAYMENTS_SQL = """
SELECT p.id AS payment_id, p.receipt_no, p.paid_on, p.amount_paise, p.payment_method, p.payment_notes,
       p.billing_name, p.notes, p.collected_by, p.is_voided, p.void_reason,
       p.student_id, s.admission_no, s.name, s.category,
       e.id AS enrollment_id, e.academic_year_id, y.label AS academic_year, e.student_class, e.section, e.roll_no
  FROM payment p
  JOIN student s ON s.id = p.student_id
  JOIN student_enrollment e ON e.id = p.enrollment_id
  JOIN academic_year y ON y.id = e.academic_year_id
 WHERE (:year_id IS NULL OR e.academic_year_id = :year_id)
   AND (:date_from IS NULL OR p.paid_on >= :date_from)
   AND (:date_to IS NULL OR p.paid_on <= :date_to)
   AND (:include_voided = 1 OR p.is_voided = 0)
 ORDER BY p.paid_on, p.id
"""

_ALLOCATIONS_SQL = """
SELECT a.payment_id, p.receipt_no, p.paid_on, p.student_id, e.academic_year_id,
       d.fee_type, d.fee_month, d.description, a.amount_paise
  FROM payment_allocation a
  JOIN payment p ON p.id = a.payment_id AND p.is_voided = 0
  JOIN student_fee_due d ON d.id = a.fee_due_id
  JOIN student_enrollment e ON e.id = p.enrollment_id
 WHERE (:year_id IS NULL OR e.academic_year_id = :year_id)
   AND (:date_from IS NULL OR p.paid_on >= :date_from)
   AND (:date_to IS NULL OR p.paid_on <= :date_to)
"""


def _frame(session: Session, sql: str, params: dict) -> pd.DataFrame:
    result = session.execute(text(sql), params)
    return pd.DataFrame(result.fetchall(), columns=list(result.keys()))


def _iso(value: Optional[date]) -> Optional[str]:
    return value.isoformat() if value else None


def dues(session: Session, year_id: int) -> pd.DataFrame:
    return _frame(session, _DUES_SQL, {"year_id": year_id})


def enrollments(session: Session, year_id: int) -> pd.DataFrame:
    return _frame(session, _ENROLLMENTS_SQL, {"year_id": year_id})


def payments(session: Session, year_id: Optional[int] = None, date_from: Optional[date] = None,
             date_to: Optional[date] = None, include_voided: bool = False) -> pd.DataFrame:
    return _frame(session, _PAYMENTS_SQL, {"year_id": year_id, "date_from": _iso(date_from),
                                           "date_to": _iso(date_to), "include_voided": int(include_voided)})


def allocations(session: Session, year_id: Optional[int] = None, date_from: Optional[date] = None,
                date_to: Optional[date] = None) -> pd.DataFrame:
    return _frame(session, _ALLOCATIONS_SQL, {"year_id": year_id, "date_from": _iso(date_from),
                                              "date_to": _iso(date_to)})


def years(session: Session) -> pd.DataFrame:
    return _frame(session, "SELECT id, label, start_date, end_date, is_current FROM academic_year ORDER BY start_date", {})
