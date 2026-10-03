from datetime import date
from typing import List, Optional, Set

from sqlalchemy import text
from sqlmodel import Session, select

from data_management.dao import FeeStructure, StudentFeeDue

_DUE_STATUS_SQL = """
SELECT fee_due_id, enrollment_id, fee_type, fee_month, description,
       amount_due_paise, amount_paid_paise, balance_paise
  FROM v_fee_due_status
 WHERE enrollment_id = :enrollment_id
 ORDER BY CASE WHEN fee_month IS NULL THEN 1 ELSE 0 END, fee_month,
          CASE fee_type WHEN 'TUITION' THEN 0 WHEN 'VAN' THEN 1 ELSE 2 END, fee_due_id
"""


def structure_for(session: Session, academic_year_id: int, student_class: str, fee_type: str) -> Optional[FeeStructure]:
    return session.exec(
        select(FeeStructure).where(
            FeeStructure.academic_year_id == academic_year_id,
            FeeStructure.student_class == student_class,
            FeeStructure.fee_type == fee_type,
        )
    ).first()


def structures_for_year(session: Session, academic_year_id: int) -> List[FeeStructure]:
    return list(session.exec(select(FeeStructure).where(FeeStructure.academic_year_id == academic_year_id)))


def dues_with_status(session: Session, enrollment_id: int) -> List[dict]:
    rows = session.execute(text(_DUE_STATUS_SQL), {"enrollment_id": enrollment_id}).mappings()
    result = []
    for row in rows:
        record = dict(row)
        if record["fee_month"]:
            record["fee_month"] = date.fromisoformat(record["fee_month"])
        result.append(record)
    return result


def paid_amount(session: Session, fee_due_id: int) -> int:
    row = session.execute(
        text("SELECT amount_paid_paise FROM v_fee_due_status WHERE fee_due_id = :id"), {"id": fee_due_id}
    ).first()
    return row[0] if row else 0


def recurring_dues(session: Session, enrollment_id: int, fee_type: str) -> List[StudentFeeDue]:
    return list(session.exec(
        select(StudentFeeDue)
        .where(StudentFeeDue.enrollment_id == enrollment_id, StudentFeeDue.fee_type == fee_type,
               StudentFeeDue.fee_month.is_not(None))
        .order_by(StudentFeeDue.fee_month)
    ))


def existing_months(session: Session, enrollment_id: int, fee_type: str) -> Set[date]:
    return {due.fee_month for due in recurring_dues(session, enrollment_id, fee_type)}


def has_allocations(session: Session, fee_due_id: int) -> bool:
    return session.execute(
        text("SELECT 1 FROM payment_allocation WHERE fee_due_id = :id LIMIT 1"), {"id": fee_due_id}
    ).first() is not None
