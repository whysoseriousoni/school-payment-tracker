"""End-to-end business scenarios through the service layer (no UI)."""
from datetime import date

import pytest
from pydantic import ValidationError

from data_management.dto.academic_year import AcademicYearCreate
from data_management.dto.fee import FeeStructureInput, OneOffDueCreate, VanChange
from data_management.dto.guardian import GuardianCreate, GuardianLinkInput
from data_management.dto.payment import AllocationInput, PaymentCreate, VoidRequest
from data_management.dto.promotion import PromotionDecision, PromotionRequest
from data_management.dto.student import (
    EnrollmentInput,
    EnrollmentUpdate,
    IdentifierInput,
    StudentCreate,
    StudentLeaving,
    StudentSearch,
)
from data_management.dto.user import PasswordChange, UserCreate
from data_management.services import (
    academic_year_service,
    auth_service,
    fee_service,
    guardian_service,
    payment_service,
    promotion_service,
    student_service,
)
from data_management.services.errors import BusinessRuleError
from data_management.services.identifier_crypto import IdentifierKeyError
from helper.money import rupees_to_paise

AADHAAR_1 = "234123412346"
AADHAAR_2 = "499185602872"


def _year():
    return academic_year_service.get_current_year()


def _new_student(name="Asha Kumar", student_class="LKG", join=date(2026, 8, 5), aadhaar=None, guardians=None,
                 van=None, section="A"):
    year = _year()
    return student_service.create_student(StudentCreate(
        name=name, category="MANAGEMENT", date_of_join=join, class_joined=student_class,
        enrollment=EnrollmentInput(academic_year_id=year.id, student_class=student_class, section=section),
        identifier=IdentifierInput(full_number=aadhaar) if aadhaar else IdentifierInput(last_4_digits="1111"),
        guardians=guardians or [], van_monthly_paise=van,
    ))


def _pay(profile, allocations, method="CASH"):
    enrollment = profile.enrollments[0]
    return payment_service.create_payment(PaymentCreate(
        student_id=profile.student_id, enrollment_id=enrollment.enrollment_id, paid_on=date(2026, 9, 1),
        payment_method=method, billing_name="Parent", allocations=allocations), collected_by="tester")


@pytest.fixture
def lkg_fee(app_db):
    fee_service.save_structure(FeeStructureInput(academic_year_id=_year().id, student_class="LKG",
                                                 fee_type="TUITION", monthly_amount_paise=rupees_to_paise(2000)))


def test_fresh_install_creates_current_year(fresh_app_db):
    year = academic_year_service.ensure_current_year()
    assert year.label == "2026-27" and year.is_current
    assert academic_year_service.ensure_current_year().id == year.id


def test_mid_year_admission_gets_dues_from_joining_month(lkg_fee):
    profile = _new_student(van=rupees_to_paise(800))
    ledger = fee_service.get_ledger(profile.enrollments[0].enrollment_id)
    tuition = [d for d in ledger if d.fee_type == "TUITION"]
    van = [d for d in ledger if d.fee_type == "VAN"]
    assert len(tuition) == 10 and tuition[0].fee_month == date(2026, 8, 1) and tuition[-1].fee_month == date(2027, 5, 1)
    assert len(van) == 10 and van[0].amount_due_paise == 80000
    assert profile.admission_no == "ADM/2026-27/0001"
    assert _new_student(name="Second").admission_no == "ADM/2026-27/0002"


def test_aadhaar_is_encrypted_unique_and_bound_to_student(lkg_fee, app_db, connect):
    first = _new_student(aadhaar=AADHAAR_1)
    assert first.identifier_last_4 == "2346" and first.has_full_identifier
    row = connect(app_db).execute("SELECT * FROM identifier WHERE last_4_digits = '2346'").fetchone()
    assert AADHAAR_1 not in (row["ciphertext"] + row["nonce"] + row["fingerprint"])
    assert student_service.reveal_identifier(first.student_id, "admin") == AADHAAR_1

    with pytest.raises(BusinessRuleError, match="already registered to Asha Kumar"):
        _new_student(name="Copycat", aadhaar=AADHAAR_1)

    second = _new_student(name="Other", aadhaar=AADHAAR_2)
    conn = connect(app_db)
    conn.execute("UPDATE identifier SET ciphertext = ?, nonce = ? WHERE last_4_digits = '2872'",
                 (row["ciphertext"], row["nonce"]))
    conn.commit()
    with pytest.raises(IdentifierKeyError):
        student_service.reveal_identifier(second.student_id, "admin")


