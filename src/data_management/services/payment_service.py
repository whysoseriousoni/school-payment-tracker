"""Receipts: creating, allocating, voiding and reading payments."""
from datetime import date
from typing import Iterable, List, Optional

from data_management.dao import AcademicYear, Payment, PaymentAllocation, StudentFeeDue
from data_management.dto.fee import FeeDueRead, due_label
from data_management.dto.payment import AllocationInput, AllocationRead, PaymentCreate, PaymentRead, VoidRequest
from data_management.repositories import fee_repository
from data_management.repositories import payment_repository as repo
from data_management.services import fee_service
from data_management.services.errors import BusinessRuleError, NotFoundError
from data_management.sql_manager import session_scope
from config.settings import RECEIPT_PREFIX
from helper.clock import now_ist
from helper.logger import get_logger
from helper.money import amount_in_words_inr, format_inr

logger = get_logger(__name__)


def suggest_allocation(open_dues: Iterable[FeeDueRead], amount_paise: int,
                       fee_types: Optional[Iterable[str]] = None) -> List[AllocationInput]:
    """Spreads `amount_paise` over pending dues in ledger order (tuition, van, then other fees)."""
    wanted = set(fee_types) if fee_types else None
    remaining = amount_paise
    allocations = []
    for due in open_dues:
        if remaining <= 0:
            break
        if due.balance_paise <= 0 or (wanted and due.fee_type not in wanted):
            continue
        portion = min(due.balance_paise, remaining)
        allocations.append(AllocationInput(fee_due_id=due.fee_due_id, amount_paise=portion))
        remaining -= portion
    return allocations


def _to_read(row: dict, allocation_rows: List[dict]) -> PaymentRead:
    allocations = [
        AllocationRead(
            fee_due_id=a["fee_due_id"], amount_paise=a["amount_paise"],
            label=due_label(a["fee_type"], a["description"], a["plan_code"]),
        )
        for a in allocation_rows if a["payment_id"] == row["id"]
    ]
    return PaymentRead(**row, allocations=allocations)


def _read_many(session, rows: List[dict]) -> List[PaymentRead]:
    allocation_rows = repo.allocations_for(session, [row["id"] for row in rows])
    return [_to_read(row, allocation_rows) for row in rows]


def create_payment(data: PaymentCreate, collected_by: str) -> PaymentRead:
    with session_scope() as session:
        enrollment = fee_service.get_enrollment(session, data.enrollment_id)
        if enrollment.student_id != data.student_id:
            raise BusinessRuleError("The selected class/year does not belong to this student")

        for allocation in data.allocations:
            due = session.get(StudentFeeDue, allocation.fee_due_id)
            if due is None or due.enrollment_id != enrollment.id:
                raise BusinessRuleError("A selected fee does not belong to this student's year")
            balance = due.amount_due_paise - fee_repository.paid_amount(session, due.id)
            if allocation.amount_paise > balance:
                raise BusinessRuleError(
                    f"{due_label(due.fee_type, due.description)}: only {format_inr(balance)} is pending"
                )

        year = session.get(AcademicYear, enrollment.academic_year_id)
        number = repo.next_receipt_number(session, year.id)
        payment = Payment(
            receipt_no=f"{RECEIPT_PREFIX}/{year.label}/{number:05d}",
            student_id=data.student_id, enrollment_id=enrollment.id, paid_on=data.paid_on,
            amount_paise=data.amount_paise, payment_method=data.payment_method,
            payment_notes=data.payment_notes, billing_name=data.billing_name, notes=data.notes,
            amount_in_words=amount_in_words_inr(data.amount_paise), collected_by=collected_by,
        )
        session.add(payment)
        session.flush()
        for allocation in data.allocations:
            session.add(PaymentAllocation(payment_id=payment.id, fee_due_id=allocation.fee_due_id,
                                          amount_paise=allocation.amount_paise))
        session.flush()
        logger.info("Receipt %s: %s for student %s by %s", payment.receipt_no, format_inr(payment.amount_paise),
                    data.student_id, collected_by)
        return _read_many(session, repo.find(session, payment_id=payment.id))[0]


def void_payment(request: VoidRequest, voided_by: str) -> PaymentRead:
    with session_scope() as session:
        payment = session.get(Payment, request.payment_id)
        if payment is None:
            raise NotFoundError("Receipt not found")
        if payment.is_voided:
            raise BusinessRuleError(f"Receipt {payment.receipt_no} is already void")
        payment.is_voided = True
        payment.void_reason = request.reason
        payment.voided_on = now_ist()
        payment.voided_by = voided_by
        session.add(payment)
        session.flush()
        logger.info("Receipt %s voided by %s: %s", payment.receipt_no, voided_by, request.reason)
        return _read_many(session, repo.find(session, payment_id=payment.id))[0]


def get_payment(payment_id: int) -> PaymentRead:
    with session_scope() as session:
        rows = repo.find(session, payment_id=payment_id)
        if not rows:
            raise NotFoundError("Receipt not found")
        return _read_many(session, rows)[0]


def find_by_receipt_no(receipt_no: str) -> Optional[PaymentRead]:
    with session_scope() as session:
        rows = repo.find(session, receipt_no=(receipt_no or "").strip())
        return _read_many(session, rows)[0] if rows else None


def list_payments(student_id: Optional[int] = None, enrollment_id: Optional[int] = None,
                  date_from: Optional[date] = None, date_to: Optional[date] = None,
                  limit: int = 1000) -> List[PaymentRead]:
    with session_scope() as session:
        rows = repo.find(session, student_id=student_id, enrollment_id=enrollment_id,
                         date_from=date_from, date_to=date_to, limit=limit)
        return _read_many(session, rows)
