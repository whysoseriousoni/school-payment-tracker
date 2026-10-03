"""Year-end promotion: closes this year's enrollments and opens next year's."""
from typing import List, Optional

from sqlmodel import select

from data_management.dao import AcademicYear, Student, StudentEnrollment
from data_management.dto.promotion import PromotionCandidate, PromotionRequest, PromotionResult
from data_management.repositories import student_repository
from data_management.services import fee_service
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from helper.logger import get_logger
from helper.school_calendar import next_class
from statics import EnrollmentOutcome, StudentStatus

logger = get_logger(__name__)


def candidates(from_year_id: int, student_class: str, section: Optional[str] = None) -> List[PromotionCandidate]:
    """Active students of a class whose year has not been closed yet."""
    with session_scope() as session:
        query = (
            select(StudentEnrollment, Student).join(Student, Student.id == StudentEnrollment.student_id)
            .where(StudentEnrollment.academic_year_id == from_year_id,
                   StudentEnrollment.student_class == student_class,
                   StudentEnrollment.outcome.is_(None), Student.status == StudentStatus.ACTIVE.value)
            .order_by(StudentEnrollment.section, StudentEnrollment.roll_no, Student.name)
        )
        if section:
            query = query.where(StudentEnrollment.section == section)
        return [
            PromotionCandidate(enrollment_id=e.id, student_id=s.id, admission_no=s.admission_no, name=s.name,
                               student_class=e.student_class, section=e.section, roll_no=e.roll_no,
                               next_class=next_class(e.student_class))
            for e, s in session.exec(query).all()
        ]


def promote(request: PromotionRequest) -> PromotionResult:
    result = PromotionResult()
    with session_scope() as session:
        from_year = session.get(AcademicYear, request.from_year_id)
        to_year = session.get(AcademicYear, request.to_year_id)
        if from_year is None or to_year is None:
            raise NotFoundError("Academic year not found")
        if to_year.start_date <= from_year.start_date:
            raise BusinessRuleError("Students can only be promoted into a later academic year")

        for decision in request.decisions:
            enrollment = session.get(StudentEnrollment, decision.enrollment_id)
            if enrollment is None or enrollment.academic_year_id != from_year.id:
                raise BusinessRuleError("A selected student is not enrolled in the source year")
            if enrollment.outcome is not None:
                raise BusinessRuleError("A selected student's year has already been closed")
            student = session.get(Student, enrollment.student_id)
            if student_repository.enrollment_for(session, student.id, to_year.id):
                raise BusinessRuleError(f"{student.name} is already enrolled in {to_year.label}")

            target_class = enrollment.student_class
            if decision.outcome == EnrollmentOutcome.LEFT.value:
                enrollment.outcome = EnrollmentOutcome.LEFT.value
                student.status = StudentStatus.LEFT.value
                student.date_of_leaving = from_year.end_date
                result.left += 1
            elif decision.outcome == EnrollmentOutcome.PROMOTED.value and next_class(target_class) is None:
                enrollment.outcome = EnrollmentOutcome.PASSED_OUT.value
                student.status = StudentStatus.PASSED_OUT.value
                student.date_of_leaving = from_year.end_date
                result.passed_out += 1
            else:
                if decision.outcome == EnrollmentOutcome.PROMOTED.value:
                    target_class = next_class(target_class)
                    result.promoted += 1
                else:
                    result.retained += 1
                enrollment.outcome = decision.outcome
                new_enrollment = StudentEnrollment(student_id=student.id, academic_year_id=to_year.id,
                                                   student_class=target_class, section=decision.target_section)
                session.add(new_enrollment)
                session.flush()
                fee_service.generate_tuition_from_structure(session, new_enrollment)
            session.add(enrollment)
            session.add(student)
        session.flush()
    logger.info("Promotion %s -> %s: %s", request.from_year_id, request.to_year_id, result.model_dump())
    return result
