"""Fee structures and the per-student dues ledger."""
from datetime import date
from typing import Dict, List, Optional

from sqlmodel import Session, select

from data_management.dao import AcademicYear, FeeStructure, Student, StudentEnrollment, StudentFeeDue
from data_management.dto.fee import FeeDueRead, FeeStructureInput, FeeStructureRead, OneOffDueCreate, VanChange
from data_management.repositories import fee_repository as repo
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper.school_calendar import fee_months
from statics import EnrollmentOutcome, FeeType, StudentStatus


# ---------- internal helpers (used by other services inside their transaction) ----------

def first_of_month(value: date) -> date:
    return value.replace(day=1)


def year_months(year: AcademicYear) -> List[date]:
    return fee_months(year.start_date.year)


def dues_start_month(year: AcademicYear, date_of_join: Optional[date]) -> date:
    """A student who joins mid-year pays from their joining month onwards."""
    months = year_months(year)
    if date_of_join is None or date_of_join <= year.start_date:
        return months[0]
    if date_of_join > year.end_date:
        return months[-1]
    return first_of_month(date_of_join)


def get_enrollment(session: Session, enrollment_id: int) -> StudentEnrollment:
    enrollment = session.get(StudentEnrollment, enrollment_id)
    if enrollment is None:
        raise NotFoundError(f"Enrollment {enrollment_id} not found")
    return enrollment


def generate_recurring_dues(session: Session, enrollment: StudentEnrollment, fee_type: str,
                            monthly_paise: int, from_month: Optional[date] = None) -> int:
    """Creates any missing monthly dues from `from_month` to May. Returns how many were created."""
    year = session.get(AcademicYear, enrollment.academic_year_id)
    existing = repo.existing_months(session, enrollment.id, fee_type)
    created = 0
    for month in year_months(year):
        if from_month and month < first_of_month(from_month):
            continue
        if month in existing:
            continue
        session.add(StudentFeeDue(enrollment_id=enrollment.id, fee_type=fee_type, fee_month=month,
                                  amount_due_paise=monthly_paise))
        created += 1
    session.flush()
    return created


def generate_tuition_from_structure(session: Session, enrollment: StudentEnrollment,
                                    from_month: Optional[date] = None) -> int:
    structure = repo.structure_for(session, enrollment.academic_year_id, enrollment.student_class,
                                   FeeType.TUITION.value)
    if structure is None or not structure.is_active:
        return 0
    return generate_recurring_dues(session, enrollment, FeeType.TUITION.value,
                                   structure.monthly_amount_paise, from_month)


def remove_or_trim_recurring_dues(session: Session, enrollment_id: int, after_or_on: date,
                                  fee_types=(FeeType.TUITION.value, FeeType.VAN.value)) -> Dict[str, int]:
    """
    Stops recurring fees from `after_or_on` (a month start): unpaid months are
    deleted, part-paid months are reduced to what was already paid.
    """
    removed = trimmed = 0
    for fee_type in fee_types:
        for due in repo.recurring_dues(session, enrollment_id, fee_type):
            if due.fee_month < after_or_on:
                continue
            paid = repo.paid_amount(session, due.id)
            if not repo.has_allocations(session, due.id):
                session.delete(due)
                removed += 1
            elif paid < due.amount_due_paise:
                due.amount_due_paise = paid
                session.add(due)
                trimmed += 1
    session.flush()
    return {"removed": removed, "trimmed": trimmed}


def dues_for(session: Session, enrollment_id: int) -> List[FeeDueRead]:
    return [FeeDueRead(**row) for row in repo.dues_with_status(session, enrollment_id)]


# ---------- fee structures ----------

def list_structures(academic_year_id: int) -> List[FeeStructureRead]:
    with session_scope() as session:
        return [FeeStructureRead.model_validate(row) for row in repo.structures_for_year(session, academic_year_id)]