def test_siblings_share_a_guardian(lkg_fee):
    mother = guardian_service.create_guardian(GuardianCreate(name="Meena", mobile_number="9876543210"))
    older = _new_student(name="Older", guardians=[GuardianLinkInput(guardian_id=mother.id, relation_type="MOTHER")])
    younger = _new_student(name="Younger", guardians=[
        GuardianLinkInput(guardian_id=mother.id, relation_type="MOTHER"),
        GuardianLinkInput(new_guardian=GuardianCreate(name="Raj"), relation_type="FATHER", is_primary=True)])
    assert older.primary_guardian.name == "Meena"
    assert younger.primary_guardian.name == "Raj"
    listed = {g.name: g for g in guardian_service.list_guardians("Meena")}
    assert sorted(listed["Meena"].students) == ["Older (MOTHER)", "Younger (MOTHER)"]

    raj_link = next(g for g in younger.guardians if g.name == "Raj")
    guardian_service.unlink(raj_link.link_id)
    assert student_service.get_profile(younger.student_id).primary_guardian.name == "Meena"
    found = student_service.search_students(StudentSearch(text="9876543210", academic_year_id=_year().id))
    assert {r.name for r in found} == {"Older", "Younger"}


def test_payment_allocation_receipts_and_void(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1))
    enrollment_id = profile.enrollments[0].enrollment_id
    ledger = fee_service.get_ledger(enrollment_id)
    allocations = payment_service.suggest_allocation(ledger, rupees_to_paise(5000))
    assert [a.amount_paise for a in allocations] == [200000, 200000, 100000]

    receipt = _pay(profile, allocations, method="UPI")
    assert receipt.receipt_no == "RCPT/2026-27/00004"  # continues after the 3 migrated receipts
    assert receipt.amount_in_words == "Five Thousand Rupees Only"
    assert [a.label for a in receipt.allocations] == ["Tuition Fee - Jun 2026", "Tuition Fee - Jul 2026",
                                                      "Tuition Fee - Aug 2026"]
    august = next(d for d in fee_service.get_ledger(enrollment_id) if d.fee_month == date(2026, 8, 1))
    assert august.status == "Part paid" and august.balance_paise == 100000

    with pytest.raises(BusinessRuleError, match="only .*1,000.00 is pending"):
        _pay(profile, [AllocationInput(fee_due_id=august.fee_due_id, amount_paise=100001)])

    payment_service.void_payment(VoidRequest(payment_id=receipt.id, reason="Wrong student"), "admin")
    assert sum(d.balance_paise for d in fee_service.get_ledger(enrollment_id)) == 12 * 200000
    with pytest.raises(BusinessRuleError, match="already void"):
        payment_service.void_payment(VoidRequest(payment_id=receipt.id, reason="again"), "admin")
    assert _pay(profile, allocations).receipt_no == "RCPT/2026-27/00005"
    assert payment_service.find_by_receipt_no("rcpt/2026-27/00005").student_id == profile.student_id


def test_payment_validation(lkg_fee):
    profile = _new_student()
    other = _new_student(name="Other")
    other_due = fee_service.get_ledger(other.enrollments[0].enrollment_id)[0]
    with pytest.raises(BusinessRuleError, match="does not belong"):
        _pay(profile, [AllocationInput(fee_due_id=other_due.fee_due_id, amount_paise=100)])
    with pytest.raises(ValidationError):
        PaymentCreate(student_id=1, enrollment_id=1, paid_on=date(2099, 1, 1), payment_method="CASH",
                      billing_name="x", allocations=[AllocationInput(fee_due_id=1, amount_paise=1)])


