"""Students, their yearly enrollments and their encrypted identifiers."""
from typing import List, Optional

from sqlalchemy import delete
from sqlmodel import Session, select

from data_management.dao import (
    AcademicYear,
    FeePlan,
    Identifier,
    Student,
    StudentEnrollment,
    StudentFeeDue,
    StudentGuardian,
)
from data_management.dto.guardian import GuardianLinkRead
from data_management.dto.student import (
    EnrollmentRead,
    EnrollmentUpdate,
    IdentifierInput,
    StudentCreate,
    StudentLeaving,
    StudentProfile,
    StudentSearch,
    StudentSearchResult,
    StudentUpdate,
)
from data_management.repositories import fee_repository
from data_management.repositories import student_repository as repo
from data_management.services import fee_service, guardian_service, identifier_crypto
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper.logger import get_logger
from statics import EnrollmentOutcome, FeeType, StudentStatus

logger = get_logger(__name__)


# ---------- internal helpers ----------

def _get_student(session: Session, student_id: int) -> Student:
    student = session.get(Student, student_id)
    if student is None:
        raise NotFoundError(f"Student {student_id} not found")
    return student


def _get_plan(session: Session, plan_id: int) -> FeePlan:
    plan = session.get(FeePlan, plan_id)
    if plan is None:
        raise NotFoundError("Fee plan not found")
    return plan


def _check_admission_no_free(session: Session, admission_no: str, student_id: Optional[int] = None) -> None:
    clash = session.exec(select(Student).where(Student.admission_no == admission_no)).first()
    if clash and clash.id != student_id:
        raise BusinessRuleError(f"Admission number {admission_no} is already used by {clash.name}")


def _check_roll_no_free(session: Session, academic_year_id: int, student_class: str, section: str,
                        roll_no: Optional[int], enrollment_id: Optional[int] = None) -> None:
    if roll_no is None:
        return
    clash = session.exec(select(StudentEnrollment).where(
        StudentEnrollment.academic_year_id == academic_year_id, StudentEnrollment.student_class == student_class,
        StudentEnrollment.section == section, StudentEnrollment.roll_no == roll_no)).first()
    if clash and clash.id != enrollment_id:
        raise BusinessRuleError(f"Roll number {roll_no} is already taken in {student_class}-{section}")


def _save_identifier(session: Session, student: Student, data: IdentifierInput) -> None:
    identifier = session.get(Identifier, student.identifier_id) if student.identifier_id else None
    if identifier is None:
        identifier = Identifier(identifier_type=data.identifier_type, last_4_digits=data.last_4_digits)
    identifier.identifier_type = data.identifier_type
    identifier.last_4_digits = data.last_4_digits
    identifier.key_version = identifier_crypto.KEY_VERSION
    if data.full_number:
        fingerprint = identifier_crypto.fingerprint(data.full_number, data.identifier_type)
        duplicate = session.exec(select(Identifier).where(Identifier.fingerprint == fingerprint)).first()
        if duplicate and duplicate.id != identifier.id:
            owner = session.exec(select(Student).where(Student.identifier_id == duplicate.id)).first()
            raise BusinessRuleError(
                f"This {data.identifier_type} number is already registered"
                + (f" to {owner.name} ({owner.admission_no})" if owner else "")
            )
        identifier.ciphertext, identifier.nonce = identifier_crypto.encrypt(
            data.full_number, student.id, data.identifier_type)
        identifier.fingerprint = fingerprint
    else:
        identifier.ciphertext = identifier.nonce = identifier.fingerprint = None
    session.add(identifier)
    session.flush()
    student.identifier_id = identifier.id
    session.add(student)


def _profile(session: Session, student_id: int) -> StudentProfile:
    student = _get_student(session, student_id)
    identifier = session.get(Identifier, student.identifier_id) if student.identifier_id else None
    return StudentProfile(
        student_id=student.id, admission_no=student.admission_no, name=student.name,
        date_of_birth=student.date_of_birth, category=student.category, status=student.status,
        date_of_join=student.date_of_join, class_joined=student.class_joined,
        date_of_leaving=student.date_of_leaving, notes=student.notes,
        identifier_type=identifier.identifier_type if identifier else None,
        identifier_last_4=identifier.last_4_digits if identifier else None,
        has_full_identifier=bool(identifier and identifier.ciphertext),
        enrollments=[EnrollmentRead(**row) for row in repo.enrollments_of(session, student.id)],
        guardians=[GuardianLinkRead(**row) for row in repo.guardian_links_of(session, student.id)],
        has_payments=repo.has_payments(session, student.id),
    )


# ---------- queries ----------

def search_students(criteria: StudentSearch) -> List[StudentSearchResult]:
    with session_scope() as session:
        return [StudentSearchResult(**row) for row in repo.search(session, criteria)]


def get_profile(student_id: int) -> StudentProfile:
    with session_scope() as session:
        return _profile(session, student_id)


