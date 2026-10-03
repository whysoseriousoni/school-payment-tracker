"""End-to-end business scenarios through the service layer (no UI)."""
from datetime import date

import pytest
from pydantic import ValidationError

from data_management.dto.academic_year import AcademicYearCreate
from data_management.dto.fee import FeeAssignment, FeePlanInput, MilestoneInput, MilestoneSet, OneOffDueCreate
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
                 van_plan=None, section="A", category="MANAGEMENT", tuition_plan=None):
    year = _year()
    return student_service.create_student(StudentCreate(
        name=name, category=category, date_of_join=join, class_joined=student_class,
        enrollment=EnrollmentInput(academic_year_id=year.id, student_class=student_class, section=section),
        identifier=IdentifierInput(full_number=aadhaar) if aadhaar else IdentifierInput(last_4_digits="1111"),
        guardians=guardians or [], van_plan_id=van_plan, tuition_plan_id=tuition_plan,
    ))


def _pay(profile, allocations, method="CASH"):
    enrollment = profile.enrollments[0]
    return payment_service.create_payment(PaymentCreate(
        student_id=profile.student_id, enrollment_id=enrollment.enrollment_id, paid_on=date(2026, 9, 1),
        payment_method=method, billing_name="Parent", allocations=allocations), collected_by="tester")


def _plan(code, fee_type="TUITION", student_class="LKG", category=None, rupees=24000, default=False, year=None):
    return fee_service.save_plan(FeePlanInput(
        academic_year_id=(year or _year()).id, code=code, fee_type=fee_type, student_class=student_class,
        category=category, annual_amount_paise=rupees_to_paise(rupees), is_default=default)).plan


@pytest.fixture
def lkg_fee(app_db):
    """LKG-FEE-1 Rs 24,000 (default), LKG-FEE-2 Rs 20,000, LKG-DG1-1 Rs 12,000 (default for DG 1), VAN-1 Rs 8,000."""
    return {
        "standard": _plan("LKG-FEE-1", default=True),
        "concession": _plan("LKG-FEE-2", rupees=20000),
        "dg1": _plan("LKG-DG1-1", category="DG 1", rupees=12000, default=True),
        "van": _plan("VAN-1", fee_type="VAN", student_class=None, rupees=8000, default=True),
    }


def test_fresh_install_creates_current_year(fresh_app_db):
    year = academic_year_service.ensure_current_year()
    assert year.label == "2026-27" and year.is_current
    assert academic_year_service.ensure_current_year().id == year.id


def test_admission_gets_default_plan_for_class_and_category(lkg_fee):
    standard = _new_student(van_plan=lkg_fee["van"].id)
    ledger = fee_service.get_ledger(standard.enrollments[0].enrollment_id)
    assert [(d.label, d.amount_due_paise) for d in ledger] == [
        ("Tuition Fee (LKG-FEE-1)", 2400000), ("Van Fee (VAN-1)", 800000)]
    dg = _new_student(name="Quota Kid", category="DG 1")
    assert fee_service.get_ledger(dg.enrollments[0].enrollment_id)[0].plan_code == "LKG-DG1-1"
    chosen = _new_student(name="Sibling", tuition_plan=lkg_fee["concession"].id)
    assert fee_service.get_ledger(chosen.enrollments[0].enrollment_id)[0].amount_due_paise == 2000000
    no_plan = _new_student(name="Grade Three", student_class="3")
    assert fee_service.get_ledger(no_plan.enrollments[0].enrollment_id) == []
    assert standard.admission_no == "ADM/2026-27/0001"


