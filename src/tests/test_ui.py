"""Streamlit page tests (AppTest runs each script headlessly in-process)."""
import pytest
from streamlit.testing.v1 import AppTest

from config import settings
from config.settings import PROJECT_ROOT
from data_management.dto.user import UserCreate
from data_management.services import auth_service
from ui.common import SESSION_USER

PAGES = [
    "ui/account.py", "ui/student/students.py", "ui/student/guardians.py", "ui/billing/billing.py",
    "ui/billing/receipts.py", "ui/analytics/summary.py", "ui/reports/reports.py", "ui/admin/setup.py",
    "ui/admin/promotion.py", "ui/admin/users.py", "ui/admin/backup.py",
]
ADMIN_PAGES = [page for page in PAGES if page.startswith("ui/admin/")]


@pytest.fixture
def ui_db(app_db, tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "BACKUP_DIR", tmp_path / "ui_backups")
    return app_db


@pytest.fixture
def admin(ui_db):
    return auth_service.create_user(UserCreate(username="admin", password="admin123", role="ADMIN"))


@pytest.fixture
def biller(ui_db):
    return auth_service.create_user(UserCreate(username="clerk", password="clerk123", role="BILLER"))


def _run(script, user=None, **state):
    app = AppTest.from_file(str(PROJECT_ROOT / script), default_timeout=60)
    if user:
        app.session_state[SESSION_USER] = user
    for key, value in state.items():
        app.session_state[key] = value
    return app.run()


def _errors(app):
    return [e.value for e in app.exception] + [e.value for e in app.error]


def test_first_run_setup_then_login(ui_db):
    app = _run("app.py")
    assert "first-time setup" in app.title[0].value
    app.text_input[0].set_value("principal")
    app.text_input[1].set_value("school2026")
    app.text_input[2].set_value("school2026")
    app.button[0].click().run()
    assert app.session_state[SESSION_USER].username == "principal"
    assert not _errors(app)

    login = _run("app.py")
    login.text_input[0].set_value("principal")
    login.text_input[1].set_value("wrong-pass1")
    login.button[0].click().run()
    assert "Invalid username or password." in [e.value for e in login.error]
    login.text_input[1].set_value("school2026")
    login.button[0].click().run()
    assert login.session_state[SESSION_USER].is_admin


def test_home_through_navigation(admin):
    app = _run("app.py", admin)
    assert not _errors(app)
    assert any("Collected today" == m.label for m in app.metric)


@pytest.mark.parametrize("page", PAGES)
def test_every_page_renders_for_admin(admin, page):
    app = _run(page, admin)
    assert not _errors(app), _errors(app)


@pytest.mark.parametrize("page", ADMIN_PAGES)
def test_billers_are_kept_out_of_admin_pages(biller, page):
    app = _run(page, biller)
    assert "only available to administrators" in app.error[0].value


def test_pages_require_login(ui_db):
    assert "Please log in." in _run("ui/billing/billing.py").warning[0].value


def test_collect_fee_end_to_end(admin):
    app = _run("ui/billing/billing.py", admin, bill_student_id=1)
    assert not _errors(app)
    assert app.subheader[0].value == "PRADEEP"
    amount = next(n for n in app.number_input if n.label.startswith("Amount received"))
    amount.set_value(3700.0).run()
    next(b for b in app.button if b.label == "Fill oldest first").click().run()
    assert not _errors(app)
    review = next(b for b in app.button if b.label == "Review and save receipt")
    assert not review.disabled
    review.click().run()
    confirm = next(b for b in app.button if b.label == "Confirm and save receipt")
    confirm.click().run()
    assert not _errors(app)
    assert any("RCPT/2026-27/00004" in s.value for s in app.success)

    from data_management.services import payment_service
    receipt = payment_service.find_by_receipt_no("RCPT/2026-27/00004")
    assert receipt.amount_paise == 370000 and receipt.collected_by == "admin"
    assert [a.label for a in receipt.allocations] == ["Tuition Fee - Oct 2026", "Tuition Fee - Nov 2026"]


def test_add_student_through_form(admin):
    app = _run("ui/student/students.py", admin)
    form_inputs = {t.label: t for t in app.text_input}
    form_inputs["Full name *"].set_value("Kavya R")
    next(s for s in app.selectbox if s.label == "Category *").set_value("DG 2")
    next(s for s in app.selectbox if s.label == "Class *").set_value("1")
    form_inputs["Aadhaar number (12 digits, stored encrypted)"].set_value("2341 2341 2346")
    form_inputs["Guardian name"].set_value("Revathi")
    form_inputs["Mobile"].set_value("9123456780")
    next(b for b in app.button if b.label == "Add student").click().run()
    assert not _errors(app), _errors(app)
    assert any("Added Kavya R" in s.value for s in app.success)

    from data_management.dto.student import StudentSearch
    from data_management.services import student_service
    found = student_service.search_students(StudentSearch(text="Kavya"))[0]
    profile = student_service.get_profile(found.student_id)
    assert profile.identifier_last_4 == "2346" and profile.primary_guardian.name == "Revathi"
    assert profile.enrollments[0].student_class == "1"


def test_add_student_shows_validation_errors(admin):
    app = _run("ui/student/students.py", admin)
    next(b for b in app.button if b.label == "Add student").click().run()
    message = app.error[0].value
    assert "Please correct" in message
    assert "Name: Name is required" in message and "Category: This field is required" in message
    assert "Enrollment > student class: This field is required" in message
    assert "Enter the guardian's name" in app.error[1].value