def find_by_id_or_admission_no(value: str) -> Optional[StudentProfile]:
    value = (value or "").strip()
    if not value:
        return None
    with session_scope() as session:
        student = None
        if value.isdigit():
            student = session.get(Student, int(value))
        if student is None:
            student = session.exec(select(Student).where(Student.admission_no == value)).first()
        return _profile(session, student.id) if student else None


def suggest_admission_number(academic_year_id: int) -> str:
    with session_scope() as session:
        year = session.get(AcademicYear, academic_year_id)
        if year is None:
            raise NotFoundError("Academic year not found")
        return repo.next_admission_number(session, year.label)


# ---------- commands ----------

def create_student(data: StudentCreate) -> StudentProfile:
    with session_scope() as session:
        year = session.get(AcademicYear, data.enrollment.academic_year_id)
        if year is None:
            raise NotFoundError("Academic year not found")
        admission_no = data.admission_no or repo.next_admission_number(session, year.label)
        _check_admission_no_free(session, admission_no)
        enrollment_data = data.enrollment
        _check_roll_no_free(session, year.id, enrollment_data.student_class, enrollment_data.section,
                            enrollment_data.roll_no)

        student = Student(
            admission_no=admission_no, name=data.name, date_of_birth=data.date_of_birth, category=data.category,
            date_of_join=data.date_of_join, class_joined=data.class_joined, notes=data.notes,
            status=StudentStatus.ACTIVE.value,
        )
        session.add(student)
        session.flush()
        if data.identifier:
            _save_identifier(session, student, data.identifier)

        enrollment = StudentEnrollment(student_id=student.id, academic_year_id=year.id,
                                       student_class=enrollment_data.student_class,
                                       section=enrollment_data.section, roll_no=enrollment_data.roll_no)
        session.add(enrollment)
        session.flush()

        if data.tuition_plan_id:
            fee_service.assign_in_session(session, enrollment, FeeType.TUITION.value,
                                          plan=_get_plan(session, data.tuition_plan_id))
        else:
            fee_service.assign_default_tuition(session, enrollment, data.category)
        if data.van_plan_id:
            fee_service.assign_in_session(session, enrollment, FeeType.VAN.value,
                                          plan=_get_plan(session, data.van_plan_id))

        for link in data.guardians:
            guardian_service.link_in_session(session, student.id, link)

        logger.info("Created student %s (%s)", student.id, admission_no)
        return _profile(session, student.id)


def enroll_existing_student(student_id: int, academic_year_id: int, student_class: str, section: str,
                            roll_no: Optional[int] = None) -> EnrollmentRead:
    """Enrolls a student in a year they are not yet enrolled in (e.g. re-admission)."""
    from data_management.dto.student import EnrollmentInput

    data = EnrollmentInput(academic_year_id=academic_year_id, student_class=student_class, section=section,
                           roll_no=roll_no)
    with session_scope() as session:
        student = _get_student(session, student_id)
        year = session.get(AcademicYear, academic_year_id)
        if year is None:
            raise NotFoundError("Academic year not found")
        if repo.enrollment_for(session, student_id, academic_year_id):
            raise BusinessRuleError(f"{student.name} is already enrolled in {year.label}")
        _check_roll_no_free(session, year.id, data.student_class, data.section, data.roll_no)
        enrollment = StudentEnrollment(student_id=student_id, academic_year_id=year.id,
                                       student_class=data.student_class, section=data.section, roll_no=data.roll_no)
        session.add(enrollment)
        session.flush()
        fee_service.assign_default_tuition(session, enrollment, student.category)
        return next(EnrollmentRead(**row) for row in repo.enrollments_of(session, student_id)
                    if row["enrollment_id"] == enrollment.id)


def update_student(student_id: int, data: StudentUpdate) -> StudentProfile:
    with session_scope() as session:
        student = _get_student(session, student_id)
        _check_admission_no_free(session, data.admission_no, student_id)
        for field, value in data.model_dump().items():
            setattr(student, field, value)
        session.add(student)
        session.flush()
        return _profile(session, student_id)


def update_identifier(student_id: int, data: IdentifierInput) -> None:
    with session_scope() as session:
        _save_identifier(session, _get_student(session, student_id), data)


def reveal_identifier(student_id: int, revealed_by: str) -> str:
    """Decrypts the full number. Callers must restrict this to administrators."""
    with session_scope() as session:
        student = _get_student(session, student_id)
        identifier = session.get(Identifier, student.identifier_id) if student.identifier_id else None
        if identifier is None or not identifier.ciphertext:
            raise BusinessRuleError("Only the last 4 digits are stored for this student")
        number = identifier_crypto.decrypt(identifier.ciphertext, identifier.nonce, student.id,
                                           identifier.identifier_type)
    logger.info("Identifier of student %s revealed by %s", student_id, revealed_by)
    return number