def test_one_off_fees_and_van_changes(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1))
    enrollment_id = profile.enrollments[0].enrollment_id
    books = fee_service.add_one_off_due(OneOffDueCreate(enrollment_id=enrollment_id, fee_type="BOOK",
                                                        description="Text books", amount_paise=150000))
    assert books.label == "Book Fee - Text books"

    created = fee_service.start_van(VanChange(enrollment_id=enrollment_id, from_month=date(2026, 9, 15),
                                              monthly_amount_paise=70000))
    assert created == 9  # Sep..May
    van = [d for d in fee_service.get_ledger(enrollment_id) if d.fee_type == "VAN"]
    _pay(profile, [AllocationInput(fee_due_id=van[0].fee_due_id, amount_paise=70000),
                   AllocationInput(fee_due_id=van[1].fee_due_id, amount_paise=30000)])
    result = fee_service.stop_van(enrollment_id, date(2026, 10, 1))
    assert result == {"removed": 7, "trimmed": 1}
    van = [d for d in fee_service.get_ledger(enrollment_id) if d.fee_type == "VAN"]
    assert [(d.fee_month.month, d.amount_due_paise, d.balance_paise) for d in van] == [(9, 70000, 0), (10, 30000, 0)]

    with pytest.raises(BusinessRuleError, match="inside the enrollment"):
        fee_service.start_van(VanChange(enrollment_id=enrollment_id, from_month=date(2027, 7, 1),
                                        monthly_amount_paise=1))
    fee_service.remove_due(books.fee_due_id)


def test_student_leaving_stops_future_fees(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1))
    enrollment_id = profile.enrollments[0].enrollment_id
    november = next(d for d in fee_service.get_ledger(enrollment_id) if d.fee_month == date(2026, 11, 1))
    _pay(profile, [AllocationInput(fee_due_id=november.fee_due_id, amount_paise=50000)])
    result = student_service.mark_left(profile.student_id, StudentLeaving(status="LEFT", date_of_leaving=date(2026, 10, 2)))
    assert result == {"removed": 6, "trimmed": 1}  # Dec..May removed, Nov reduced to the Rs 500 paid
    after = student_service.get_profile(profile.student_id)
    assert after.status == "LEFT" and after.enrollments[0].outcome == "LEFT"
    student_service.reactivate(profile.student_id)
    assert student_service.get_profile(profile.student_id).status == "ACTIVE"


def test_delete_only_without_payments(lkg_fee):
    keep = _new_student(join=date(2026, 6, 1))
    _pay(keep, payment_service.suggest_allocation(fee_service.get_ledger(keep.enrollments[0].enrollment_id), 100))
    with pytest.raises(BusinessRuleError, match="mark them as left"):
        student_service.delete_student(keep.student_id)
    mistake = _new_student(name="Typo", aadhaar=AADHAAR_1)
    student_service.delete_student(mistake.student_id)
    _new_student(name="Typo fixed", aadhaar=AADHAAR_1)  # Aadhaar free again


def test_roll_numbers_and_sections(app_db):
    year = _year()
    students = student_service.search_students(StudentSearch(academic_year_id=year.id, student_class="UKG"))
    assert student_service.auto_assign_roll_numbers(year.id, "UKG", "A") == len(students) == 3
    rolls = {r.name: r.roll_no for r in student_service.search_students(
        StudentSearch(academic_year_id=year.id, student_class="UKG"))}
    assert rolls == {"Student Test": 1, "UNNAMED STUDENT #3": 2, "VBN": 3}
    target = next(r for r in students if r.name == "VBN")
    with pytest.raises(BusinessRuleError, match="already taken"):
        student_service.update_enrollment(target.enrollment_id, EnrollmentUpdate(section="A", roll_no=1))
    student_service.update_enrollment(target.enrollment_id, EnrollmentUpdate(section="B", roll_no=1))