def test_plan_rules_and_amount_changes(lkg_fee):
    with pytest.raises(BusinessRuleError, match="already exists"):
        _plan("lkg-fee-1")
    with pytest.raises(ValidationError, match="needs a class"):
        FeePlanInput(academic_year_id=1, code="X-1", fee_type="TUITION", annual_amount_paise=1)
    with pytest.raises(ValidationError, match="letters, numbers"):
        FeePlanInput(academic_year_id=1, code="UKG FEE", fee_type="VAN", annual_amount_paise=1)

    first, second = _new_student(), _new_student(name="Second")
    _pay(first, [AllocationInput(fee_due_id=fee_service.get_ledger(first.enrollments[0].enrollment_id)[0].fee_due_id,
                                 amount_paise=2300000)])
    result = fee_service.save_plan(FeePlanInput(academic_year_id=_year().id, code="LKG-FEE-1", fee_type="TUITION",
                                                student_class="LKG", annual_amount_paise=2200000, is_default=True),
                                   plan_id=lkg_fee["standard"].id)
    assert result.dues_updated == 1 and result.dues_skipped == ["Asha Kumar"]  # already paid Rs 23,000
    assert fee_service.get_ledger(second.enrollments[0].enrollment_id)[0].amount_due_paise == 2200000

    new_default = fee_service.save_plan(FeePlanInput(academic_year_id=_year().id, code="LKG-FEE-2",
                                                     fee_type="TUITION", student_class="LKG",
                                                     annual_amount_paise=2000000, is_default=True),
                                        plan_id=lkg_fee["concession"].id)
    plans = {p.code: p for p in fee_service.list_plans(_year().id)}
    assert plans["LKG-FEE-2"].is_default and not plans["LKG-FEE-1"].is_default
    assert plans["LKG-FEE-1"].students_assigned == 2 and new_default.plan.students_assigned == 0
    with pytest.raises(BusinessRuleError, match="assigned to students"):
        fee_service.delete_plan(lkg_fee["standard"].id)
    fee_service.delete_plan(lkg_fee["dg1"].id)


def test_assignment_plan_or_custom_amount(lkg_fee):
    student = _new_student()
    enrollment_id = student.enrollments[0].enrollment_id
    due = fee_service.assign(FeeAssignment(enrollment_id=enrollment_id, fee_type="TUITION",
                                           fee_plan_id=lkg_fee["concession"].id))
    assert (due.plan_code, due.amount_due_paise) == ("LKG-FEE-2", 2000000)
    custom = fee_service.assign(FeeAssignment(enrollment_id=enrollment_id, fee_type="TUITION",
                                              custom_amount_paise=1500000, reason="Staff child"))
    assert custom.label == "Tuition Fee (custom)" and custom.override_reason == "Staff child"
    assert custom.fee_due_id == due.fee_due_id  # still one tuition fee per term
    with pytest.raises(ValidationError, match="reason"):
        FeeAssignment(enrollment_id=enrollment_id, fee_type="TUITION", custom_amount_paise=1)
    with pytest.raises(ValidationError, match="not both"):
        FeeAssignment(enrollment_id=enrollment_id, fee_type="TUITION", fee_plan_id=1, custom_amount_paise=1,
                      reason="x")
    with pytest.raises(BusinessRuleError, match="not a Van Fee plan"):
        fee_service.assign(FeeAssignment(enrollment_id=enrollment_id, fee_type="VAN",
                                         fee_plan_id=lkg_fee["standard"].id))
    _pay(student, [AllocationInput(fee_due_id=custom.fee_due_id, amount_paise=1000000)])
    with pytest.raises(BusinessRuleError, match="cannot be lower"):
        fee_service.assign(FeeAssignment(enrollment_id=enrollment_id, fee_type="TUITION", custom_amount_paise=500000,
                                         reason="x"))


def test_assign_defaults_reports_students_without_a_plan(app_db):
    year = _year()
    _plan("UKG-FEE-1", student_class="UKG", rupees=10000, default=True)
    _plan("UKG-DG1-1", student_class="UKG", category="DG 1", rupees=5000, default=True)
    result = fee_service.assign_defaults(year.id)
    assert result["assigned"] == 3
    assert result["missing"] == ["UNNAMED STUDENT #2 (3, no category)", "PEEDARP (4, MANAGEMENT)"]
    rows = {r.name: r for r in fee_service.assignment_rows(year.id, student_class="UKG")}
    assert rows["VBN"].tuition_plan == "UKG-DG1-1" and rows["Student Test"].tuition_paise == 1000000
    assert fee_service.assign_defaults(year.id)["assigned"] == 0  # idempotent