def update_enrollment(enrollment_id: int, data: EnrollmentUpdate) -> None:
    with session_scope() as session:
        enrollment = fee_service.get_enrollment(session, enrollment_id)
        _check_roll_no_free(session, enrollment.academic_year_id, enrollment.student_class, data.section,
                            data.roll_no, enrollment_id)
        enrollment.section = data.section
        enrollment.roll_no = data.roll_no
        session.add(enrollment)


def change_class(enrollment_id: int, new_class: str) -> None:
    """Corrects a wrong class. Allowed only while no tuition has been paid; the default plan is re-assigned."""
    from statics import CLASSES

    if new_class not in CLASSES:
        raise BusinessRuleError("Unknown class")
    with session_scope() as session:
        enrollment = fee_service.get_enrollment(session, enrollment_id)
        tuition = fee_repository.annual_due(session, enrollment_id, FeeType.TUITION.value)
        if tuition and fee_repository.has_allocations(session, tuition.id):
            raise BusinessRuleError("Tuition has already been paid this year; the class cannot be changed")
        if tuition:
            session.delete(tuition)
        enrollment.student_class = new_class
        enrollment.roll_no = None
        session.add(enrollment)
        session.flush()
        student = session.get(Student, enrollment.student_id)
        fee_service.assign_default_tuition(session, enrollment, student.category)


def mark_left(student_id: int, data: StudentLeaving) -> dict:
    """Marks a student as left / passed out. Annual fees stop at what has been paid so far."""
    with session_scope() as session:
        student = _get_student(session, student_id)
        student.status = data.status
        student.date_of_leaving = data.date_of_leaving
        session.add(student)
        result = {"removed": 0, "trimmed": 0}
        open_enrollments = session.exec(select(StudentEnrollment).where(
            StudentEnrollment.student_id == student_id, StudentEnrollment.outcome.is_(None))).all()
        reason = f"{data.status.replace('_', ' ').title()} on {data.date_of_leaving:%d %b %Y}"
        for enrollment in open_enrollments:
            enrollment.outcome = (EnrollmentOutcome.PASSED_OUT.value if data.status == StudentStatus.PASSED_OUT.value
                                  else EnrollmentOutcome.LEFT.value)
            session.add(enrollment)
            outcome = fee_service.stop_annual_fees(session, enrollment.id, reason)
            result = {key: result[key] + outcome[key] for key in result}
        return result


def reactivate(student_id: int) -> None:
    with session_scope() as session:
        student = _get_student(session, student_id)
        student.status = StudentStatus.ACTIVE.value
        student.date_of_leaving = None
        session.add(student)
        latest = session.exec(select(StudentEnrollment, AcademicYear)
                              .join(AcademicYear, AcademicYear.id == StudentEnrollment.academic_year_id)
                              .where(StudentEnrollment.student_id == student_id)
                              .order_by(AcademicYear.start_date.desc())).first()
        if latest and latest[0].outcome in (EnrollmentOutcome.LEFT.value, EnrollmentOutcome.PASSED_OUT.value):
            latest[0].outcome = None
            session.add(latest[0])


def delete_student(student_id: int) -> None:
    """Permanent removal, only for records created by mistake (no payments)."""
    with session_scope() as session:
        student = _get_student(session, student_id)
        if repo.has_payments(session, student_id):
            raise BusinessRuleError("This student has payments; mark them as left instead of deleting")
        enrollment_ids = [e.id for e in session.exec(
            select(StudentEnrollment).where(StudentEnrollment.student_id == student_id))]
        if enrollment_ids:
            session.execute(delete(StudentFeeDue).where(StudentFeeDue.enrollment_id.in_(enrollment_ids)))
            session.execute(delete(StudentEnrollment).where(StudentEnrollment.id.in_(enrollment_ids)))
        session.execute(delete(StudentGuardian).where(StudentGuardian.student_id == student_id))
        identifier_id = student.identifier_id
        session.delete(student)
        session.flush()
        if identifier_id:
            identifier = session.get(Identifier, identifier_id)
            if identifier:
                session.delete(identifier)
        logger.info("Deleted student %s", student_id)


def auto_assign_roll_numbers(academic_year_id: int, student_class: str, section: str,
                             only_missing: bool = True) -> int:
    """Alphabetical roll numbers. With only_missing, existing numbers are kept and new ones follow them."""
    with session_scope() as session:
        rows = session.exec(
            select(StudentEnrollment, Student).join(Student, Student.id == StudentEnrollment.student_id)
            .where(StudentEnrollment.academic_year_id == academic_year_id,
                   StudentEnrollment.student_class == student_class, StudentEnrollment.section == section,
                   Student.status == StudentStatus.ACTIVE.value)
            .order_by(Student.name)
        ).all()
        if not only_missing:
            for enrollment, _ in rows:
                enrollment.roll_no = None
                session.add(enrollment)
            session.flush()
        next_number = max([e.roll_no for e, _ in rows if e.roll_no] or [0]) + 1
        assigned = 0
        for enrollment, _ in rows:
            if enrollment.roll_no is None:
                enrollment.roll_no = next_number
                next_number += 1
                assigned += 1
                session.add(enrollment)
        return assigned