def test_apply_structure_and_class_change(app_db):
    year = _year()
    fee_service.save_structure(FeeStructureInput(academic_year_id=year.id, student_class="UKG", fee_type="TUITION",
                                                 monthly_amount_paise=150000))
    result = fee_service.apply_tuition_structure(year.id)
    # Student 3 has no joining date (12 months); students 5 and 6 joined in July (11 months each).
    assert result["created"] == 12 + 11 + 11
    fee_service.save_structure(FeeStructureInput(academic_year_id=year.id, student_class="UKG", fee_type="TUITION",
                                                 monthly_amount_paise=160000))
    assert fee_service.apply_tuition_structure(year.id, "UKG", update_unpaid=True)["updated"] == result["created"]
    with pytest.raises(BusinessRuleError, match="already been paid"):
        student_service.change_class(student_service.get_profile(1).enrollments[0].enrollment_id, "3")


def test_promotion_to_next_year(app_db):
    current = _year()
    next_year = academic_year_service.create_year(AcademicYearCreate(start_year=2027))
    fee_service.save_structure(FeeStructureInput(academic_year_id=next_year.id, student_class="1", fee_type="TUITION",
                                                 monthly_amount_paise=250000))
    ukg = promotion_service.candidates(current.id, "UKG")
    decisions = [PromotionDecision(enrollment_id=c.enrollment_id, outcome=outcome, target_section="B")
                 for c, outcome in zip(ukg, ["PROMOTED", "RETAINED", "LEFT"])]
    result = promotion_service.promote(PromotionRequest(from_year_id=current.id, to_year_id=next_year.id,
                                                        decisions=decisions))
    assert (result.promoted, result.retained, result.left) == (1, 1, 1)
    promoted = student_service.get_profile(ukg[0].student_id)
    new_enrollment = promoted.enrollment_for(next_year.id)
    assert (new_enrollment.student_class, new_enrollment.section) == ("1", "B")
    assert len(fee_service.get_ledger(new_enrollment.enrollment_id)) == 12
    assert promotion_service.candidates(current.id, "UKG") == []
    with pytest.raises(BusinessRuleError, match="later academic year"):
        promotion_service.promote(PromotionRequest(from_year_id=next_year.id, to_year_id=current.id, decisions=[
            PromotionDecision(enrollment_id=new_enrollment.enrollment_id, outcome="PROMOTED", target_section="A")]))


def test_class_ten_passes_out(lkg_fee):
    year = _year()
    next_year = academic_year_service.create_year(AcademicYearCreate(start_year=2027))
    senior = _new_student(name="Senior", student_class="10")
    candidate = promotion_service.candidates(year.id, "10")[0]
    assert candidate.next_class is None
    result = promotion_service.promote(PromotionRequest(from_year_id=year.id, to_year_id=next_year.id, decisions=[
        PromotionDecision(enrollment_id=candidate.enrollment_id, outcome="PROMOTED", target_section="A")]))
    assert result.passed_out == 1
    assert student_service.get_profile(senior.student_id).status == "PASSED_OUT"


def test_users_and_login(fresh_app_db):
    assert auth_service.needs_first_admin()
    with pytest.raises(BusinessRuleError):
        auth_service.create_first_admin(UserCreate(username="clerk", password="abcd1234", role="BILLER"))
    admin = auth_service.create_first_admin(UserCreate(username="Admin", password="abcd1234", role="ADMIN"))
    assert admin.username == "admin" and not auth_service.needs_first_admin()
    assert auth_service.authenticate("ADMIN", "abcd1234").is_admin
    assert auth_service.authenticate("admin", "wrong") is None
    assert auth_service.authenticate("nobody", "abcd1234") is None
    with pytest.raises(BusinessRuleError, match="own account"):
        auth_service.set_active(admin.id, False, acting_user_id=admin.id)
    biller = auth_service.create_user(UserCreate(username="billing", password="bill1234", role="BILLER"))
    with pytest.raises(BusinessRuleError, match="active administrator"):
        auth_service.set_active(admin.id, False, acting_user_id=biller.id)
    auth_service.change_password(PasswordChange(user_id=biller.id, new_password="newpass99"))
    assert auth_service.authenticate("billing", "newpass99").role == "BILLER"
    auth_service.set_active(biller.id, False, acting_user_id=admin.id)
    assert auth_service.authenticate("billing", "newpass99") is None
    with pytest.raises(ValidationError):
        UserCreate(username="x y", password="short", role="ADMIN")