def test_milestones_and_payment_status(lkg_fee):
    year = _year()
    with pytest.raises(ValidationError, match="increase"):
        MilestoneSet(academic_year_id=year.id, milestones=[MilestoneInput(due_date=date(2026, 10, 31), cumulative_percent=60),
                                                           MilestoneInput(due_date=date(2027, 1, 31), cumulative_percent=50)])
    with pytest.raises(BusinessRuleError, match="outside term"):
        fee_service.save_milestones(MilestoneSet(academic_year_id=year.id, milestones=[
            MilestoneInput(due_date=date(2027, 7, 1), cumulative_percent=100)]))
    fee_service.save_milestones(MilestoneSet(academic_year_id=year.id, milestones=[
        MilestoneInput(due_date=date(2027, 3, 31), cumulative_percent=100),
        MilestoneInput(due_date=date(2026, 10, 31), cumulative_percent=50)]))
    assert [m.cumulative_percent for m in fee_service.get_milestones(year.id)] == [50, 100]

    student = _new_student(van_plan=lkg_fee["van"].id)  # Rs 24,000 tuition + Rs 8,000 van
    enrollment_id = student.enrollments[0].enrollment_id
    _pay(student, payment_service.suggest_allocation(fee_service.get_ledger(enrollment_id), 1000000))
    before = fee_service.payment_status(enrollment_id, date(2026, 10, 30))
    assert (before["expected_percent"], before["overdue_paise"]) == (0, 0)
    after = fee_service.payment_status(enrollment_id, date(2026, 11, 1))
    # 50% of Rs 24,000 tuition + 50% of Rs 8,000 van = Rs 16,000 expected; Rs 10,000 paid -> Rs 6,000 overdue
    assert after["expected_paise"] == 1600000 and after["overdue_paise"] == 600000
    assert after["next_milestone"] == (date(2027, 3, 31), 100) and after["receipts"] == 1


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


def test_flexible_payments_receipts_and_void(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1))
    enrollment_id = profile.enrollments[0].enrollment_id
    tuition = fee_service.get_ledger(enrollment_id)[0]
    receipt = _pay(profile, [AllocationInput(fee_due_id=tuition.fee_due_id, amount_paise=rupees_to_paise(5000))],
                   method="UPI")
    assert receipt.receipt_no == "RCPT/2026-27/00004"  # continues after the 3 migrated receipts
    assert receipt.amount_in_words == "Five Thousand Rupees Only"
    assert [a.label for a in receipt.allocations] == ["Tuition Fee (LKG-FEE-1)"]
    after = fee_service.get_ledger(enrollment_id)[0]
    assert after.status == "Part paid" and after.balance_paise == 1900000

    with pytest.raises(BusinessRuleError, match="only .*19,000.00 is pending"):
        _pay(profile, [AllocationInput(fee_due_id=tuition.fee_due_id, amount_paise=1900001)])

    payment_service.void_payment(VoidRequest(payment_id=receipt.id, reason="Wrong student"), "admin")
    assert fee_service.get_ledger(enrollment_id)[0].balance_paise == 2400000
    with pytest.raises(BusinessRuleError, match="already void"):
        payment_service.void_payment(VoidRequest(payment_id=receipt.id, reason="again"), "admin")
    for _ in range(13):  # any number of instalments is allowed (the UI warns after 12)
        _pay(profile, [AllocationInput(fee_due_id=tuition.fee_due_id, amount_paise=100000)])
    assert fee_service.receipt_count(enrollment_id) == 13
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


