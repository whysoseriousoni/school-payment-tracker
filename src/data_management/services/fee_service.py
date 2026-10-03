"""
Fee plans, milestones, fee assignment and the per-student ledger.

Tuition and van are annual fees: one due per student per term, taken from the
assigned fee plan (or a custom amount with a reason) and paid in any number of
instalments. One-off fees (books, uniform, custom) are added per student.
"""
from datetime import date
from typing import Dict, List, Optional

from sqlalchemy import delete, update
from sqlmodel import Session, select

from data_management.dao import AcademicYear, FeeMilestone, FeePlan, Student, StudentEnrollment, StudentFeeDue
from data_management.dto.fee import (
    AssignmentRow,
    FeeAssignment,
    FeeDueRead,
    FeePlanInput,
    FeePlanRead,
    MilestoneRead,
    MilestoneSet,
    OneOffDueCreate,
    PlanSaveResult,
    fee_type_label,
)
from data_management.repositories import fee_repository as repo
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper import fee_rules
from helper.clock import today_ist
from helper.money import format_inr
from statics import EnrollmentOutcome, FeeType, StudentStatus


# ---------- helpers shared with other services (run inside their transaction) ----------

def get_enrollment(session: Session, enrollment_id: int) -> StudentEnrollment:
    enrollment = session.get(StudentEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError(f"Enrollment {enrollment_id} not found")
    return enrollment


def _plan_read(plan: FeePlan, counts: Optional[Dict[int, int]] = None) -> FeePlanRead:
    return FeePlanRead.model_validate(plan).model_copy(update={"students_assigned": (counts or {}).get(plan.id, 0)})


def assign_in_session(session: Session, enrollment: StudentEnrollment, fee_type: str,
                      plan: Optional[FeePlan] = None, custom_amount_paise: Optional[int] = None,
                      reason: Optional[str] = None) -> StudentFeeDue:
    """Creates or changes the student's annual due for `fee_type`."""
    if plan is not None:
        if plan.academic_year_id != enrollment.academic_year_id or plan.fee_type != fee_type:
            raise BusinessRuleError(f"Plan {plan.code} is not a {fee_type_label(fee_type)} plan for this term")
        if not plan.is_active:
            raise BusinessRuleError(f"Plan {plan.code} is inactive")
        amount, plan_id, override = plan.annual_amount_paise, plan.id, None
    else:
        amount, plan_id, override = custom_amount_paise, None, reason

    due = repo.annual_due(session, enrollment.id, fee_type)
    if due is None:
        due = StudentFeeDue(enrollment_id=enrollment.id, fee_type=fee_type)
    else:
        paid = repo.paid_amount(session, due.id)
        if amount < paid:
            raise BusinessRuleError(f"{format_inr(paid)} has already been paid towards {fee_type_label(fee_type)}; "
                                    f"the new amount cannot be lower than that")
    due.fee_plan_id, due.amount_due_paise, due.override_reason = plan_id, amount, override
    session.add(due)
    session.flush()
    return due


def assign_default_tuition(session: Session, enrollment: StudentEnrollment, category: Optional[str]) -> bool:
    """Gives a new enrollment its default tuition plan. Returns False when no default plan exists."""
    if repo.annual_due(session, enrollment.id, FeeType.TUITION.value):
        return True
    plan = repo.default_plan(session, enrollment.academic_year_id, FeeType.TUITION.value,
                             enrollment.student_class, category)
    if plan is None:
        return False
    assign_in_session(session, enrollment, FeeType.TUITION.value, plan=plan)
    return True


def stop_annual_fees(session: Session, enrollment_id: int, reason: str,
                     fee_types=(FeeType.TUITION.value, FeeType.VAN.value)) -> Dict[str, int]:
    """Unpaid annual fees are removed; part-paid ones are reduced to what has been paid."""
    removed = trimmed = 0
    for fee_type in fee_types:
        due = repo.annual_due(session, enrollment_id, fee_type)
        if due is None:
            continue
        paid = repo.paid_amount(session, due.id)
        if not repo.has_allocations(session, due.id):
            session.delete(due)
            removed += 1
        elif paid < due.amount_due_paise:
            due.amount_due_paise = paid
            due.override_reason = reason
            session.add(due)
            trimmed += 1
    session.flush()
    return {"removed": removed, "trimmed": trimmed}


def dues_for(session: Session, enrollment_id: int) -> List[FeeDueRead]:
    return [FeeDueRead(**row) for row in repo.dues_with_status(session, enrollment_id)]


# ---------- plans ----------

def list_plans(academic_year_id: int, fee_type: Optional[str] = None, active_only: bool = False) -> List[FeePlanRead]:
    with session_scope() as session:
        counts = repo.assignment_counts(session, academic_year_id)
        plans = repo.plans_for_year(session, academic_year_id)
        return [_plan_read(p, counts) for p in plans
                if (fee_type is None or p.fee_type == fee_type) and (p.is_active or not active_only)]


def save_plan(data: FeePlanInput, plan_id: Optional[int] = None) -> PlanSaveResult:
    """Creates or updates a plan. A changed amount flows to every student on the plan (unless already overpaid)."""
    with session_scope() as session:
        if session.get(AcademicYear, data.academic_year_id) is None:
            raise NotFoundError("Academic year not found")
        same_code = repo.plan_by_code(session, data.academic_year_id, data.code)
        if same_code and same_code.id != plan_id:
            raise BusinessRuleError(f"Plan code {data.code} already exists in this term")
        plan = session.get(FeePlan, plan_id) if plan_id else FeePlan(academic_year_id=data.academic_year_id)
        if plan is None:
            raise NotFoundError("Fee plan not found")
        if plan_id and plan.fee_type != data.fee_type and repo.assignment_counts(session, plan.academic_year_id).get(plan.id):
            raise BusinessRuleError(f"{plan.code} is assigned to students; its fee type cannot change")

        if data.is_default:  # one default per term + fee type + class + category
            session.execute(update(FeePlan).where(
                FeePlan.academic_year_id == data.academic_year_id, FeePlan.fee_type == data.fee_type,
                FeePlan.student_class.is_(None) if data.student_class is None else FeePlan.student_class == data.student_class,
                FeePlan.category.is_(None) if data.category is None else FeePlan.category == data.category,
                FeePlan.id != (plan_id or -1)).values(is_default=False))
            session.flush()
        for field, value in data.model_dump().items():
            setattr(plan, field, value)
        session.add(plan)
        session.flush()

        updated, skipped = 0, []
        dues = session.exec(select(StudentFeeDue).where(StudentFeeDue.fee_plan_id == plan.id)).all()
        for due in dues:
            if due.amount_due_paise == plan.annual_amount_paise:
                continue
            if repo.paid_amount(session, due.id) > plan.annual_amount_paise:
                enrollment = session.get(StudentEnrollment, due.enrollment_id)
                skipped.append(session.get(Student, enrollment.student_id).name)
                continue
            due.amount_due_paise = plan.annual_amount_paise
            session.add(due)
            updated += 1
        session.flush()
        counts = repo.assignment_counts(session, plan.academic_year_id)
        return PlanSaveResult(plan=_plan_read(plan, counts), dues_updated=updated, dues_skipped=skipped)


def delete_plan(plan_id: int) -> None:
    with session_scope() as session:
        plan = session.get(FeePlan, plan_id)
        if plan is None:
            raise NotFoundError("Fee plan not found")
        if repo.assignment_counts(session, plan.academic_year_id).get(plan_id):
            raise BusinessRuleError(f"{plan.code} is assigned to students; deactivate it instead")
        session.delete(plan)


def copy_plans(from_year_id: int, to_year_id: int, increase_percent: float = 0.0) -> int:
    """Copies plans (and milestones, shifted by whole years) into another term; existing codes are kept."""
    with session_scope() as session:
        source = session.get(AcademicYear, from_year_id)
        target = session.get(AcademicYear, to_year_id)
        if source is None or target is None:
            raise NotFoundError("Academic year not found")
        copied = 0
        for plan in repo.plans_for_year(session, from_year_id):
            if repo.plan_by_code(session, to_year_id, plan.code):
                continue
            amount = int(round(plan.annual_amount_paise * (1 + increase_percent / 100) / 100)) * 100
            session.add(FeePlan(academic_year_id=to_year_id, code=plan.code, fee_type=plan.fee_type,
                                student_class=plan.student_class, category=plan.category,
                                annual_amount_paise=amount, is_default=plan.is_default, is_active=plan.is_active,
                                description=plan.description))
            copied += 1
        if not repo.milestones(session, to_year_id):
            shift = target.start_date.year - source.start_date.year
            for milestone in repo.milestones(session, from_year_id):
                try:
                    shifted = milestone.due_date.replace(year=milestone.due_date.year + shift)
                except ValueError:  # 29 Feb
                    shifted = milestone.due_date.replace(year=milestone.due_date.year + shift, day=28)
                session.add(FeeMilestone(academic_year_id=to_year_id, due_date=shifted,
                                         cumulative_percent=milestone.cumulative_percent))
        return copied


# ---------- milestones ----------

def get_milestones(academic_year_id: int) -> List[MilestoneRead]:
    with session_scope() as session:
        return [MilestoneRead.model_validate(m) for m in repo.milestones(session, academic_year_id)]


def save_milestones(data: MilestoneSet) -> None:
    with session_scope() as session:
        year = session.get(AcademicYear, data.academic_year_id)
        if year is None:
            raise NotFoundError("Academic year not found")
        for milestone in data.milestones:
            if not year.start_date <= milestone.due_date <= year.end_date:
                raise BusinessRuleError(f"{milestone.due_date:%d %b %Y} is outside term {year.label}")
        session.execute(delete(FeeMilestone).where(FeeMilestone.academic_year_id == year.id))
        for milestone in data.milestones:
            session.add(FeeMilestone(academic_year_id=year.id, **milestone.model_dump()))


# ---------- assignment ----------

def assignment_rows(academic_year_id: int, student_class: Optional[str] = None, section: Optional[str] = None,
                    category: Optional[str] = None) -> List[AssignmentRow]:
    with session_scope() as session:
        return [AssignmentRow(**row) for row in repo.assignment_rows(session, academic_year_id, student_class,
                                                                     section, category)]


def assign(data: FeeAssignment) -> FeeDueRead:
    with session_scope() as session:
        enrollment = get_enrollment(session, data.enrollment_id)
        plan = None
        if data.fee_plan_id is not None:
            plan = session.get(FeePlan, data.fee_plan_id)
            if plan is None:
                raise NotFoundError("Fee plan not found")
        due = assign_in_session(session, enrollment, data.fee_type, plan, data.custom_amount_paise, data.reason)
        return next(d for d in dues_for(session, enrollment.id) if d.fee_due_id == due.id)


def assign_defaults(academic_year_id: int, student_class: Optional[str] = None) -> Dict[str, object]:
    """Gives every active student without tuition their default plan. Reports who has no matching plan."""
    assigned, missing = 0, []
    with session_scope() as session:
        query = (select(StudentEnrollment, Student).join(Student, Student.id == StudentEnrollment.student_id)
                 .where(StudentEnrollment.academic_year_id == academic_year_id,
                        Student.status == StudentStatus.ACTIVE.value))
        if student_class:
            query = query.where(StudentEnrollment.student_class == student_class)
        for enrollment, student in session.exec(query).all():
            if enrollment.outcome in (EnrollmentOutcome.LEFT.value, EnrollmentOutcome.PASSED_OUT.value):
                continue
            if repo.annual_due(session, enrollment.id, FeeType.TUITION.value):
                continue
            if assign_default_tuition(session, enrollment, student.category):
                assigned += 1
            else:
                missing.append(f"{student.name} ({enrollment.student_class}, {student.category or 'no category'})")
    return {"assigned": assigned, "missing": missing}


def remove_van(enrollment_id: int) -> Dict[str, int]:
    with session_scope() as session:
        get_enrollment(session, enrollment_id)
        return stop_annual_fees(session, enrollment_id, f"Van stopped on {today_ist():%d %b %Y}",
                                fee_types=(FeeType.VAN.value,))


# ---------- ledger ----------

def get_ledger(enrollment_id: int) -> List[FeeDueRead]:
    with session_scope() as session:
        get_enrollment(session, enrollment_id)
        return dues_for(session, enrollment_id)


def receipt_count(enrollment_id: int) -> int:
    with session_scope() as session:
        return repo.receipt_count(session, enrollment_id)


def add_one_off_due(data: OneOffDueCreate) -> FeeDueRead:
    with session_scope() as session:
        get_enrollment(session, data.enrollment_id)
        due = StudentFeeDue(enrollment_id=data.enrollment_id, fee_type=data.fee_type,
                            description=data.description, amount_due_paise=data.amount_paise)
        session.add(due)
        session.flush()
        return next(item for item in dues_for(session, data.enrollment_id) if item.fee_due_id == due.id)


def remove_due(fee_due_id: int) -> None:
    with session_scope() as session:
        due = session.get(StudentFeeDue, fee_due_id)
        if due is None:
            raise NotFoundError("Fee not found")
        if repo.has_allocations(session, fee_due_id):
            raise BusinessRuleError("This fee has payments against it; void those receipts first")
        session.delete(due)


def payment_status(enrollment_id: int, as_of: Optional[date] = None) -> dict:
    """Expected and overdue amounts for one student, using the term's milestones."""
    with session_scope() as session:
        enrollment = get_enrollment(session, enrollment_id)
        year = session.get(AcademicYear, enrollment.academic_year_id)
        as_of = max(year.start_date, min(as_of or today_ist(), year.end_date))
        milestones = [(m.due_date, m.cumulative_percent) for m in repo.milestones(session, year.id)]
        percent = fee_rules.expected_percent(milestones, as_of, year.end_date)
        expected = overdue = 0
        for due in dues_for(session, enrollment_id):
            if due.is_annual:
                due_expected = fee_rules.expected_amount(due.amount_due_paise, percent)
            else:
                due_expected = due.amount_due_paise if due.created_on <= as_of else 0
            expected += due_expected
            overdue += max(0, due_expected - due.amount_paid_paise)
        upcoming = fee_rules.next_milestone(milestones, as_of)
        return {"as_of": as_of, "expected_percent": percent, "expected_paise": expected, "overdue_paise": overdue,
                "next_milestone": upcoming, "has_milestones": bool(milestones),
                "receipts": repo.receipt_count(session, enrollment_id)}