def default_monthly_fee(academic_year_id: int, student_class: str, fee_type: str) -> Optional[int]:
    with session_scope() as session:
        structure = repo.structure_for(session, academic_year_id, student_class, fee_type)
        return structure.monthly_amount_paise if structure and structure.is_active else None


def save_structure(data: FeeStructureInput) -> FeeStructureRead:
    with session_scope() as session:
        if session.get(AcademicYear, data.academic_year_id) is None:
            raise NotFoundError("Academic year not found")
        structure = repo.structure_for(session, data.academic_year_id, data.student_class, data.fee_type)
        if structure is None:
            structure = FeeStructure(**data.model_dump())
        else:
            structure.monthly_amount_paise = data.monthly_amount_paise
            structure.is_active = True
        session.add(structure)
        session.flush()
        return FeeStructureRead.model_validate(structure)


def apply_tuition_structure(academic_year_id: int, student_class: Optional[str] = None,
                            update_unpaid: bool = False) -> Dict[str, int]:
    """
    Brings active students' tuition dues in line with the fee structure:
    creates missing months (from each student's joining month) and, if
    `update_unpaid`, changes the amount of months that have no payment yet.
    """
    created = updated = 0
    with session_scope() as session:
        year = session.get(AcademicYear, academic_year_id)
        if year is None:
            raise NotFoundError("Academic year not found")
        query = (
            select(StudentEnrollment, Student)
            .join(Student, Student.id == StudentEnrollment.student_id)
            .where(StudentEnrollment.academic_year_id == academic_year_id,
                   Student.status == StudentStatus.ACTIVE.value)
        )
        if student_class:
            query = query.where(StudentEnrollment.student_class == student_class)
        for enrollment, student in session.exec(query).all():
            if enrollment.outcome in (EnrollmentOutcome.LEFT.value, EnrollmentOutcome.PASSED_OUT.value):
                continue
            created += generate_tuition_from_structure(session, enrollment, dues_start_month(year, student.date_of_join))
            if not update_unpaid:
                continue
            structure = repo.structure_for(session, academic_year_id, enrollment.student_class, FeeType.TUITION.value)
            if structure is None:
                continue
            for due in repo.recurring_dues(session, enrollment.id, FeeType.TUITION.value):
                if due.amount_due_paise != structure.monthly_amount_paise and not repo.has_allocations(session, due.id):
                    due.amount_due_paise = structure.monthly_amount_paise
                    session.add(due)
                    updated += 1
    return {"created": created, "updated": updated}


# ---------- ledger ----------

def get_ledger(enrollment_id: int) -> List[FeeDueRead]:
    with session_scope() as session:
        get_enrollment(session, enrollment_id)
        return dues_for(session, enrollment_id)


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


# ---------- van ----------

def _check_month_in_year(session: Session, enrollment: StudentEnrollment, month: date) -> date:
    month = first_of_month(month)
    if month not in year_months(session.get(AcademicYear, enrollment.academic_year_id)):
        raise BusinessRuleError("The month must fall inside the enrollment's academic year (June to May)")
    return month


def start_van(data: VanChange) -> int:
    """Van fee from `from_month` to May. Unpaid future months take the new amount."""
    with session_scope() as session:
        enrollment = get_enrollment(session, data.enrollment_id)
        from_month = _check_month_in_year(session, enrollment, data.from_month)
        for due in repo.recurring_dues(session, enrollment.id, FeeType.VAN.value):
            if due.fee_month >= from_month and not repo.has_allocations(session, due.id):
                due.amount_due_paise = data.monthly_amount_paise
                session.add(due)
        return generate_recurring_dues(session, enrollment, FeeType.VAN.value, data.monthly_amount_paise, from_month)


def stop_van(enrollment_id: int, from_month: date) -> Dict[str, int]:
    with session_scope() as session:
        enrollment = get_enrollment(session, enrollment_id)
        month = _check_month_in_year(session, enrollment, from_month)
        return remove_or_trim_recurring_dues(session, enrollment_id, month, fee_types=(FeeType.VAN.value,))