def test_one_off_fees_and_van(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1))
    enrollment_id = profile.enrollments[0].enrollment_id
    books = fee_service.add_one_off_due(OneOffDueCreate(enrollment_id=enrollment_id, fee_type="BOOK",
                                                        description="Text books", amount_paise=150000))
    assert books.label == "Book Fee - Text books"
    with pytest.raises(ValidationError, match="Describe"):
        OneOffDueCreate(enrollment_id=enrollment_id, fee_type="CUSTOM", amount_paise=1)

    van = fee_service.assign(FeeAssignment(enrollment_id=enrollment_id, fee_type="VAN", fee_plan_id=lkg_fee["van"].id))
    _pay(profile, [AllocationInput(fee_due_id=van.fee_due_id, amount_paise=300000)])
    assert fee_service.remove_van(enrollment_id) == {"removed": 0, "trimmed": 1}
    van = next(d for d in fee_service.get_ledger(enrollment_id) if d.fee_type == "VAN")
    assert (van.amount_due_paise, van.balance_paise) == (300000, 0) and van.override_reason.startswith("Van stopped")

    other = _new_student(name="No payments", van_plan=lkg_fee["van"].id)
    assert fee_service.remove_van(other.enrollments[0].enrollment_id) == {"removed": 1, "trimmed": 0}
    fee_service.remove_due(books.fee_due_id)


def test_student_leaving_stops_annual_fees(lkg_fee):
    profile = _new_student(join=date(2026, 6, 1), van_plan=lkg_fee["van"].id)
    enrollment_id = profile.enrollments[0].enrollment_id
    tuition = fee_service.get_ledger(enrollment_id)[0]
    _pay(profile, [AllocationInput(fee_due_id=tuition.fee_due_id, amount_paise=800000)])
    result = student_service.mark_left(profile.student_id, StudentLeaving(status="LEFT", date_of_leaving=date(2026, 10, 2)))
    assert result == {"removed": 1, "trimmed": 1}  # unpaid van removed, tuition reduced to the Rs 8,000 paid
    ledger = fee_service.get_ledger(enrollment_id)
    assert [(d.fee_type, d.amount_due_paise, d.balance_paise) for d in ledger] == [("TUITION", 800000, 0)]
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


def test_class_change_reassigns_default_plan(lkg_fee):
    _plan("UKG-FEE-1", student_class="UKG", rupees=10000, default=True)
    profile = _new_student()
    enrollment_id = profile.enrollments[0].enrollment_id
    student_service.change_class(enrollment_id, "UKG")
    assert fee_service.get_ledger(enrollment_id)[0].plan_code == "UKG-FEE-1"
    with pytest.raises(BusinessRuleError, match="already been paid"):
        student_service.change_class(student_service.get_profile(1).enrollments[0].enrollment_id, "3")


def test_promotion_to_next_year(app_db):
    current = _year()
    next_year = academic_year_service.create_year(AcademicYearCreate(start_year=2027))
    _plan("1-FEE-1", student_class="1", rupees=30000, default=True, year=next_year)
    ukg = promotion_service.candidates(current.id, "UKG")
    decisions = [PromotionDecision(enrollment_id=c.enrollment_id, outcome=outcome, target_section="B")
                 for c, outcome in zip(ukg, ["PROMOTED", "RETAINED", "LEFT"])]
    result = promotion_service.promote(PromotionRequest(from_year_id=current.id, to_year_id=next_year.id,
                                                        decisions=decisions))
    assert (result.promoted, result.retained, result.left) == (1, 1, 1)
    promoted = student_service.get_profile(ukg[0].student_id)
    new_enrollment = promoted.enrollment_for(next_year.id)
    assert (new_enrollment.student_class, new_enrollment.section) == ("1", "B")
    assert [d.plan_code for d in fee_service.get_ledger(new_enrollment.enrollment_id)] == ["1-FEE-1"]
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


def test_copy_plans_to_next_term(lkg_fee):
    year = _year()
    fee_service.save_milestones(MilestoneSet(academic_year_id=year.id, milestones=[
        MilestoneInput(due_date=date(2026, 10, 31), cumulative_percent=50)]))
    next_year = academic_year_service.create_year(AcademicYearCreate(start_year=2027))
    assert fee_service.copy_plans(year.id, next_year.id, increase_percent=10) == 5  # 4 LKG/VAN + migrated 2-FEE-1
    plans = {p.code: p for p in fee_service.list_plans(next_year.id)}
    assert plans["LKG-FEE-1"].annual_amount_paise == 2640000 and plans["LKG-FEE-1"].is_default
    assert [m.due_date for m in fee_service.get_milestones(next_year.id)] == [date(2027, 10, 31)]
    assert fee_service.copy_plans(year.id, next_year.id) == 0


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
