from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import text
from sqlmodel import Session, select

from data_management.dao import FeeMilestone, FeePlan, StudentFeeDue

_DUE_STATUS_SQL = """
SELECT fee_due_id, enrollment_id, fee_type, fee_plan_id, plan_code, description, override_reason,
       amount_due_paise, amount_paid_paise, balance_paise, created_on
  FROM v_fee_due_status
 WHERE enrollment_id = :enrollment_id
 ORDER BY CASE fee_type WHEN 'TUITION' THEN 0 WHEN 'VAN' THEN 1 ELSE 2 END, fee_due_id
"""

_ASSIGNMENT_SQL = """
SELECT e.id AS enrollment_id, s.id AS student_id, s.admission_no, s.name, e.student_class, e.section, e.roll_no,
       s.category,
       tp.code AS tuition_plan, t.amount_due_paise AS tuition_paise, COALESCE(tv.amount_paid_paise, 0) AS tuition_paid_paise,
       vp.code AS van_plan, v.amount_due_paise AS van_paise
  FROM student_enrollment e
  JOIN student s ON s.id = e.student_id
  LEFT JOIN student_fee_due t ON t.enrollment_id = e.id AND t.fee_type = 'TUITION'
  LEFT JOIN fee_plan tp ON tp.id = t.fee_plan_id
  LEFT JOIN v_fee_due_status tv ON tv.fee_due_id = t.id
  LEFT JOIN student_fee_due v ON v.enrollment_id = e.id AND v.fee_type = 'VAN'
  LEFT JOIN fee_plan vp ON vp.id = v.fee_plan_id
 WHERE e.academic_year_id = :year_id
   AND s.status = 'ACTIVE'
   AND (:student_class IS NULL OR e.student_class = :student_class)
   AND (:section IS NULL OR e.section = :section)
   AND (:category IS NULL OR s.category = :category)
 ORDER BY e.student_class, e.section, COALESCE(e.roll_no, 100000), s.name
"""


def plans_for_year(session: Session, academic_year_id: int) -> List[FeePlan]:
    return list(session.exec(select(FeePlan).where(FeePlan.academic_year_id == academic_year_id)
                             .order_by(FeePlan.fee_type, FeePlan.student_class, FeePlan.code)))


def plan_by_code(session: Session, academic_year_id: int, code: str) -> Optional[FeePlan]:
    return session.exec(select(FeePlan).where(FeePlan.academic_year_id == academic_year_id,
                                              FeePlan.code == code.upper())).first()


def assignment_counts(session: Session, academic_year_id: int) -> Dict[int, int]:
    rows = session.execute(text(
        "SELECT d.fee_plan_id, COUNT(*) FROM student_fee_due d JOIN fee_plan p ON p.id = d.fee_plan_id"
        " WHERE p.academic_year_id = :y GROUP BY d.fee_plan_id"), {"y": academic_year_id})
    return {row[0]: row[1] for row in rows}


def default_plan(session: Session, academic_year_id: int, fee_type: str, student_class: str,
                 category: Optional[str]) -> Optional[FeePlan]:
    """Most specific default: class + category, then class only, then (van) any class."""
    candidates = session.exec(select(FeePlan).where(
        FeePlan.academic_year_id == academic_year_id, FeePlan.fee_type == fee_type,
        FeePlan.is_default == True, FeePlan.is_active == True)).all()  # noqa: E712

    def rank(plan: FeePlan) -> Optional[int]:
        if plan.student_class not in (student_class, None) or plan.category not in (category, None):
            return None
        return (plan.student_class is None) * 2 + (plan.category is None)

    ranked = sorted((r, p.id, p) for p in candidates if (r := rank(p)) is not None)
    return ranked[0][2] if ranked else None


def annual_due(session: Session, enrollment_id: int, fee_type: str) -> Optional[StudentFeeDue]:
    return session.exec(select(StudentFeeDue).where(StudentFeeDue.enrollment_id == enrollment_id,
                                                    StudentFeeDue.fee_type == fee_type)).first()


def dues_with_status(session: Session, enrollment_id: int) -> List[dict]:
    rows = session.execute(text(_DUE_STATUS_SQL), {"enrollment_id": enrollment_id}).mappings()
    return [{**row, "created_on": date.fromisoformat(row["created_on"])} for row in rows]


def paid_amount(session: Session, fee_due_id: int) -> int:
    row = session.execute(text("SELECT amount_paid_paise FROM v_fee_due_status WHERE fee_due_id = :id"),
                          {"id": fee_due_id}).first()
    return row[0] if row else 0


def has_allocations(session: Session, fee_due_id: int) -> bool:
    return session.execute(text("SELECT 1 FROM payment_allocation WHERE fee_due_id = :id LIMIT 1"),
                           {"id": fee_due_id}).first() is not None


def milestones(session: Session, academic_year_id: int) -> List[FeeMilestone]:
    return list(session.exec(select(FeeMilestone).where(FeeMilestone.academic_year_id == academic_year_id)
                             .order_by(FeeMilestone.due_date)))


def receipt_count(session: Session, enrollment_id: int) -> int:
    return session.execute(text("SELECT COUNT(*) FROM payment WHERE enrollment_id = :e AND is_voided = 0"),
                           {"e": enrollment_id}).scalar_one()


def assignment_rows(session: Session, academic_year_id: int, student_class: Optional[str],
                    section: Optional[str], category: Optional[str]) -> List[dict]:
    return [dict(row) for row in session.execute(text(_ASSIGNMENT_SQL), {
        "year_id": academic_year_id, "student_class": student_class, "section": section, "category": category,
    }).mappings()]
